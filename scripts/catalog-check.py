"""Prepare and check two small FLPQ_Data v6 archives (run inside WSL)."""
import csv
import hashlib
import io
import json
import re
import subprocess
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/2026-11-03-catalog'
DATA = ROOT / 'data/catalog-v6'
BASE = 'https://cfpq-data.storage.yandexcloud.net/6.0.0/'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def matrix(data):
    lines = [line.split() for line in data.decode().splitlines() if line and not line.startswith('%')]
    rows, cols, count = map(int, lines[0])
    pairs = [tuple(map(int, line[:2])) for line in lines[1:]]
    assert len(pairs) == count
    assert all(0 <= u < rows and 0 <= v < cols for u, v in pairs)
    return rows, pairs


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    reference = urllib.request.urlopen(BASE + 'reachable_pairs.csv', timeout=30).read()
    (OUT / 'reachable_pairs.csv').write_bytes(reference)
    counts = {(r['graph'], r['grammar']): int(r['num_reachable_pairs']) for r in
              csv.DictReader(io.StringIO(reference.decode())) if r['num_reachable_pairs']}
    manifest, results = [], []
    for name in ('atom', 'bzip'):
        url = BASE + f'graph/{name}.tar.gz'
        archive = urllib.request.urlopen(url, timeout=30).read()
        directory = DATA / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f'{name}.tar.gz').write_bytes(archive)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            files = {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}
        edges, dimensions = [], set()
        for path, content in sorted(files.items()):
            if '/graph/' not in path or not path.endswith('.mtx'):
                continue
            n, pairs = matrix(content)
            dimensions.add(n)
            label = Path(path).stem
            edges.extend((u, v, label) for u, v in pairs)
            edges.extend((v, u, label + '_r') for u, v in pairs)
        assert len(dimensions) == 1
        n = dimensions.pop()
        # CFRA cannot receive an explicit dimension; avoid silently dropping vertices.
        assert {v for u, w, _ in edges for v in (u, w)} == set(range(n))
        graph = directory / 'cfra-graph.txt'
        graph.write_text(''.join(f'{u} {v} {label}\n' for u, v, label in edges))
        manifest.append({'graph': name, 'url': url, 'archive_sha256': digest(archive),
                         'graph_sha256': digest(graph.read_bytes()), 'vertices': n,
                         'edges_with_reverse': len(edges), 'conversion': 'zero-based; add transpose with _r suffix'})
        for path, content in sorted(files.items()):
            if not path.endswith('.cnf') or (name, Path(path).name) not in counts:
                continue
            grammar = directory / Path(path).name
            grammar.write_bytes(content)
            _, expected_pairs = matrix(files[str(Path(path).parent / 'results.mtx')])
            expected = counts[name, grammar.name]
            assert len(expected_pairs) == expected
            for algo in ('base', 'incremental', 'lazy'):
                command = [str(ROOT / 'src/cfra/build-cpu-gcc13/cfra'), '--graph', str(graph),
                           '--grammar', str(grammar), '--algo', algo, '--cpu']
                run = subprocess.run(command, capture_output=True, text=True, timeout=60)
                match = re.search(r'#SEdges:\s*(\d+)', run.stdout)
                actual = int(match.group(1)) if match else None
                results.append({'graph': name, 'grammar': grammar.name, 'grammar_sha256': digest(content),
                                'algo': algo, 'expected': expected, 'actual': actual,
                                'exit_code': run.returncode, 'stdout': run.stdout, 'stderr': run.stderr,
                                'passed': run.returncode == 0 and actual == expected})
    (OUT / 'manifest.json').write_text(json.dumps({'reference_url': BASE + 'reachable_pairs.csv',
        'reference_sha256': digest(reference), 'inputs': manifest}, indent=2))
    (OUT / 'results.json').write_text(json.dumps(results, indent=2))
    for row in results:
        print(row['graph'], row['grammar'], row['algo'], row['expected'], row['actual'], row['passed'])
    return 0 if all(row['passed'] for row in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
