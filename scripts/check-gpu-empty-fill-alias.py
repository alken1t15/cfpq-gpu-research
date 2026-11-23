"""Compare CUDA baseline and empty-fill candidate on identical luindex inputs."""
import json
import os
from pathlib import Path
import re
import runpy
from statistics import median
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "build/gpu-mxm-alias"
TRIAL = ROOT / "build/gpu-empty-fill-alias"
DATA = ROOT / "data/flpq-all"
OUT = DATA / "gpu-empty-fill-alias"


def main():
    importer = runpy.run_path(str(ROOT / "scripts/check-gpu-flpq-data.py"))
    digest = importer["sha256"]
    importer["verify_build"]()
    builds = {"baseline": BASE, "trial": TRIAL}
    libraries = {name: build / "cuBool/cubool/libcubool.so" for name, build in builds.items()}
    hashes = {name: {str(path.relative_to(ROOT)): digest(path)
                    for path in (build / "cfra", libraries[name])}
              for name, build in builds.items()}
    environments = {}
    for name, library in libraries.items():
        env = dict(os.environ, LD_LIBRARY_PATH=str(library.parent))
        env.pop("LD_PRELOAD", None)
        dependencies = subprocess.check_output(["ldd", str(BASE / "cfra")], env=env, text=True)
        if not any(line.split()[:3] == ["libcubool.so", "=>", str(library)]
                   for line in dependencies.splitlines()):
            raise ValueError(f"Unexpected cuBool library for {name}: {dependencies}")
        environments[name] = env
    OUT.mkdir()
    (OUT / "manifest.json").write_text(json.dumps({
        "source": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "builds": hashes, "timeout_seconds": 900,
    }, indent=2) + "\n")
    for script, flags in (
        ("check-cubool-mxm-pairs.py", ["--gpu", "--collect-failures"]),
        ("probe-matrix-primitives.py", ["--gpu"]),
        ("check-gpu-mxm-boundaries.py", [str(OUT / "boundaries.json")]),
    ):
        print("REGRESSION", script, flush=True)
        with (OUT / (script + ".log")).open("w") as log:
            subprocess.run([sys.executable, str(ROOT / "scripts" / script),
                            str(libraries["trial"]), *flags],
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)

    pizza = ROOT / "data/trial-catalog/pizza"
    smoke = subprocess.run([str(TRIAL / "cfra"), "--graph", str(pizza / "cfra-graph.txt"),
                            "--grammar", str(pizza / "nested_parentheses_subClassOf_type.cnf"),
                            "--algo", "incremental"],
                           env=environments["trial"],
                           capture_output=True, text=True, timeout=900)
    (OUT / "pizza.stdout").write_text(smoke.stdout)
    (OUT / "pizza.stderr").write_text(smoke.stderr)
    if smoke.returncode or not re.search(r"^#SEdges:\s*1356\s*$", smoke.stdout, re.MULTILINE):
        raise RuntimeError("Pizza correctness check failed")
    print("PASS pizza incremental: 1356 pairs", flush=True)

    query = "java_points_to.cnf"
    folder = DATA / "cuda-baseline-resume"
    reference = json.loads((folder / "inputs-luindex.json").read_text())
    samples = {name: [] for name in builds}
    schedule = [("warmup", name) for name in builds]
    for pair in range(5):
        order = ("baseline", "trial") if pair % 2 == 0 else ("trial", "baseline")
        schedule.extend((f"pair-{pair + 1}", name) for name in order)

    with TemporaryDirectory() as scratch, (OUT / "results.jsonl").open("w", buffering=1) as results:
        graph, grammars = importer["prepare"](DATA / "6.0.0/graph/luindex.tar.gz",
                                             "luindex", {query}, Path(scratch))
        grammar = grammars[query]
        if {"graph.txt": digest(graph), query: digest(grammar)} != reference:
            raise ValueError("luindex input hashes differ from benchmark")
        (OUT / "inputs.json").write_text(json.dumps(reference, indent=2) + "\n")
        for phase, label in schedule:
            print("START", phase, label, flush=True)
            command = [str(BASE / "cfra"), "--graph", str(graph),
                       "--grammar", str(grammar), "--algo", "incremental"]
            stdout_path, stderr_path = [OUT / f"{phase}-{label}.{ext}" for ext in ("stdout", "stderr")]
            start = time.monotonic()
            code = None
            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                try:
                    code = subprocess.run(command, env=environments[label], stdout=stdout, stderr=stderr,
                                          timeout=900).returncode
                except subprocess.TimeoutExpired:
                    pass
            seconds = time.monotonic() - start
            output = stdout_path.read_text(errors="replace")
            match = re.search(r"^#SEdges:\s*(\d+)\s*$", output, re.MULTILINE)
            actual = int(match[1]) if match else None
            status = "timeout" if code is None else "pass" if code == 0 and actual == 9677 else "failure"
            print(json.dumps(dict(phase=phase, build=label, seconds=seconds, expected=9677,
                                  actual=actual, exit_code=code, status=status,
                                  stdout=stdout_path.name, stderr=stderr_path.name)), file=results)
            print("END", phase, label, status, actual, f"{seconds:.3f}s", flush=True)
            if status != "pass":
                return 1
            if phase != "warmup":
                samples[label].append(seconds)
    for name, checksums in hashes.items():
        for path, expected in checksums.items():
            if digest(ROOT / path) != expected:
                raise ValueError(f"Changed {name} artifact: {path}")
    summary = {label: dict(samples=times, median=median(times)) for label, times in samples.items()}
    summary["baseline_over_trial"] = summary["baseline"]["median"] / summary["trial"]["median"]
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
