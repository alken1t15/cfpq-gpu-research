"""Check indexed-format diagnostics without changing query semantics."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/2026-11-03-template-warning'
MARKER = 'no matching graph-label indices were found'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cases = [
        ('raw_indexed', '0 1 open_3\n1 2 close_3\n', 'S open_i close_i\n', True, 0),
        ('adapted_indexed', '0 1 open_i_3\n1 2 close_i_3\n', 'S open_i close_i\n', False, 1),
        ('non_indexed', '0 1 a\n', 'S a\n', False, 1),
        # Missing indexed edges can be intentional; preserve the epsilon answer.
        ('epsilon_no_indices', '0 1 a\n', 'S\nS open_i close_i\n', True, 2),
    ]
    results = []
    for name, edges, rules, warning, expected in cases:
        directory = OUT / name
        directory.mkdir(exist_ok=True)
        (directory / 'graph.txt').write_text(edges)
        (directory / 'grammar.cnf').write_text(rules + 'Count:\nS\n')
        for algo in ('base', 'incremental', 'lazy'):
            run = subprocess.run([str(ROOT / 'src/cfra/build-cpu-gcc13/cfra'),
                '--graph', str(directory / 'graph.txt'), '--grammar', str(directory / 'grammar.cnf'),
                '--algo', algo, '--cpu'], capture_output=True, text=True, timeout=15)
            passed = (run.returncode == 0 and (MARKER in run.stderr) == warning
                      and f'#SEdges: {expected}\n' in run.stdout and MARKER not in run.stdout)
            results.append(dict(case=name, algo=algo, passed=passed, expected_warning=warning,
                                expected_count=expected, exit_code=run.returncode,
                                stdout=run.stdout, stderr=run.stderr))
    (OUT / 'results.json').write_text(json.dumps(results, indent=2))
    print(f"{sum(r['passed'] for r in results)}/{len(results)} passed")
    return 0 if all(r['passed'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
