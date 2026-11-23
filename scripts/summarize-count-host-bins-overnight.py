"""Summarize a completed overnight CUDA validation and diagnostic queue."""
import argparse
from collections import Counter
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report = args.report
    data = report.parent
    lines = ["# Overnight CUDA results", ""]
    exit_file = report / "exit-code"
    lines.append(f"Queue exit code: {exit_file.read_text().strip() if exit_file.exists() else 'missing'}")
    stages = report / "status.tsv"
    if stages.exists():
        lines.extend(stages.read_text().splitlines())
    catalog = report / "catalog/results.jsonl"
    if catalog.exists():
        rows = [json.loads(line) for line in catalog.read_text().splitlines()]
        lines.extend(["", f"Catalog: {len(rows)}/21 recorded, {dict(Counter(r['status'] for r in rows))}."])
        for row in rows:
            if row["status"] != "pass":
                lines.append(f"- {row['graph']} / {row['algo']}: {row['status']}: {row['reason']}")
        matched = 0
        for path in catalog.parent.glob("inputs-*.json"):
            reference = next((data / directory / path.name
                              for directory in ("cuda-baseline", "cuda-baseline-resume")
                              if (data / directory / path.name).exists()), None)
            if reference and json.loads(reference.read_text()) == json.loads(path.read_text()):
                matched += 1
            else:
                lines.append(f"- Input hashes missing or different: {path.name}")
        lines.append(f"Matched input manifests: {matched}/7.")
    diagnostics = report / "diagnostics/results.json"
    if diagnostics.exists():
        runs = {r["run"]: r for r in json.loads(diagnostics.read_text())}
        lines.extend(["", "| Run | Iterations | CFRA MxM | Pairs | Count kernels | 4-byte D2H |",
                      "|---|---:|---:|---:|---:|---:|"])
        for name, row in runs.items():
            fields = ("iterations", "mxm", "pairs", "count_kernels", "d2h_4_bytes")
            lines.append("| " + " | ".join([name, *(str(row.get(key, "")) for key in fields)]) + " |")
        for mode in ("plain", "profile"):
            baseline, trial = (runs.get(f"{label}-{mode}") for label in ("baseline", "trial"))
            if baseline and trial:
                same = all(baseline[key] == trial[key] for key in ("iterations", "mxm"))
                lines.append(f"\nCFRA iteration and MxM totals match between libraries ({mode}): {same}.")
                if mode == "profile" and same and baseline["count_kernels"] != trial["count_kernels"]:
                    lines.append("Inspect kernel coverage and library execution separately. CFRA issued the same number of MxM calls.")
    else:
        lines.extend(["", "Diagnostic results unavailable. See diagnostics.log."])
    (report / "morning-summary.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
