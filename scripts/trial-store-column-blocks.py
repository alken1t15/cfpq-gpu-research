"""Build and run an isolated CFRA column-block trial on luindex."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import runpy
import shlex
import subprocess
from statistics import median
from tempfile import TemporaryDirectory
import time

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/flpq-all"
BASE = ROOT / "build/gpu-mxm-alias"
HEADER = ROOT / "experiments/2026-11-24-store-column-blocks/store_column_blocks.hpp"


def build_trial(work, phase_timing=False, single_unpack=False, cache=False, nvtx_include=None,
                progress=False):
    source = ROOT / "src/cfra/src/incremental_algo/incremental_algo.cpp"
    code = '#include "store_column_blocks.hpp"\n' + source.read_text()
    code = code.replace("    int iter = 0;", "    unsigned long long calls = 0;\n    int iter = 0;")
    marker = "        for (auto& [a, b, c] : grammar.complex_rules()) {"
    for lhs, rhs, group in (("mb", "dmc", "right_delta"), ("dmb", "mc", "right_full")):
        old = f"            CB_CHECK(cuBool_MxM(tmp.get_ensure(a), {lhs}, {rhs}, CUBOOL_HINT_ACCUMULATE));\n            tmp.invalidate(a);\n        }}"
        if code.count(old) != 1:
            raise ValueError("Unexpected incremental rule loop")
        index = code.rindex(marker, 0, code.index(old))
        code = code[:index] + f"        std::vector<store_blocks::Operand> {group};\n" + code[index:]
        left_store = "M" if lhs == "mb" else "DM"
        census = ""
        if phase_timing:
            census = ", false" if lhs == "mb" else ", immutable_store"
        if cache:
            census = ", nullptr" if lhs == "mb" else ", immutable_store ? &package_cache : nullptr"
        code = code.replace(old, f"""            if (store_blocks::matches(a, b, c)) {{
                {group}.push_back({{&a, {rhs}}});
                continue;
            }}
            ++calls;
{old}
        if (!{group}.empty())
            calls += store_blocks::multiply(tmp, {left_store}.get("Al"), {group}{census});
""")
    code = code.replace("    result.iterations   = iter;",
                        '    std::cerr << "TrialMxM: " << calls << "\\n";\n    result.iterations   = iter;')
    if phase_timing or cache:
        code = code.replace("    int iter = 0;", """
    const auto writes_store = [](const auto& rule) { return std::get<0>(rule).starts_with("store_i_"); };
    const bool immutable_store =
        std::none_of(grammar.epsilon_rules().begin(), grammar.epsilon_rules().end(),
            [](const auto& symbol) { return symbol.starts_with("store_i_"); })
        && std::none_of(grammar.terminal_rules().begin(), grammar.terminal_rules().end(), writes_store)
        && std::none_of(grammar.simple_rules().begin(), grammar.simple_rules().end(), writes_store)
        && std::none_of(grammar.complex_rules().begin(), grammar.complex_rules().end(), writes_store);
    int iter = 0;""")
    if cache:
        code = "#define STORE_BLOCK_CACHE\n" + code
        code = code.replace("    int iter = 0;", "    store_blocks::PackageCache package_cache;\n    int iter = 0;")
        code = code.replace("    result.iterations   = iter;", """
    std::cerr << "PackageCache: " << package_cache.hits << " " << package_cache.matrices.size()
        << " " << package_cache.csr_bytes << "\\n";
    result.iterations   = iter;""")
    if phase_timing:
        code = "#define STORE_BLOCK_TIMING\n" + code
        code = code.replace("    result.iterations   = iter;", """
    std::cerr << "BlockPhases: " << store_blocks::batches
        << " " << std::chrono::duration<double>(store_blocks::packing).count()
        << " " << std::chrono::duration<double>(store_blocks::product_time).count()
        << " " << std::chrono::duration<double>(store_blocks::unpacking).count() << "\\n";
    std::cerr << "CacheCensus: " << immutable_store << " " << store_blocks::cache_packages
        << " " << store_blocks::seen_packages.size() << " " << store_blocks::cache_hits
        << " " << store_blocks::cache_bytes << " "
        << std::chrono::duration<double>(store_blocks::repeated_packing).count() << "\\n";
    result.iterations   = iter;""")
    if single_unpack:
        code = "#define STORE_BLOCK_SINGLE_UNPACK\n" + code
    if progress:
        code = code.replace("    int iter = 0;", '    std::cerr << "PROGRESS initialized\\n";\n    int iter = 0;')
        code = code.replace("        iter++;", '        iter++;\n        std::cerr << "PROGRESS begin " << iter << "\\n";')
        code = code.replace("        if (dm_total == 0)", '''
        std::cerr << "PROGRESS end " << iter << " mxm=" << calls << " delta=" << dm_total << "\\n";
        if (dm_total == 0)''')
    if nvtx_include:
        pattern = r"CB_CHECK\((cuBool_\w+)(?=\()"
        code = re.sub(pattern, r'CFRA_NVTX_CHECK("incremental/\1", \1', code)
        header = re.sub(pattern, r'CFRA_NVTX_CHECK("store_blocks/\1", \1', HEADER.read_text())
        (work / HEADER.name).write_text(header)
        (work / "cfra_nvtx.hpp").write_text(
            '#include <nvtx3/nvtx3.hpp>\n'
            '#define CFRA_NVTX_CHECK(label, call) \\\n'
            '    do { const nvtx3::scoped_range range{label}; CB_CHECK(call); } while (false)\n')
        code = '#include "cfra_nvtx.hpp"\n' + code
    generated = work / source.name
    generated.write_text(code)
    flags = []
    for line in (BASE / "CMakeFiles/cfra.dir/flags.make").read_text().splitlines():
        if line.startswith(("CXX_DEFINES =", "CXX_INCLUDES =", "CXX_FLAGS =")):
            flags.extend(shlex.split(line.split("=", 1)[1]))
    if nvtx_include:
        flags.extend(["-I", str(nvtx_include)])
    obj, binary = work / "incremental.o", work / "cfra"
    command = ["/usr/bin/g++-13", *flags, "-I" + str(source.parent), "-I" + str(HEADER.parent),
               "-c", str(generated), "-o", str(obj)]
    link = shlex.split((BASE / "CMakeFiles/cfra.dir/link.txt").read_text())
    link[link.index("-o") + 1] = str(binary)
    link[link.index("CMakeFiles/cfra.dir/src/incremental_algo/incremental_algo.cpp.o")] = str(obj)
    for cmd in (command, link):
        subprocess.run(cmd, cwd=BASE, timeout=180, check=True)
    return binary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    report_cases = ROOT / "experiments/2026-11-21-flpq-gpu-suite/benchmark-cases.csv"
    parser.add_argument("--case-list", type=Path, default=report_cases)
    parser.add_argument("--graph", default="luindex")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--progress", action="store_true", help="Log incremental iteration boundaries for diagnostics")
    parser.add_argument("--phase-timing", action="store_true", help="Measure host-observed block phases in a diagnostic run")
    parser.add_argument("--single-unpack", action="store_true", help="Partition a single extraction of the packed result")
    parser.add_argument("--pairs", type=int, default=1)
    parser.add_argument("--compare-unpack", action="store_true",
                        help="Compare per-block extraction against single-pass unpacking")
    parser.add_argument("--compare-cache", action="store_true",
                        help="Compare single-pass unpacking with and without a package cache")
    parser.add_argument("--profile", action="store_true",
                        help="Capture CUDA traces for a single cache comparison pair")
    parser.add_argument("--nvtx-include", type=Path,
                        help="Add per-operation NVTX ranges using this NVTX include directory")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    with args.case_list.open(newline="", encoding="utf-8-sig") as file:
        queries = {row["graph"]: row["grammar"] for row in csv.DictReader(file)}
    queries.setdefault("lusearch", "java_points_to.cnf")
    if args.graph not in queries:
        parser.error(f"Unknown graph: {args.graph}")
    if args.graph != "luindex" and not args.compare_cache:
        parser.error("Graphs other than luindex require --compare-cache")
    query = queries[args.graph]
    with (DATA / "6.0.0/reachable_pairs.csv").open(newline="", encoding="utf-8-sig") as file:
        references = [row["num_reachable_pairs"] for row in csv.DictReader(file)
                      if row["graph"] == args.graph and row["grammar"] == query
                      and row["query_class"] == "cfpq"]
    if len(references) != 1 or not references[0].strip():
        parser.error(f"Missing unique CFPQ reference for {args.graph}/{query}")
    expected_pairs = int(references[0])
    expect_hits = args.graph in ("luindex", "lusearch")
    if args.profile and (not args.compare_cache or args.pairs != 1):
        parser.error("--profile requires --compare-cache with one pair")
    if args.nvtx_include:
        args.nvtx_include = args.nvtx_include.resolve()
        if not args.profile or not (args.nvtx_include / "nvtx3/nvtx3.hpp").is_file():
            parser.error("--nvtx-include requires --profile and a directory containing nvtx3/nvtx3.hpp")
    if args.compare_cache and (args.compare_unpack or args.phase_timing or args.single_unpack):
        parser.error("--compare-cache selects both cache variants and disables phase timing")
    if args.compare_unpack and (args.phase_timing or args.single_unpack):
        parser.error("--compare-unpack selects both unpacking variants and disables phase timing")
    if args.pairs < 1 or (args.phase_timing and args.pairs != 1):
        parser.error("Expected positive pairs; phase timing runs once")
    out = args.out.resolve()
    out.mkdir()
    importer = runpy.run_path(str(ROOT / "scripts/check-gpu-flpq-data.py"))
    importer["verify_build"]()
    hashes = json.loads((DATA / "gpu-fill-host-bins/manifest.json").read_text())["builds"]["trial"]
    importer["verify_hashes"](hashes)
    library = ROOT / next(path for path in hashes if path.endswith("/libcubool.so"))
    env = dict(os.environ, LD_LIBRARY_PATH=str(library.parent))
    env.pop("LD_PRELOAD", None)
    rows = []
    with TemporaryDirectory() as folder:
        work = Path(folder)
        single_unpack = args.single_unpack or args.compare_unpack or args.compare_cache
        trial = build_trial(work, args.phase_timing, single_unpack, args.compare_cache, args.nvtx_include,
                            args.progress)
        baseline = BASE / "cfra"
        if args.compare_unpack or args.compare_cache:
            separate = work / "separate"
            separate.mkdir()
            baseline = build_trial(separate, single_unpack=args.compare_cache, nvtx_include=args.nvtx_include,
                                   progress=args.progress)
        archive = DATA / "6.0.0/graph" / f"{args.graph}.tar.gz"
        graph, grammars = importer["prepare"](archive, args.graph, {query}, work)
        digest = importer["sha256"]
        inputs = {"graph.txt": digest(graph), query: digest(grammars[query])}
        if args.graph != "lusearch" and args.case_list == report_cases:
            benchmark_inputs = [DATA / group / f"inputs-{args.graph}.json"
                                for group in ("cuda-baseline", "cuda-baseline-resume")]
            recorded = [json.loads(path.read_text()) for path in benchmark_inputs if path.is_file()]
            if not recorded or any(any(hashes.get(key) != value for key, value in inputs.items())
                                   for hashes in recorded):
                raise ValueError(f"Input hashes differ from report for {args.graph}")
        (out / "manifest.json").write_text(json.dumps(dict(inputs=inputs, build=hashes,
            graph=args.graph, expected_pairs=expected_pairs, archive_sha256=digest(archive),
            header_sha256=digest(HEADER), trial_sha256=digest(trial), phase_timing=args.phase_timing,
            baseline_sha256=digest(baseline), single_unpack=single_unpack,
            compare_unpack=args.compare_unpack, compare_cache=args.compare_cache,
            profile=args.profile, nvtx=bool(args.nvtx_include), pairs=args.pairs,
            progress=args.progress, timeout_seconds=args.timeout), indent=2))
        binaries = {"baseline": baseline, "trial": trial}
        schedule = [("diagnostic", "trial")] if args.phase_timing else []
        if not args.phase_timing:
            if args.pairs > 1:
                schedule.extend(("warmup", label) for label in binaries)
            for pair in range(args.pairs):
                order = ("baseline", "trial") if pair % 2 == 0 else ("trial", "baseline")
                schedule.extend((f"pair-{pair + 1}", label) for label in order)
        expected_mxm = 79639 if args.graph == "luindex" else None
        for phase, label in schedule:
            binary = binaries[label]
            deps = subprocess.check_output(["ldd", str(binary)], env=env, text=True)
            if not any(line.split()[:3] == ["libcubool.so", "=>", str(library)]
                       for line in deps.splitlines()):
                raise ValueError(f"Wrong library for {label}")
            command = [str(binary), "--graph", str(graph), "--grammar", str(grammars[query]),
                       "--algo", "incremental"]
            print("START", phase, label, flush=True)
            prefix = out / f"{phase}-{label}"
            if args.profile:
                trace = "cuda,nvtx" if args.nvtx_include else "cuda"
                command = ["nsys", "profile", f"--trace={trace}", "--sample=none", "--cpuctxsw=none",
                           f"--output={prefix}", *command]
            monitor = None
            with prefix.with_suffix(".stdout").open("wb") as stdout, prefix.with_suffix(".stderr").open("wb") as stderr, prefix.with_suffix(".vram.csv").open("wb") as memory:
                monitor = subprocess.Popen(["nvidia-smi", "--query-gpu=memory.used",
                                            "--format=csv,noheader,nounits", "-l", "1"],
                                           stdout=memory, stderr=stderr)
                start = time.monotonic()
                try:
                    result = subprocess.run(command, env=env, stdout=stdout, stderr=stderr, timeout=args.timeout)
                    exit_code, reason = result.returncode, ""
                except subprocess.TimeoutExpired:
                    exit_code, reason = None, f"Timeout after {args.timeout} seconds"
                finally:
                    seconds = time.monotonic() - start
                    monitor.terminate()
                    monitor.wait(timeout=10)
            stdout = prefix.with_suffix(".stdout").read_text()
            stderr = prefix.with_suffix(".stderr").read_text()
            match = re.search(r"^#SEdges:\s*(\d+)$", stdout, re.M)
            calls = re.search(r"^TrialMxM: (\d+)$", stderr, re.M)
            samples = [int(value) for value in prefix.with_suffix(".vram.csv").read_text().splitlines()
                       if value.strip().isdigit()]
            row = dict(build=label, phase=phase, wall_seconds=seconds, pairs=int(match[1]) if match else None,
                       mxm=int(calls[1]) if calls else None, exit_code=exit_code, reason=reason,
                       sampled_device_peak_mib=max(samples, default=None))
            if args.phase_timing:
                phases = re.search(r"^BlockPhases: (\d+) (\S+) (\S+) (\S+)$", stderr, re.M)
                if not phases:
                    raise ValueError("Missing phase timings; see trial.stderr")
                row["phases"] = dict(batches=int(phases[1]), packing_seconds=float(phases[2]),
                                     multiply_seconds=float(phases[3]), unpacking_seconds=float(phases[4]))
                census = re.search(r"^CacheCensus: ([01]) (\d+) (\d+) (\d+) (\d+) (\S+)$", stderr, re.M)
                if not census:
                    raise ValueError("Missing cache census; see trial.stderr")
                row["cache_census"] = dict(immutable_store=census[1] == "1",
                    packages=int(census[2]), unique=int(census[3]), repeats=int(census[4]),
                    csr_bytes=int(census[5]), repeated_packing_seconds=float(census[6]))
            if args.compare_cache and label == "trial" and exit_code == 0:
                stats = re.search(r"^PackageCache: (\d+) (\d+) (\d+)$", stderr, re.M)
                if not stats or (expect_hits and not int(stats[1])):
                    raise ValueError(f"Expected cache hits on {args.graph}")
                row["cache"] = dict(hits=int(stats[1]), entries=int(stats[2]), csr_bytes=int(stats[3]))
            rows.append(row)
            (out / "results.json").write_text(json.dumps(rows, indent=2) + "\n")
            print(json.dumps(row), flush=True)
            if row["pairs"] != expected_pairs or exit_code != 0:
                return 1
            if args.compare_unpack or args.compare_cache:
                if not row["mxm"] or (expected_mxm is not None and row["mxm"] != expected_mxm):
                    raise ValueError(f"Unexpected MxM calls on {args.graph}")
                expected_mxm = row["mxm"]
            if args.profile:
                with prefix.with_suffix(".stats.csv").open("wb") as stats, prefix.with_suffix(".stats.stderr").open("wb") as stderr:
                    subprocess.run(["nsys", "stats", "--report=cuda_api_sum,cuda_gpu_kern_sum,cuda_gpu_mem_time_sum",
                                    "--format=csv", str(prefix.with_suffix(".nsys-rep"))],
                                   stdout=stats, stderr=stderr, timeout=600, check=True)
    if not args.phase_timing and not args.profile:
        medians = {label: median(row["wall_seconds"] for row in rows
                                if row["build"] == label and row["phase"].startswith("pair-"))
                   for label in binaries}
        (out / "summary.json").write_text(json.dumps(medians, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
