"""Compare completed end-to-end repetitions of CFG_bench and CFRA."""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
from statistics import mean, median, stdev


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cfg-results", type=Path, required=True)
    parser.add_argument("--cfra-summary", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    measured = defaultdict(list)
    checks = {}
    for line in args.cfg_results.read_bytes().split(b"\n")[:-1]:
        row = json.loads(line)
        if row["phase"] == "measure":
            measured[row["graph"]].append(row)
        elif row["phase"] == "check":
            checks[row["graph"]] = row

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.cfra_summary.open(newline="", encoding="utf-8-sig") as source, args.out.open(
        "w", newline="", encoding="utf-8-sig"
    ) as target:
        writer = csv.writer(target)
        writer.writerow(("graph", "grammar", "cfra_mode", "expected_pairs", "cfg_check",
                         "cfg_completed", "cfg_passed", "cfg_other_statuses",
                         "cfg_median_seconds", "cfg_mean_seconds", "cfg_sample_sd_seconds",
                         "cfra_median_seconds", "cfg_over_cfra"))
        for row in csv.DictReader(source):
            graph = row["graph"]
            runs = measured[graph]
            expected = int(row["expected_pairs"])
            check = checks.get(graph, {})
            if any(r["expected_pairs"] != expected for r in runs) or check.get("expected_pairs", expected) != expected:
                raise ValueError(f"Expected counts differ on {graph}")
            times = [r["wall_seconds"] for r in runs if r["status"] == "pass"]
            statuses = Counter(r["status"] for r in runs if r["status"] != "pass")
            cfg_stats = (median(times), mean(times), stdev(times)) if len(times) == len(runs) == 5 else ("", "", "")
            cfra = row["median_seconds"] if row["passed"] == row["completed"] == "5" else ""
            ratio = cfg_stats[0] / float(cfra) if cfra and cfg_stats[0] != "" else ""
            writer.writerow((graph, row["grammar"], row["algo"], expected, check.get("status", ""),
                             len(runs), len(times), dict(statuses) if statuses else "",
                             *cfg_stats, cfra, ratio))


if __name__ == "__main__":
    main()
