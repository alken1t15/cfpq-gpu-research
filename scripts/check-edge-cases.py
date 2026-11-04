"""Small declared-language checks; grammar semantics are explicit per fixture."""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/2026-11-03-edge-cases'
CASES = [
    ('chain', '0 1 a\n1 2 a\n', 'S A\nA a\n', [(0, 1), (1, 2)]),
    ('epsilon_chain', '0 1 a\n', 'S A\nA\n', [(0, 0), (1, 1)]),
    ('epsilon_product', '0 1 a\n', 'S A B\nA\nB a\n', [(0, 1)]),
    ('duplicates_loop', '0 0 a\n0 0 a\n0 1 a\n', 'S a\nS S S\n', [(0, 0), (0, 1)]),
    ('absent_terminal', '0 1 a\n', 'S b\n', []),
    # Same indexed language spelled explicitly and with README template syntax.
    ('indexed_explicit', '0 1 open_i_3\n1 2 close_i_3\n',
     'S open_i_3 close_i_3\n', [(0, 2)]),
    ('indexed_template', '0 1 open_i_3\n1 2 close_i_3\n',
     'S open_i close_i\n', [(0, 2)]),
    ('indexed_two_values', '0 1 open_i_3\n1 2 close_i_3\n2 3 open_i_7\n3 4 close_i_7\n',
     'S open_i close_i\n', [(0, 2), (2, 4)]),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for name, edges, rules, pairs in CASES:
        directory = OUT / name
        directory.mkdir(exist_ok=True)
        graph, grammar = directory / 'graph.txt', directory / 'grammar.cnf'
        graph.write_text(edges)
        grammar.write_text(rules + 'Count:\nS\n')
        for algo in ('base', 'incremental', 'lazy'):
            run = subprocess.run([str(ROOT / 'src/cfra/build-cpu-gcc13/cfra'),
                '--graph', str(graph), '--grammar', str(grammar), '--algo', algo, '--cpu'],
                capture_output=True, text=True, timeout=15)
            match = re.search(r'#SEdges:\s*(\d+)', run.stdout)
            actual = int(match.group(1)) if match else None
            results.append({'case': name, 'algo': algo, 'expected_pairs': pairs,
                'expected_count': len(pairs), 'actual': actual, 'exit_code': run.returncode,
                'passed': run.returncode == 0 and actual == len(pairs),
                'stdout': run.stdout, 'stderr': run.stderr})
            print(name, algo, len(pairs), actual, results[-1]['passed'])
    (OUT / 'results.json').write_text(json.dumps(results, indent=2))
    return 0 if all(r['passed'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
