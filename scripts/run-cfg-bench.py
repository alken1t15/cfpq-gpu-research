"""Check and time the optimized CFL_adv solver using one process per repetition."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
from statistics import mean, median, stdev
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    repo = args.repo.resolve()
    cases = sorted(args.inputs.resolve().glob("*/case.csv"))
    if not cases or not (repo / "build/cfg_bench").is_file():
        parser.error("Prepared cases and a built CFG_bench binary are required")
    args.out.mkdir(parents=True)
    binary = repo / "build/cfg_bench"
    manifest = {
        "cfg_bench_sha": subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "libraries": subprocess.check_output(["ldd", str(binary)], text=True),
        "inputs": json.loads((args.inputs / "inputs.json").read_text()),
        "timeout_seconds": args.timeout, "algorithms": ["CFL_adv"], "flags": ["-t", "-efbl"],
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    failure = False
    with (args.out / "results.jsonl").open("w", buffering=1) as results:
        for case in cases:
            with case.open(newline="") as config:
                expected = int(next(csv.reader(config))[2])
            passed_check = False
            samples = []
            for index, phase in enumerate(("check", "warmup", *("measure",) * 5)):
                if index and not passed_check:
                    break
                graph = case.parent.name
                command = [str(binary), "-t", "-a", "CFL_adv", "-efbl", "-c", str(case)]
                print(f"START {graph} {phase} {index}", flush=True)
                stem = args.out / f"{graph}-{index}"
                stdout_path, stderr_path = stem.with_suffix(".stdout"), stem.with_suffix(".stderr")
                start = time.monotonic()
                returncode = None
                with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                    try:
                        returncode = subprocess.run(command, cwd=repo, stdout=stdout, stderr=stderr,
                                                    timeout=args.timeout).returncode
                    except subprocess.TimeoutExpired:
                        pass
                seconds = time.monotonic() - start
                output = re.sub(r"\x1b\[[0-9;]*m", "", stdout_path.read_text(errors="replace"))
                match = re.search(r"Result:\s*(\d+) \(Return code: (-?\d+)\) \[([^]]+)\].*?\(([0-9.]+) sec\)", output)
                if returncode is None:
                    status = "timeout"
                elif match and returncode == 0 and match[2] == "0" and match[3] == "OK" and int(match[1]) == expected:
                    status = "pass"
                elif match and match[3] == "Wrong":
                    status = "mismatch"
                else:
                    status = "execution_error"
                row = dict(graph=graph, phase=phase, repeat=index-1 if phase == "measure" else None,
                           command=command, status=status, exit_code=returncode, wall_seconds=seconds,
                           expected_pairs=expected, actual_pairs=int(match[1]) if match else None,
                           analysis_seconds=float(match[4]) if match else None,
                           stdout=stdout_path.name, stderr=stderr_path.name)
                print(json.dumps(row), file=results)
                print(f"{status.upper()} {graph} {phase} {seconds:.3f}s", flush=True)
                failure |= status != "pass"
                if phase == "check":
                    passed_check = status == "pass"
                if phase == "measure" and status == "pass":
                    samples.append(seconds)
            if len(samples) == 5:
                print(f"TIMING {graph}: median={median(samples):.6f}s mean={mean(samples):.6f}s "
                      f"sample_sd={stdev(samples):.6f}s", flush=True)
    return int(failure)


if __name__ == "__main__":
    raise SystemExit(main())
