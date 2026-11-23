"""Run FLPQ_Data 6.0.0 CFPQ cases on the verified CUDA-only CFRA build."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import os
import platform
from pathlib import Path, PurePosixPath
import re
import subprocess
from statistics import mean, median, stdev
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/gpu-mxm-alias"
EMPTY_FILL_BUILD = ROOT / "build/gpu-empty-fill-alias"
ALGORITHMS = ("base", "incremental", "lazy")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024**2), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_build():
    manifest = ROOT / "experiments/2026-11-19-gpu-alias/manifest.json"
    hashes = json.loads(manifest.read_text())["sha256"]
    verify_hashes(hashes)
    return hashes


def verify_hashes(hashes):
    for name, expected in hashes.items():
        if sha256(ROOT / name) != expected:
            raise ValueError(f"Unexpected binary hash: {name}")


def save_benchmark_manifest(out, hashes, args, build):
    def capture(command):
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=15)
            return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
        except (OSError, subprocess.TimeoutExpired) as error:
            return {"error": str(error)}

    manifest = {
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": capture(["git", "-C", str(ROOT), "rev-parse", "HEAD"]),
        "status": capture(["git", "-C", str(ROOT), "status", "--porcelain"]),
        "sha256": hashes, "platform": platform.platform(), "timeout_seconds": args.timeout,
        "cpu": capture(["lscpu"]), "memory": capture(["free", "-b"]),
        "gpu": capture(["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                        "--format=csv"]), "build_cache": (build / "CMakeCache.txt").read_text(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def matrix_lines(source):
    if source.readline().strip().lower() != b"%%matrixmarket matrix coordinate pattern general":
        raise ValueError("Expected a general MatrixMarket pattern matrix")
    for line in source:
        line = line.strip()
        if line and not line.startswith(b"%"):
            yield line.split()


def prepare(archive, graph, grammars, directory):
    graph_path = directory / "graph.txt"
    vertices = None
    highest = -1
    labels = set()
    grammar_paths = {}
    with tarfile.open(archive, "r|gz") as tar, graph_path.open("w", buffering=1024**2) as edges:
        for member in tar:
            parts = PurePosixPath(member.name).parts
            if not member.isfile() or not parts or parts[0] != graph:
                continue
            name = parts[-1]
            if len(parts) == 5 and parts[1:3] == ("queries", "cfpq") and name in grammars:
                if name in grammar_paths:
                    raise ValueError(f"Duplicate grammar: {name}")
                path = directory / name
                with tar.extractfile(member) as source:
                    path.write_bytes(source.read())
                grammar_paths[name] = path
            if len(parts) != 3 or parts[1] != "graph" or not name.endswith(".mtx"):
                continue
            label = name[:-4]
            if not label or any(char.isspace() for char in label):
                raise ValueError(f"Invalid label: {label!r}")
            forward, reverse = label, label + "_r"
            if forward in labels or reverse in labels:
                raise ValueError(f"Label collision: {label}")
            labels.update((forward, reverse))
            try:
                with tar.extractfile(member) as source:
                    lines = matrix_lines(source)
                    size = next(lines, [])
                    if len(size) != 3:
                        raise ValueError("Missing matrix dimensions")
                    rows, cols, count = map(int, size)
                    if rows != cols or not 0 < rows < 2**32 or count < 0:
                        raise ValueError(f"Invalid matrix dimensions/count: {size}")
                    if vertices is not None and rows != vertices:
                        raise ValueError(f"Graph dimensions differ: {rows} vs {vertices}")
                    vertices = rows
                    seen = 0
                    for pair in lines:
                        u, v = map(int, pair)
                        if not (0 <= u < rows and 0 <= v < cols):
                            raise ValueError(f"Vertex out of range: {u} {v}")
                        highest = max(highest, u, v)
                        edges.write(f"{u} {v} {forward}\n{v} {u} {reverse}\n")
                        seen += 1
                    if seen != count:
                        raise ValueError(f"Expected {count} entries, read {seen}")
            except ValueError as error:
                raise ValueError(f"{member.name}: {error}") from error
        if vertices is None:
            raise ValueError("No graph matrices found")
        tokens = set().union(*(set(path.read_text().split()) for path in grammar_paths.values()))
        if highest < vertices - 1:
            # CFRA infers dimensions from the largest vertex ID in the edge list.
            marker = "__cfra_dimension"
            while marker in tokens or marker in labels:
                marker += "_"
            edges.write(f"{vertices - 1} {vertices - 1} {marker}\n")
    # FLPQ stores family_N, while CFRA expands family_i to family_i_N.
    replacements = {}
    for label in sorted(labels):
        indexed = re.fullmatch(r"(.+)_(0|[1-9][0-9]*)(_r)?", label)
        if not indexed:
            continue
        family, index, reverse = indexed.groups()
        template = f"{family}{reverse or ''}_i"
        if template in tokens:
            target = f"{template}_{index}"
            if label in tokens or target in labels:
                raise ValueError(f"Ambiguous indexed label mapping: {label} -> {target}")
            replacements[label] = target
    if replacements:
        adapted = graph_path.with_suffix(".adapted")
        with graph_path.open() as original, adapted.open("w", buffering=1024**2) as edges:
            for line in original:
                src, dst, label = line.split()
                edges.write(f"{src} {dst} {replacements.get(label, label)}\n")
        adapted.replace(graph_path)
    return graph_path, grammar_paths


def run_case(command, expected, timeout, stdout_path, stderr_path, build=BUILD):
    start = time.monotonic()
    env = dict(os.environ, LD_LIBRARY_PATH=str(build / "cuBool/cubool"))
    env.pop("LD_PRELOAD", None)
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        try:
            code = subprocess.run(command, env=env, stdout=stdout, stderr=stderr,
                                  timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            return "timeout", f"Exceeded {timeout} seconds", None, time.monotonic() - start
        except OSError as error:
            return "launch_error", str(error), None, time.monotonic() - start
    seconds = time.monotonic() - start
    match = re.search(rb"^#SEdges:\s*(\d+)\s*$", stdout_path.read_bytes(), re.MULTILINE)
    actual = int(match[1]) if match else None
    if code:
        with stderr_path.open("rb") as stderr:
            stderr.seek(max(0, stderr_path.stat().st_size - 4096))
            tail = stderr.read().decode(errors="replace").strip().splitlines()
        detail = f"exit {code}" if code > 0 else f"signal {-code}"
        return "execution_error", f"{detail}: {tail[-1]}" if tail else detail, actual, seconds
    if actual is None:
        return "missing_result", "CFRA did not print #SEdges", None, seconds
    if expected is None:
        return "no_reference", "Catalog has no reference count", actual, seconds
    if actual != expected:
        return "mismatch", f"Expected {expected} pairs, got {actual}", actual, seconds
    return "pass", "", actual, seconds


def grammar_error(path):
    try:
        rules, footer = path.read_text().split("Count:")
    except (OSError, ValueError) as error:
        return f"Cannot read CNF grammar and its Count: section: {error}"
    if len(footer.split()) != 1:
        return "CFRA requires exactly one start symbol in the Count: section"
    if any(len(line.split()) > 3 for line in rules.splitlines()):
        return "CFRA cannot parse a CNF rule with more than three tokens"
    return None


def execute_case(command, expected, timeout, raw, sequence, allowed, error, build):
    if not allowed:
        return "skipped", "Correctness check did not pass", None, None, None, None
    if error is not None:
        return "input_error", error, None, None, None, None
    stdout, stderr = raw / f"{sequence:04d}.stdout", raw / f"{sequence:04d}.stderr"
    return (*run_case(command, expected, timeout, stdout, stderr, build), stdout, stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data/flpq-all/6.0.0")
    parser.add_argument("--out", type=Path, required=True, help="New report directory")
    parser.add_argument("--scratch", type=Path, help="Directory for one temporary converted graph")
    parser.add_argument("--graph", action="append", help="Limit to a graph (repeatable)")
    parser.add_argument("--case-list", type=Path, help="CSV with graph and grammar columns")
    parser.add_argument("--algo", choices=ALGORITHMS, action="append", help="Default: all three")
    parser.add_argument("--timeout", type=int, default=900, help="Seconds per solver invocation")
    parser.add_argument("--benchmark", action="store_true", help="Check, warm up, and measure five repeats")
    parser.add_argument("--empty-fill", action="store_true", help="Use the verified CUDA empty-fill candidate")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    build = EMPTY_FILL_BUILD if args.empty_fill else BUILD
    if args.empty_fill:
        manifest = ROOT / "data/flpq-all/gpu-empty-fill-alias/manifest.json"
        hashes = json.loads(manifest.read_text())["builds"]["trial"]
        verify_hashes(hashes)
    else:
        hashes = verify_build()

    cases = {}
    with (args.data / "reachable_pairs.csv").open(newline="", encoding="utf-8-sig") as catalog:
        for row in csv.DictReader(catalog):
            if row["query_class"] != "cfpq":
                continue
            graph, grammar = row["graph"], row["grammar"]
            if not all(re.fullmatch(r"[\w.-]+", value) and value not in (".", "..")
                       for value in (graph, grammar)):
                raise ValueError(f"Invalid catalog case: {graph}/{grammar}")
            references = cases.setdefault(graph, {})
            if grammar in references:
                raise ValueError(f"Duplicate catalog case: {graph}/{grammar}")
            value = row["num_reachable_pairs"].strip()
            references[grammar] = int(value) if value else None
    catalog_cases = cases
    if args.case_list:
        selected_cases = {}
        with args.case_list.open(newline="", encoding="utf-8-sig") as file:
            for row in csv.DictReader(file):
                graph, grammar = row.get("graph"), row.get("grammar")
                if graph not in cases or grammar not in cases[graph]:
                    parser.error(f"Unknown catalog case: {graph}/{grammar}")
                grammars = selected_cases.setdefault(graph, {})
                if grammar in grammars:
                    parser.error(f"Duplicate selected case: {graph}/{grammar}")
                grammars[grammar] = cases[graph][grammar]
        if not selected_cases:
            parser.error("--case-list contains no cases")
        cases = selected_cases
    if args.graph and set(args.graph) - cases.keys():
        parser.error(f"Unknown graphs: {sorted(set(args.graph) - cases.keys())}")
    selected = sorted(set(args.graph or cases))
    algos = tuple(dict.fromkeys(args.algo or ALGORITHMS))
    planned = sum(len(cases[graph]) for graph in selected) * len(algos)
    phases = ("check", "warmup", "measure", "measure", "measure", "measure", "measure")
    if args.benchmark:
        planned *= len(phases)
    else:
        phases = ("check",)

    args.out.mkdir(parents=True)
    raw = args.out / "raw"
    raw.mkdir()
    if args.benchmark or args.empty_fill:
        save_benchmark_manifest(args.out, hashes, args, build)
    counts = Counter()
    with (args.out / "summary.log").open("w", encoding="utf-8", buffering=1) as summary, (
        args.out / "results.jsonl"
    ).open("w", encoding="utf-8", buffering=1) as results:
        def log(message):
            print(message, flush=True)
            print(message, file=summary)

        log(f"Planned: {planned} runs on {len(selected)} graphs, timeout {args.timeout}s per run")
        for graph in selected:
            log(f"PREPARE {graph}")
            with tempfile.TemporaryDirectory(dir=args.scratch) as work:
                preparation_error = None
                try:
                    graph_path, grammars = prepare(args.data / "graph" / f"{graph}.tar.gz",
                                                   graph, catalog_cases[graph], Path(work))
                except (OSError, EOFError, tarfile.TarError, ValueError) as error:
                    preparation_error = str(error)
                if (args.benchmark or args.empty_fill) and preparation_error is None:
                    input_hashes = {name: sha256(grammars[name]) for name in cases[graph] if name in grammars}
                    input_hashes["graph.txt"] = sha256(graph_path)
                    (args.out / f"inputs-{graph}.json").write_text(json.dumps(input_hashes, indent=2) + "\n")
                for grammar, expected in sorted(cases[graph].items()):
                    error = preparation_error
                    if error is None:
                        error = (grammar_error(grammars[grammar]) if grammar in grammars
                                 else "Catalog grammar missing from archive")
                    for algo in algos:
                        repetitions = []
                        check_passed = False
                        for attempt, phase in enumerate(phases):
                            command = None
                            if error is None:
                                command = [str(build / "cfra"), "--graph", str(graph_path),
                                           "--grammar", str(grammars[grammar]), "--algo", algo]
                            log(f"START {graph}/{grammar}/{algo} {phase}")
                            status, reason, actual, seconds, stdout, stderr = execute_case(
                                command, expected, args.timeout, raw, sum(counts.values()) + 1,
                                check_passed or phase == "check", error, build)
                            if phase == "check":
                                check_passed = status == "pass"
                            if phase == "measure" and status == "pass":
                                repetitions.append(seconds)
                            counts[status] += 1
                            result = dict(graph=graph, grammar=grammar, algo=algo, status=status,
                                          reason=reason, expected=expected, actual=actual, seconds=seconds,
                                          stdout=str(stdout.relative_to(args.out)) if stdout else None,
                                          stderr=str(stderr.relative_to(args.out)) if stderr else None)
                            if args.benchmark:
                                result.update(phase=phase, repeat=attempt - 1 if phase == "measure" else None)
                            print(json.dumps(result), file=results)
                            outcome = reason or f"{actual} pairs"
                            duration = f" ({seconds:.2f}s)" if seconds is not None else ""
                            log(f"[{sum(counts.values())}/{planned}] {status.upper()} "
                                f"{graph}/{grammar}/{algo} {phase}: {outcome}{duration}")
                        if args.benchmark and repetitions:
                            log(f"TIMING {graph}/{grammar}/{algo} successful={len(repetitions)}/5 "
                                f"median={median(repetitions):.6f}s mean={mean(repetitions):.6f}s "
                                f"min={min(repetitions):.6f}s max={max(repetitions):.6f}s "
                                f"sample_sd={stdev(repetitions) if len(repetitions) > 1 else 'n/a'}")
        failures = planned - counts["pass"] - counts["no_reference"]
        log(f"TOTAL {planned}: passed={counts['pass']}, failed={failures}, "
            f"without_reference={counts['no_reference']}")
        log(f"ALL PASSED: {'yes' if counts['pass'] == planned else 'no'}")
    return 1 if failures else 2 if counts["no_reference"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
