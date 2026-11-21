"""Export per-run metrics and matched algorithm comparisons from a FLPQ report."""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import re
from statistics import median


def write_csv(path, fields, rows):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def read_runs(directory):
    # An active runner may be appending the last row as we read the snapshot.
    content = (directory / "results.jsonl").read_bytes()
    for line in content.split(b"\n")[:-1]:
        row = json.loads(line)
        row["wall_seconds"] = row.pop("seconds")
        if row["stdout"]:
            stdout = (directory / row["stdout"]).read_text(errors="replace")
            analysis = re.search(r"^AnalysisTime: ([0-9.eE+-]+)$", stdout, re.MULTILINE)
            graph = re.search(r"^Graph: (\d+) vertices, (\d+) labels, (\d+) edges$",
                              stdout, re.MULTILINE)
            if analysis:
                row["analysis_seconds"] = float(analysis[1])
            if graph:
                row.update(zip(("vertices", "labels", "edges"), map(int, graph.groups())))
        yield row


def compare(runs):
    matched = defaultdict(dict)
    for run in runs:
        if run["status"] == "pass":
            matched[run["graph"], run["grammar"]][run["algo"]] = run
    for (graph, grammar), algorithms in sorted(matched.items()):
        base = algorithms.get("base")
        if not base:
            continue
        for algo in ("incremental", "lazy"):
            other = algorithms.get(algo)
            if not other:
                continue
            row = dict(graph=graph, grammar=grammar, algo=algo)
            for metric in ("wall_seconds", "analysis_seconds"):
                left, right = base.get(metric), other.get(metric)
                row[f"base_{metric}"] = left
                row[f"algo_{metric}"] = right
                row[f"base_over_algo_{metric}"] = left / right if left and right else None
            yield row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    runs = list(read_runs(args.report))
    comparisons = list(compare(runs))
    write_csv(args.report / "timings.csv",
              ("graph", "grammar", "algo", "status", "expected", "actual", "wall_seconds",
               "analysis_seconds", "vertices", "labels", "edges", "reason", "stdout", "stderr"),
              runs)
    write_csv(args.report / "comparisons.csv",
              ("graph", "grammar", "algo", "base_wall_seconds", "algo_wall_seconds",
               "base_over_algo_wall_seconds", "base_analysis_seconds", "algo_analysis_seconds",
               "base_over_algo_analysis_seconds"), comparisons)
    for algo in sorted({run["algo"] for run in runs}):
        statuses = Counter(run["status"] for run in runs if run["algo"] == algo)
        ratios = [row["base_over_algo_wall_seconds"] for row in comparisons
                  if row["algo"] == algo and row["base_over_algo_wall_seconds"] is not None]
        print(f"{algo}: {dict(statuses)}")
        if ratios:
            print(f"  Matched against base: {len(ratios)}, median wall ratio {median(ratios):.3f}x")


if __name__ == "__main__":
    main()
