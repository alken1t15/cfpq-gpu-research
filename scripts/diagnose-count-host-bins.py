"""Count CFRA iterations and MxM calls, and correlate them with full Nsight traces."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import runpy
import shlex
import sqlite3
import subprocess
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/flpq-all"
BASE = ROOT / "build/gpu-mxm-alias"


def summarize_rules(stderr, grammar, total):
    templates = []
    for line in grammar.split("Count:", 1)[0].splitlines():
        symbols = line.split()
        if len(symbols) != 3 or not any(s.endswith("_i") for s in symbols):
            continue
        parts = []
        for symbol in symbols:
            suffix = ""
            if symbol.endswith("_i"):
                suffix = r"_(?P=index)" if any("(?P<index>" in part for part in parts) else r"_(?P<index>\d+)"
            parts.append(re.escape(symbol) + suffix)
        templates.append((" ".join(symbols), re.compile(" ".join(parts))))
    counts = Counter()
    for line in stderr.splitlines():
        if not line.startswith("CFRA_RULE "):
            continue
        _, first, second, third, count = line.split()
        rule = " ".join((first, second, third))
        families = [name for name, pattern in templates if pattern.fullmatch(rule)]
        if len(families) > 1:
            raise ValueError(f"Ambiguous template for {rule}")
        counts[families[0] if families else "unindexed"] += int(count)
    if sum(counts.values()) != total:
        raise ValueError("Per-rule MxM counts do not sum to the overall counter")
    return dict(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--indexed-rules", action="store_true",
                        help="Run an unprofiled per-rule census with the verified fill library")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True)
    importer = runpy.run_path(str(ROOT / "scripts/check-gpu-flpq-data.py"))
    importer["verify_build"]()
    tag = "gpu-fill-host-bins" if args.indexed_rules else "gpu-count-host-bins"
    builds = json.loads((DATA / tag / "manifest.json").read_text())["builds"]
    importer["verify_hashes"]({**builds["baseline"], **builds["trial"]})
    if args.indexed_rules:
        builds = {"trial": builds["trial"]}

    source = ROOT / "src/cfra/src/incremental_algo/incremental_algo.cpp"
    code = "#include <iostream>\n" + source.read_text()
    code, calls = re.subn(r"(?m)^( +)(CB_CHECK\(cuBool_MxM\()", r"\1++mxm_calls;\n\1\2", code)
    if calls != 2 or code.count("    int iter = 0;") != 1 or code.count("    result.iterations   = iter;") != 1:
        raise ValueError("Unexpected incremental solver source")
    code = code.replace("    int iter = 0;", "    unsigned long long mxm_calls = 0;\n    int iter = 0;")
    code = code.replace("    result.iterations   = iter;",
                        '    std::cerr << "CFRA_COUNTS iterations=" << iter << " mxm=" << mxm_calls << "\\n";\n'
                        "    result.iterations   = iter;")
    if args.indexed_rules:
        code = "#include <map>\n#include <tuple>\n" + code
        code = code.replace("    int iter = 0;",
                            "    std::map<std::tuple<std::string, std::string, std::string>, unsigned long long> rule_calls;\n"
                            "    int iter = 0;")
        code = code.replace("            ++mxm_calls;",
                            "            ++mxm_calls;\n            ++rule_calls[{a, b, c}];")
        code = code.replace("    result.iterations   = iter;",
                            '    for (const auto& [rule, count] : rule_calls) {\n'
                            '        const auto& [a, b, c] = rule;\n'
                            '        std::cerr << "CFRA_RULE " << a << " " << b << " " << c << " " << count << "\\n";\n'
                            '    }\n    result.iterations   = iter;')
    query = "java_points_to.cnf"
    results = []
    with TemporaryDirectory() as scratch:
        work = Path(scratch)
        generated = work / source.name
        generated.write_text(code)
        flags = []
        for line in (BASE / "CMakeFiles/cfra.dir/flags.make").read_text().splitlines():
            if line.startswith(("CXX_DEFINES =", "CXX_INCLUDES =", "CXX_FLAGS =")):
                flags.extend(shlex.split(line.split("=", 1)[1]))
        obj, binary = work / "incremental.o", work / "cfra"
        compile_cmd = ["/usr/bin/g++-13", *flags, "-I" + str(source.parent),
                       "-c", str(generated), "-o", str(obj)]
        link = shlex.split((BASE / "CMakeFiles/cfra.dir/link.txt").read_text())
        link[link.index("-o") + 1] = str(binary)
        old_obj = "CMakeFiles/cfra.dir/src/incremental_algo/incremental_algo.cpp.o"
        link[link.index(old_obj)] = str(obj)
        for cmd in (compile_cmd, link):
            subprocess.run(cmd, cwd=BASE, timeout=120, check=True)
        graph, grammars = importer["prepare"](
            DATA / "6.0.0/graph/luindex.tar.gz", "luindex", {query}, work)
        digest = importer["sha256"]
        inputs = {"graph.txt": digest(graph), query: digest(grammars[query])}
        if inputs != json.loads((DATA / "cuda-baseline-resume/inputs-luindex.json").read_text()):
            raise ValueError("Input hashes differ from benchmark")
        (out / "manifest.json").write_text(json.dumps(dict(
            builds=builds, inputs=inputs, source_sha256=digest(source),
            binary_sha256=digest(binary), compile=compile_cmd, link=link), indent=2))
        for label, hashes in builds.items():
            library = ROOT / next(name for name in hashes if name.endswith("/libcubool.so"))
            env = dict(os.environ, LD_LIBRARY_PATH=str(library.parent))
            env.pop("LD_PRELOAD", None)
            deps = subprocess.check_output(["ldd", str(binary)], env=env, text=True)
            if not any(line.split()[:3] == ["libcubool.so", "=>", str(library)]
                       for line in deps.splitlines()):
                raise ValueError(f"Wrong loaded library for {label}")
            app = [str(binary), "--graph", str(graph), "--grammar", str(grammars[query]),
                   "--algo", "incremental"]
            for profiled in ((False,) if args.indexed_rules else (False, True)):
                name = label + ("-profile" if profiled else "-plain")
                prefix = out / name
                command = app
                if profiled:
                    command = ["nsys", "profile", "--trace=cuda", "--sample=none",
                               "--cpuctxsw=none", f"--output={prefix}", *app]
                print("START", name, flush=True)
                with prefix.with_suffix(".stdout").open("wb") as stdout, prefix.with_suffix(".stderr").open("wb") as stderr:
                    subprocess.run(command, env=env, stdout=stdout, stderr=stderr,
                                   timeout=1200, check=True)
                stderr_text = prefix.with_suffix(".stderr").read_text()
                match = re.search(r"CFRA_COUNTS iterations=(\d+) mxm=(\d+)", stderr_text)
                if not match or not re.search(r"^#SEdges:\s*9677\s*$", prefix.with_suffix(".stdout").read_text(), re.M):
                    raise ValueError(f"Unexpected result from {name}")
                row = dict(run=name, iterations=int(match[1]), mxm=int(match[2]), pairs=9677)
                if args.indexed_rules:
                    row["mxm_by_template"] = summarize_rules(stderr_text, grammars[query].read_text(), row["mxm"])
                if profiled:
                    database = prefix.with_suffix(".sqlite")
                    subprocess.run(["nsys", "export", "--type=sqlite", f"--output={database}",
                                    str(prefix.with_suffix(".nsys-rep"))], timeout=900, check=True)
                    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
                        row["count_kernels"] = db.execute("""
                            SELECT count(*) FROM CUPTI_ACTIVITY_KIND_KERNEL k
                            JOIN StringIds s ON s.id=k.demangledName
                            WHERE s.value LIKE '%kernel_call_impl%count_nz_functor%'
                        """).fetchone()[0]
                        row["d2h_4_bytes"] = db.execute("""
                            SELECT count(*) FROM CUPTI_ACTIVITY_KIND_MEMCPY WHERE copyKind=2 AND bytes=4
                        """).fetchone()[0]
                results.append(row)
                (out / "results.json").write_text(json.dumps(results, indent=2) + "\n")
                print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
