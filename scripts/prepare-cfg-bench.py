"""Prepare CFG_bench inputs from the same FLPQ archives as the CFRA benchmark."""
import argparse
import csv
import json
from pathlib import Path
import re
import runpy
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/flpq-all/6.0.0"
CASES = ROOT / "experiments/2026-11-21-flpq-gpu-suite/benchmark-cases.csv"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--case-list", type=Path, default=CASES)
    args = parser.parse_args()
    out = args.out.resolve()
    importer = runpy.run_path(str(ROOT / "scripts/check-gpu-flpq-data.py"))
    with (DATA / "reachable_pairs.csv").open(newline="", encoding="utf-8-sig") as catalog:
        cases = {}
        for row in csv.DictReader(catalog):
            if row["query_class"] == "cfpq":
                cases.setdefault(row["graph"], {})[row["grammar"]] = row["num_reachable_pairs"]
    with args.case_list.open(newline="", encoding="utf-8-sig") as selection:
        selected = list(csv.DictReader(selection))
    out.mkdir(parents=True)
    configs = []
    manifest = {}
    for case in selected:
        graph, grammar = case["graph"], case["grammar"]
        folder = out / graph
        folder.mkdir()
        with TemporaryDirectory() as scratch:
            original, grammars = importer["prepare"](DATA / "graph" / f"{graph}.tar.gz",
                                                     graph, cases[graph], Path(scratch))
            source_grammar = grammars[grammar]
            target_grammar = folder / grammar
            target_grammar.write_bytes(source_grammar.read_bytes())
            graph_path = folder / f"{graph}.g"
            templates = set(source_grammar.read_text().split())
            indexed = re.compile(r"(.+_i)_(0|[1-9][0-9]*)")
            with original.open() as edges, graph_path.open("w") as converted:
                for line in edges:
                    src, dst, label = line.split()
                    match = indexed.fullmatch(label)
                    if match and match[1] in templates:
                        label = f"{match[1]}\t{match[2]}"
                    converted.write(f"{src}\t{dst}\t{label}\n")
            digest = importer["sha256"]
            manifest[graph] = dict(cfra_graph=digest(original), cfg_bench_graph=digest(graph_path),
                                   grammar=digest(target_grammar))
        expected = cases[graph][grammar]
        if not expected.strip():
            raise ValueError(f"Missing expected pair count: {graph}/{grammar}")
        row = [str(graph_path), str(target_grammar), expected]
        if any("," in field for field in row):
            raise ValueError("CFG_bench configuration fields cannot contain commas")
        configs.append(row)
        (folder / "case.csv").write_text(",".join(row) + "\n")
        print(f"{graph}/{grammar}: {expected} expected pairs", flush=True)
    (out / "cases.csv").write_text("".join(",".join(row) + "\n" for row in configs))
    (out / "inputs.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
