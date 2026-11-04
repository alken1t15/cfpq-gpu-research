"""Independent set-based oracle for the two upstream smoke-test grammars."""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/cfra"
BINARY = SOURCE / "build-cpu-gcc13/cfra"


def oracle(case):
    edges = [line.split() for line in (SOURCE / f"test_data/{case}/graph.txt").read_text().splitlines() if line.strip()]
    labels = {}
    vertices = set()
    for source, target, label in edges:
        source, target = int(source), int(target)
        vertices.update((source, target))
        labels.setdefault(label, set()).add((source, target))
    # Explicit grammars, independent of CFRA's grammar parser.
    if case == "an_bn":
        relations = {"a": labels["a"], "b": labels["b"], "S": set(), "Sb": set()}
        rules = [("Sb", "S", "b"), ("S", "a", "Sb"), ("S", "a", "b")]
        start = "S"
    else:
        relations = {"A": labels["A"] | {(v, v) for v in vertices}}
        rules = [("A", "A", "A")]
        start = "A"
    while True:
        before = sum(map(len, relations.values()))
        for head, left, right in rules:
            additions = {(u, w) for u, v in relations[left] for x, w in relations[right] if v == x}
            relations[head].update(additions)
        if sum(map(len, relations.values())) == before:
            return sorted(relations[start])


def main():
    results = []
    for case in ("an_bn", "transitive_loop"):
        pairs = oracle(case)
        for algorithm in ("base", "incremental", "lazy"):
            command = [str(BINARY), "--graph", str(SOURCE / f"test_data/{case}/graph.txt"),
                       "--grammar", str(SOURCE / f"test_data/{case}/grammar.cnf"),
                       "--algo", algorithm, "--cpu"]
            run = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
            actual = int(re.search(r"#SEdges:\s*(\d+)", run.stdout).group(1))
            results.append({"case": case, "algorithm": algorithm, "expected_count": len(pairs),
                            "actual_count": actual, "oracle_pairs": pairs, "stdout": run.stdout,
                            "stderr": run.stderr, "passed": actual == len(pairs)})
    print(json.dumps(results, indent=2))
    return 0 if all(item["passed"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
