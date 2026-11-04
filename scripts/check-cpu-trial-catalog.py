"""Cross-check baseline and CPU trial on several external graph families."""
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/2026-11-03-trial-catalog'
BASE = 'https://cfpq-data.storage.yandexcloud.net/6.0.0/'
CASES = [('atom', 'nested_parentheses_subClassOf_type.cnf'), ('bzip', 'c_alias.cnf'),
         ('pizza', 'nested_parentheses_subClassOf_type.cnf'), ('gzip', 'c_alias.cnf'),
         ('luindex', 'java_points_to.cnf'), ('gson', 'java_points_to.cnf')]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    reference = urllib.request.urlopen(BASE + 'reachable_pairs.csv', timeout=30).read()
    (OUT / 'reachable_pairs.csv').write_bytes(reference)
    counts = {(r['graph'], r['grammar']): int(r['num_reachable_pairs']) for r in
              csv.DictReader(io.StringIO(reference.decode())) if r['num_reachable_pairs']}
    results, inputs = [], []
    binary = ROOT / 'src/cfra/build-cpu-gcc13/cfra'
    libraries = {'baseline': ROOT / 'src/cfra/build-cpu-gcc13/cuBool/cubool',
                 'fast_path': ROOT / 'build/cpu-empty-union-trial'}
    for name, grammar_name in CASES:
        directory = ROOT / 'data/trial-catalog' / name
        directory.mkdir(parents=True, exist_ok=True)
        url = BASE + f'graph/{name}.tar.gz'
        archive = urllib.request.urlopen(url, timeout=30).read()
        (directory / f'{name}.tar.gz').write_bytes(archive)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            files = {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}
        edges, vertices, dimensions, mapping = [], set(), set(), {}
        for path, content in sorted(files.items()):
            if '/graph/' not in path or not path.endswith('.mtx'):
                continue
            lines = [s.split() for s in content.decode().splitlines() if s and not s.startswith('%')]
            n, cols, count = map(int, lines[0])
            assert n == cols and count == len(lines) - 1
            dimensions.add(n)
            label = Path(path).stem
            indexed = re.fullmatch(r'(load|store)_(\d+)', label) if name in ('luindex', 'gson') else None
            forward = f'{indexed[1]}_i_{indexed[2]}' if indexed else label
            reverse = f'{indexed[1]}_r_i_{indexed[2]}' if indexed else label + '_r'
            mapping[label], mapping[label + '_r'] = forward, reverse
            for line in lines[1:]:
                u, v = map(int, line[:2])
                assert 0 <= u < n and 0 <= v < n
                vertices.update((u, v))
                edges.extend([(u, v, forward), (v, u, reverse)])
        assert len(dimensions) == 1
        n = next(iter(dimensions))
        assert vertices == set(range(n)), (name, 'Cannot represent isolated vertices safely')
        assert len(set(mapping.values())) == len(mapping)
        graph, grammar = directory / 'cfra-graph.txt', directory / grammar_name
        graph.write_text(''.join(f'{u} {v} {label}\n' for u, v, label in edges))
        grammar_path = next(p for p in files if Path(p).name == grammar_name)
        grammar.write_bytes(files[grammar_path])
        expected = counts[name, grammar_name]
        inputs.append(dict(graph=name, url=url, archive_sha256=digest(archive), vertices=n,
                           edges=len(edges), graph_sha256=digest(graph.read_bytes()),
                           grammar=grammar_name, grammar_sha256=digest(grammar.read_bytes()),
                           expected=expected, label_mapping=mapping))
        (OUT / 'inputs.json').write_text(json.dumps(inputs, indent=2))
        for algo in ('base', 'incremental', 'lazy'):
            for variant, library in libraries.items():
                command = [str(binary), '--graph', str(graph), '--grammar', str(grammar), '--algo', algo, '--cpu']
                try:
                    run = subprocess.run(command, env=dict(os.environ, LD_LIBRARY_PATH=str(library)),
                                         capture_output=True, text=True, timeout=120)
                    match = re.search(r'#SEdges:\s*(\d+)', run.stdout)
                    row = dict(actual=int(match[1]) if match else None, exit_code=run.returncode,
                               stdout=run.stdout, stderr=run.stderr)
                except subprocess.TimeoutExpired:
                    row = dict(actual=None, status='timeout')
                row.update(graph=name, algo=algo, variant=variant, expected=expected)
                row['passed'] = row['actual'] == expected and row.get('exit_code') == 0
                results.append(row)
                (OUT / 'results.json').write_text(json.dumps(results, indent=2))
                print(name, algo, variant, row['actual'], expected, row['passed'], flush=True)
    (OUT / 'manifest.json').write_text(json.dumps(dict(binary_sha256=digest(binary.read_bytes()),
        library_sha256={k: digest((p / 'libcubool.so').read_bytes()) for k, p in libraries.items()},
        reference_sha256=digest(reference), timeout_seconds=120), indent=2))
    return 0 if all(r['passed'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
