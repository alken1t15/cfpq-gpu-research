"""Compare the recorded upstream parser and current parser on luindex."""
import hashlib
import json
import re
import subprocess
import tarfile
import time
import urllib.request
import csv
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/cfra'
DATA = ROOT / 'data/catalog-v6/luindex'
OUT = ROOT / 'experiments/2026-11-03-java'
SHA = '3bc9794a509ca2f40c82b04e6c31e21ef9d1dbf1'
URL = 'https://cfpq-data.storage.yandexcloud.net/6.0.0/graph/luindex.tar.gz'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    archive = urllib.request.urlopen(URL, timeout=30).read()
    (DATA / 'luindex.tar.gz').write_bytes(archive)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        files = {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}
    graph_raw, graph_adapted = [], []
    vertices, sizes, mapping = set(), set(), {}
    for path, content in sorted(files.items()):
        if '/graph/' not in path or not path.endswith('.mtx'):
            continue
        lines = [line.split() for line in content.decode().splitlines() if line and not line.startswith('%')]
        rows, cols, count = map(int, lines[0])
        assert rows == cols and count == len(lines) - 1
        sizes.add(rows)
        label = Path(path).stem
        indexed = re.fullmatch(r'(load|store)_(\d+)', label)
        forward = f'{indexed[1]}_i_{indexed[2]}' if indexed else label
        reverse = f'{indexed[1]}_r_i_{indexed[2]}' if indexed else label + '_r'
        mapping[label], mapping[label + '_r'] = forward, reverse
        for line in lines[1:]:
            u, v = map(int, line[:2])
            assert 0 <= u < rows and 0 <= v < cols
            vertices.update((u, v))
            graph_raw.extend([(u, v, label), (v, u, label + '_r')])
            graph_adapted.extend([(u, v, forward), (v, u, reverse)])
    assert len(sizes) == 1 and vertices == set(range(next(iter(sizes))))
    assert len(set(mapping.values())) == len(mapping)
    inputs = {}
    for name, edges in [('raw', graph_raw), ('adapted', graph_adapted)]:
        path = DATA / f'cfra-{name}.txt'
        path.write_text(''.join(f'{u} {v} {label}\n' for u, v, label in edges))
        inputs[name] = path
    grammar_bytes = files['luindex/queries/cfpq/java_points_to/java_points_to.cnf']
    grammar = DATA / 'java_points_to.cnf'
    grammar.write_bytes(grammar_bytes)
    # Keep a genuine baseline binary without replacing the current source tree.
    # Only grammar.cpp differs in production sources; compile its recorded version
    # with all other unchanged .cpp files and the same, unchanged cuBool library.
    original = subprocess.check_output(['git', '-C', str(SOURCE), 'show', f'{SHA}:src/grammar/grammar.cpp'])
    (OUT / 'upstream-grammar.cpp').write_bytes(original)
    library = SOURCE / 'build-cpu-gcc13/cuBool/cubool'
    before = OUT / 'cfra-upstream'
    cpp = [str(p) for p in sorted((SOURCE / 'src').rglob('*.cpp')) if p.name != 'grammar.cpp']
    for path in (SOURCE / 'src').rglob('*'):
        if not path.is_file() or path.name == 'grammar.cpp':
            continue
        recorded = subprocess.check_output(['git', '-C', str(SOURCE), 'show',
                                           f'{SHA}:{path.relative_to(SOURCE).as_posix()}'])
        # Windows checkout may use CRLF; compare logical source bytes.
        assert path.read_bytes().replace(b'\r\n', b'\n') == recorded.replace(b'\r\n', b'\n')
    command = ['g++-13', '-std=gnu++20', '-O3', '-DNDEBUG',
               '-I' + str(SOURCE / 'cuBool/cubool/include'), '-I' + str(SOURCE / 'src'),
               '-I' + str(SOURCE / 'src/grammar'), '-I' + str(SOURCE / 'src/graph'),
               '-I' + str(SOURCE / 'src/matrix_store'), str(OUT / 'upstream-grammar.cpp'),
               *cpp, '-L' + str(library), '-Wl,-rpath,' + str(library), '-lcubool', '-o', str(before)]
    (OUT / 'compile-command.json').write_text(json.dumps(command, indent=2))
    subprocess.run(command, check=True)
    reference_url = 'https://cfpq-data.storage.yandexcloud.net/6.0.0/reachable_pairs.csv'
    reference = urllib.request.urlopen(reference_url, timeout=30).read()
    (OUT / 'reachable_pairs.csv').write_bytes(reference)
    expected = next(int(r['num_reachable_pairs']) for r in csv.DictReader(io.StringIO(reference.decode()))
                    if r['graph'] == 'luindex' and r['grammar'] == grammar.name)
    result_lines = [s for s in files['luindex/queries/cfpq/java_points_to/results.mtx'].decode().splitlines()
                    if s and not s.startswith('%')]
    assert int(result_lines[0].split()[2]) == len(result_lines) - 1 == expected
    manifest = {'upstream_sha': SHA, 'url': URL, 'archive_sha256': sha(archive),
                'grammar_sha256': sha(grammar_bytes), 'vertices': len(vertices),
                'edges_with_reverse': len(graph_raw), 'label_mapping': mapping,
                'reference_url': reference_url, 'reference_sha256': sha(reference), 'expected': expected,
                'upstream_binary_sha256': sha(before.read_bytes()),
                'fixed_binary_sha256': sha((SOURCE / 'build-cpu-gcc13/cfra').read_bytes()),
                'input_sha256': {k: sha(p.read_bytes()) for k, p in inputs.items()}}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    results = []
    binaries = {'upstream': before, 'fixed': SOURCE / 'build-cpu-gcc13/cfra'}
    for format_name, graph in inputs.items():
        for version, binary in binaries.items():
            for algo in ('base', 'incremental', 'lazy'):
                cmd = [str(binary), '--graph', str(graph), '--grammar', str(grammar), '--algo', algo, '--cpu']
                start = time.monotonic()
                try:
                    run = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                    match = re.search(r'#SEdges:\s*(\d+)', run.stdout)
                    record = {'exit_code': run.returncode, 'actual': int(match[1]) if match else None,
                              'stdout': run.stdout, 'stderr': run.stderr}
                except subprocess.TimeoutExpired:
                    record = {'status': 'timeout', 'actual': None}
                record.update(format=format_name, version=version, algo=algo, expected=expected,
                              wall_seconds=time.monotonic()-start)
                results.append(record)
                (OUT / 'results.json').write_text(json.dumps(results, indent=2))
                print(format_name, version, algo, record['actual'], 'expected', expected, flush=True)
    # The raw-label runs deliberately probe unsupported naming; acceptance is
    # correctness of the fixed parser on the explicitly adapted CFRA format.
    return 0 if all(r['actual'] == expected and r.get('exit_code') == 0
                    for r in results if r['format'] == 'adapted' and r['version'] == 'fixed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
