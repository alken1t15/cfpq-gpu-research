"""Profile a verified cuBool candidate on the benchmark luindex query."""
import argparse
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/flpq-all"
BINARY = ROOT / "build/gpu-mxm-alias/cfra"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count-host-bins", action="store_true")
    args = parser.parse_args()
    tag = "gpu-count-host-bins" if args.count_host_bins else "gpu-empty-fill-alias"
    out = DATA / ("gpu-count-host-bins-profile" if args.count_host_bins else "gpu-empty-fill-profile")
    library = ROOT / "build" / tag / "cuBool/cubool/libcubool.so"
    importer = runpy.run_path(str(ROOT / "scripts/check-gpu-flpq-data.py"))
    digest = importer["sha256"]
    manifest = json.loads((DATA / tag / "manifest.json").read_text())["builds"]
    importer["verify_build"]()
    for path, expected in {**manifest["baseline"], **manifest["trial"]}.items():
        if digest(ROOT / path) != expected:
            raise ValueError(f"Unexpected build artifact: {path}")
    env = dict(os.environ, LD_LIBRARY_PATH=str(library.parent))
    env.pop("LD_PRELOAD", None)
    dep = subprocess.check_output(["ldd", str(BINARY)], env=env, text=True)
    if not any(line.split()[:3] == ["libcubool.so", "=>", str(library)] for line in dep.splitlines()):
        raise ValueError(f"Unexpected dynamic library: {dep}")

    out.mkdir()
    query = "java_points_to.cnf"
    with TemporaryDirectory() as scratch:
        graph, grammars = importer["prepare"](DATA / "6.0.0/graph/luindex.tar.gz",
                                             "luindex", {query}, Path(scratch))
        grammar = grammars[query]
        hashes = {"graph.txt": digest(graph), query: digest(grammar)}
        reference = json.loads((DATA / "cuda-baseline-resume/inputs-luindex.json").read_text())
        if hashes != reference:
            raise ValueError("Unexpected luindex input hashes")
        command = ["nsys", "profile", "--trace=cuda", "--sample=none", "--cpuctxsw=none",
                   f"--output={out / 'luindex'}", str(BINARY), "--graph", str(graph),
                   "--grammar", str(grammar), "--algo", "incremental"]
        (out / "manifest.json").write_text(json.dumps(
            dict(command=command, inputs=hashes, builds=manifest,
                 nsys=subprocess.check_output(["nsys", "--version"], text=True).strip()), indent=2))
        print("START full luindex CUDA profile", flush=True)
        with (out / "luindex.stdout").open("wb") as stdout, (out / "luindex.stderr").open("wb") as stderr:
            subprocess.run(command, env=env, stdout=stdout, stderr=stderr, timeout=1200, check=True)
    if not re.search(r"^#SEdges:\s*9677\s*$", (out / "luindex.stdout").read_text(), re.MULTILINE):
        raise RuntimeError("The profiled run did not return 9677 pairs")
    print("PASS luindex: 9677 pairs; exporting CUDA statistics", flush=True)
    with (out / "luindex-stats.csv").open("wb") as stdout, (out / "luindex-stats.stderr").open("wb") as stderr:
        subprocess.run(["nsys", "stats", "--report=cuda_api_sum,cuda_gpu_kern_sum,cuda_gpu_mem_time_sum",
                        "--format=csv", str(out / "luindex.nsys-rep")],
                       stdout=stdout, stderr=stderr, timeout=600, check=True)
    print("Profile and statistics complete", flush=True)


if __name__ == "__main__":
    main()
