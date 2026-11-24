"""Build and run an isolated CFRA column-block trial on luindex."""
import argparse
import json
import os
from pathlib import Path
import re
import runpy
import shlex
import subprocess
from tempfile import TemporaryDirectory
import time

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/flpq-all"
BASE = ROOT / "build/gpu-mxm-alias"
HEADER = ROOT / "experiments/2026-11-24-store-column-blocks/store_column_blocks.hpp"


def build_trial(work):
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
        code = code.replace(old, f"""            if (store_blocks::matches(a, b, c)) {{
                {group}.push_back({{&a, {rhs}}});
                continue;
            }}
            ++calls;
{old}
        if (!{group}.empty())
            calls += store_blocks::multiply(tmp, {left_store}.get("Al"), {group});
""")
    code = code.replace("    result.iterations   = iter;",
                        '    std::cerr << "TrialMxM: " << calls << "\\n";\n    result.iterations   = iter;')
    generated = work / source.name
    generated.write_text(code)
    flags = []
    for line in (BASE / "CMakeFiles/cfra.dir/flags.make").read_text().splitlines():
        if line.startswith(("CXX_DEFINES =", "CXX_INCLUDES =", "CXX_FLAGS =")):
            flags.extend(shlex.split(line.split("=", 1)[1]))
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
    args = parser.parse_args()
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
        trial = build_trial(work)
        query = "java_points_to.cnf"
        graph, grammars = importer["prepare"](
            DATA / "6.0.0/graph/luindex.tar.gz", "luindex", {query}, work)
        digest = importer["sha256"]
        inputs = {"graph.txt": digest(graph), query: digest(grammars[query])}
        if inputs != json.loads((DATA / "cuda-baseline-resume/inputs-luindex.json").read_text()):
            raise ValueError("Input hashes differ from benchmark")
        (out / "manifest.json").write_text(json.dumps(dict(inputs=inputs, build=hashes,
            header_sha256=digest(HEADER), trial_sha256=digest(trial)), indent=2))
        for label, binary in (("baseline", BASE / "cfra"), ("trial", trial)):
            deps = subprocess.check_output(["ldd", str(binary)], env=env, text=True)
            if not any(line.split()[:3] == ["libcubool.so", "=>", str(library)]
                       for line in deps.splitlines()):
                raise ValueError(f"Wrong library for {label}")
            command = [str(binary), "--graph", str(graph), "--grammar", str(grammars[query]),
                       "--algo", "incremental"]
            print("START", label, flush=True)
            prefix = out / label
            monitor = None
            with prefix.with_suffix(".stdout").open("wb") as stdout, prefix.with_suffix(".stderr").open("wb") as stderr, prefix.with_suffix(".vram.csv").open("wb") as memory:
                monitor = subprocess.Popen(["nvidia-smi", "--query-gpu=memory.used",
                                            "--format=csv,noheader,nounits", "-l", "1"],
                                           stdout=memory, stderr=stderr)
                start = time.monotonic()
                try:
                    result = subprocess.run(command, env=env, stdout=stdout, stderr=stderr, timeout=900)
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
            row = dict(build=label, wall_seconds=seconds, pairs=int(match[1]) if match else None,
                       mxm=int(calls[1]) if calls else None, exit_code=result.returncode,
                       sampled_device_peak_mib=max(samples, default=None))
            rows.append(row)
            (out / "results.json").write_text(json.dumps(rows, indent=2) + "\n")
            print(json.dumps(row), flush=True)
            if row["pairs"] != 9677 or row["exit_code"]:
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
