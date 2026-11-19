"""Validate alias behavior in the integrated CUDA-only build."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build/gpu-mxm-alias'
OUT = ROOT / 'experiments/2026-11-19-gpu-alias'
LIB = BUILD / 'cuBool/cubool/libcubool.so'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, LD_LIBRARY_PATH=str(LIB.parent))
    results = []
    def run(name, cmd):
        print(name, flush=True)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env)
            row = dict(exit_code=r.returncode, stdout=r.stdout, stderr=r.stderr)
        except subprocess.TimeoutExpired as e:
            row = dict(status='timeout', stdout=(e.stdout or b'').decode(errors='replace'),
                       stderr=(e.stderr or b'').decode(errors='replace'))
        results.append(dict(name=name, command=cmd, **row))
        (OUT / 'results.json').write_text(json.dumps(results, indent=2))
        return row

    files = (LIB, BUILD / 'cfra')
    (OUT / 'manifest.json').write_text(json.dumps(dict(
        source_base=subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
        sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}), indent=2))
    for script, args in (
        ('check-cubool-mxm-pairs.py', ['--gpu', '--collect-failures']),
        ('probe-matrix-primitives.py', ['--gpu']),
        ('check-gpu-mxm-boundaries.py', [str(OUT / 'boundaries.json')]),
    ):
        row = run(script, [sys.executable, str(ROOT / 'scripts' / script), str(LIB), *args])
        if row.get('exit_code') != 0:
            return 1
    inputs = json.loads((ROOT / 'experiments/2026-11-03-trial-catalog/inputs.json').read_text())
    passed = True
    for item in inputs:
        if item['graph'] in ('gson', 'luindex'):
            continue
        data = ROOT / 'data/trial-catalog' / item['graph']
        for algo in ('base', 'incremental', 'lazy'):
            row = run(item['graph'] + '-' + algo, [str(BUILD / 'cfra'), '--graph',
                      str(data / 'cfra-graph.txt'), '--grammar', str(data / item['grammar']), '--algo', algo])
            match = re.search(r'#SEdges:\s*(\d+)', row['stdout'])
            passed &= bool(row.get('exit_code') == 0 and match and int(match[1]) == item['expected'])
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
