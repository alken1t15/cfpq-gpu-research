"""Replace only the multiply object using the early-mask experimental header."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/2026-11-06-mxm-diagnosis'
BUILD = ROOT / 'build/mxm-diagnosis'
LIB = ROOT / 'build/gpu-cubool-pr19/cuBool/cubool'


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    before = digest(LIB / 'libcubool.so')
    flags = []
    for line in (LIB / 'CMakeFiles/cubool.dir/flags.make').read_text().splitlines():
        if line.startswith(('CUDA_DEFINES =', 'CUDA_INCLUDES =', 'CUDA_FLAGS =')):
            flags += shlex.split(line.split('=', 1)[1])
    source = ROOT / 'src/cfra/cuBool/cubool/sources/cuda/cuda_matrix_multiply.cu'
    obj = BUILD / 'multiply.cu.o'
    compile_cmd = ['/usr/local/cuda-12.4/bin/nvcc', '-ccbin=/usr/bin/g++-11',
                   '-I'+str(BUILD / 'early_mask'), *flags, '-c', str(source), '-o', str(obj)]
    link = shlex.split((LIB / 'CMakeFiles/cubool.dir/link.txt').read_text())
    trial = BUILD / 'libcubool.so'
    link[link.index('-o')+1] = str(trial)
    for i, token in enumerate(link):
        if token.endswith('sources/cuda/cuda_matrix_multiply.cu.o'):
            link[i] = str(obj)
        elif token.endswith('.o') and not token.startswith('/'):
            link[i] = str(LIB / token)
    (OUT / 'trial-commands.json').write_text(json.dumps([compile_cmd, link], indent=2))
    for cmd in (compile_cmd, link):
        subprocess.run(cmd, check=True)
    commands = [
        ('primitive-trial', ['python3', str(ROOT / 'scripts/probe-matrix-primitives.py'), str(trial), '--gpu']),
        ('matrix-trial', ['python3', str(ROOT / 'scripts/check-cubool-mxm-pairs.py'), str(trial), '--gpu', '--collect-failures']),
    ]
    results = []
    for name, cmd in commands:
        run = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        (OUT / (name+'.json')).write_text(run.stdout)
        (OUT / (name+'.stderr')).write_text(run.stderr)
        results.append(dict(name=name, command=cmd, exit_code=run.returncode))
        print(name, 'exit', run.returncode, run.stdout[:180], flush=True)
    assert digest(LIB / 'libcubool.so') == before
    (OUT / 'trial-manifest.json').write_text(json.dumps(dict(
        baseline_sha256=before, trial_sha256=digest(trial),
        source_commit=subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
        commands=results), indent=2))


if __name__ == '__main__':
    main()
