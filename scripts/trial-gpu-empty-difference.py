"""Isolated correction of CUDA A\empty semantics; keep baseline untouched."""
import difflib
import hashlib
import json
import os
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'src/cfra/build-gpu-cuda124/cuBool/cubool'
SOURCE = ROOT / 'src/cfra/cuBool/cubool/sources/cuda/cuda_matrix_ewisemult_inverted.cu'
OUT = ROOT / 'experiments/2026-11-03-gpu-difference'
BUILD = ROOT / 'build/gpu-empty-difference'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    original = SOURCE.read_text()
    old = '''        if (a->isMatrixEmpty() || b->isMatrixEmpty()) {
            this->clearAndResizeStorageToDim();
            return;
        }'''
    new = '''        if (a->isMatrixEmpty()) {
            this->clearAndResizeStorageToDim();
            return;
        }
        if (b->isMatrixEmpty()) {
            if (this != a) this->clone(aBase);
            return;
        }'''
    assert original.count(old) == 1
    changed = original.replace(old, new)
    generated = OUT / SOURCE.name
    generated.write_text(changed)
    relative = 'cubool/sources/cuda/' + SOURCE.name
    (OUT / 'cubool-empty-difference.patch').write_text(''.join(difflib.unified_diff(
        original.splitlines(True), changed.splitlines(True), fromfile='a/' + relative, tofile='b/' + relative)))
    flags = []
    for line in (LIB / 'CMakeFiles/cubool.dir/flags.make').read_text().splitlines():
        if line.startswith(('CUDA_DEFINES =', 'CUDA_INCLUDES =', 'CUDA_FLAGS =')):
            flags += shlex.split(line.split('=', 1)[1])
    obj = BUILD / 'difference.cu.o'
    commands = [['/usr/local/cuda-12.4/bin/nvcc', '-ccbin=/usr/bin/g++-11', *flags,
                 '-c', str(generated), '-o', str(obj)]]
    link = shlex.split((LIB / 'CMakeFiles/cubool.dir/link.txt').read_text())
    link[link.index('-o') + 1] = str(BUILD / 'libcubool.so')
    for i, token in enumerate(link):
        if token.endswith('sources/cuda/cuda_matrix_ewisemult_inverted.cu.o'):
            link[i] = str(obj)
        elif token.endswith('.o') and not token.startswith('/'):
            link[i] = str(LIB / token)
    commands.append(link)
    (OUT / 'commands.json').write_text(json.dumps(commands, indent=2))
    before = hashlib.sha256((LIB / 'libcubool.so').read_bytes()).hexdigest()
    for command in commands:
        subprocess.run(command, check=True)
    run = subprocess.run(['python3', str(ROOT / 'scripts/probe-matrix-primitives.py'),
        str(BUILD / 'libcubool.so'), '--gpu'], capture_output=True, text=True, timeout=60)
    (OUT / 'primitive-trial.json').write_text(run.stdout)
    (OUT / 'primitive-trial.stderr').write_text(run.stderr)
    parsed = json.loads(run.stdout)
    assert all(r['passed'] for r in parsed['results'] if r['operation'] == 'cuBool_Matrix_EWiseMulInverted')
    env = dict(os.environ, LD_LIBRARY_PATH=str(BUILD))
    query = subprocess.run([str(ROOT / 'src/cfra/build-gpu-cuda124/cfra'),
        '--graph', str(ROOT / 'data/trial-catalog/atom/cfra-graph.txt'), '--grammar',
        str(ROOT / 'data/trial-catalog/atom/nested_parentheses_subClassOf_type.cnf'),
        '--algo', 'incremental'], env=env, capture_output=True, text=True, timeout=120)
    (OUT / 'atom.stdout').write_text(query.stdout)
    (OUT / 'atom.stderr').write_text(query.stderr)
    assert query.returncode == 0 and '#SEdges: 6\n' in query.stdout
    assert hashlib.sha256((LIB / 'libcubool.so').read_bytes()).hexdigest() == before
    (OUT / 'manifest.json').write_text(json.dumps(dict(baseline_library_sha256=before,
        trial_library_sha256=hashlib.sha256((BUILD / 'libcubool.so').read_bytes()).hexdigest(),
        trial_source_sha256=hashlib.sha256(generated.read_bytes()).hexdigest(),
        primitive_passed=parsed['passed'], primitive_total=parsed['total'], atom_pairs=6), indent=2))
    print('Difference cases passed; atom incremental=6; all primitive probes:', parsed['passed'], '/', parsed['total'])


if __name__ == '__main__':
    main()
