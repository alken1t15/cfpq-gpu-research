from pathlib import Path
from statistics import median
import csv
import json
import sys

out = Path(sys.argv[1])
cases = Path("experiments/2026-11-27-flpq-expanded/cases.csv")
cpu_rows = [json.loads(line) for line in (out/"cpu/results.jsonl").read_text().splitlines()]
inputs = json.loads((out/"cpu/manifest.json").read_text())["inputs"]
fields = ["graph", "grammar", "expected_pairs", "cpu_passes", "gpu_passes",
          "cpu_median_s", "gpu_median_s", "cpu_over_gpu", "cpu_status", "gpu_status"]
with cases.open(newline="", encoding="utf-8-sig") as source, (out/"comparison.csv").open("w", newline="") as target:
    writer = csv.DictWriter(target, fieldnames=fields)
    writer.writeheader()
    for case in csv.DictReader(source):
        graph, grammar = case["graph"], case["grammar"]
        folder = out/f"gpu-{graph}"
        cpu = [r for r in cpu_rows if r["graph"] == graph]
        manifest = folder/"manifest.json"
        result = folder/"results.json"
        row = dict(case, cpu_status=", ".join(sorted({r["status"] for r in cpu})))
        cpu_pass = [r["wall_seconds"] for r in cpu if r["phase"] == "measure" and r["status"] == "pass"]
        expected = int(next(csv.reader((out/"inputs"/graph/"case.csv").read_text().splitlines()))[2])
        row.update(expected_pairs=expected, cpu_passes=len(cpu_pass), gpu_passes=0, gpu_status="missing")
        if len(cpu_pass) == 5:
            row["cpu_median_s"] = median(cpu_pass)
        if manifest.is_file() and result.is_file():
            gpu_input = json.loads(manifest.read_text())
            matched = gpu_input["inputs"] == {"graph.txt": inputs[graph]["cfra_graph"],
                                               grammar: inputs[graph]["grammar"]}
            matched &= gpu_input["expected_pairs"] == expected
            samples = json.loads(result.read_text())
            gpu_pass = [r["wall_seconds"] for r in samples if r["phase"].startswith("pair-")
                        and r["build"] == "trial" and r["pairs"] == expected and r["exit_code"] == 0]
            row.update(gpu_passes=len(gpu_pass), gpu_status="input mismatch" if not matched
                       else "pass" if len(gpu_pass) == 5 and (folder/"summary.json").is_file() else "incomplete")
            if row["gpu_status"] == "pass":
                row["gpu_median_s"] = median(gpu_pass)
                if len(cpu_pass) == 5:
                    row["cpu_over_gpu"] = row["cpu_median_s"]/row["gpu_median_s"]
        writer.writerow(row)
