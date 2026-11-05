"""Record targeted checks of the PR19 GPU-only build without changing old results."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build/gpu-cubool-pr19'
OUT = ROOT / 'experiments/2026-11-06-cubool-update'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    library = BUILD / 'cuBool/cubool/libcubool.so'
    binary = BUILD / 'cfra'
    manifest = {'cubool_fork': 'https://github.com/vano105/cuBool',
                'cubool_sha': '37ccfd818f3bc9c5cb6483a2e76fc73ee93a01f3',
                'gpu_only': True,
                'sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in (library, binary)}}
    env = dict(os.environ, LD_LIBRARY_PATH=str(library.parent))
    command = [sys.executable, str(ROOT / 'scripts/probe-matrix-primitives.py'), str(library), '--gpu']
    probe = subprocess.run(command, capture_output=True, text=True, timeout=120, env=env)
    (OUT / 'primitive-results.json').write_text(probe.stdout)
    (OUT / 'primitive.stderr').write_text(probe.stderr)
    manifest['primitive_command'] = command
    manifest['primitive_exit_code'] = probe.returncode
    rows = []
    data = ROOT / 'data/trial-catalog/atom'
    for algo in ('base', 'incremental', 'lazy'):
        command = [str(binary), '--graph', str(data / 'cfra-graph.txt'),
                   '--grammar', str(data / 'nested_parentheses_subClassOf_type.cnf'), '--algo', algo]
        run = subprocess.run(command, capture_output=True, text=True, timeout=60, env=env)
        match = re.search(r'#SEdges:\s*(\d+)', run.stdout)
        actual = int(match[1]) if match else None
        rows.append(dict(algorithm=algo, command=command, exit_code=run.returncode,
                         expected=6, actual=actual, passed=run.returncode == 0 and actual == 6,
                         stdout=run.stdout, stderr=run.stderr))
    (OUT / 'atom-results.json').write_text(json.dumps(rows, indent=2))
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    details = json.loads(probe.stdout)
    print(json.dumps({'primitives_passed': details['passed'], 'primitives_total': details['total'],
                      'atom_passed': sum(r['passed'] for r in rows), 'atom_total': len(rows)}))
    return 0 if probe.returncode == 0 and all(r['passed'] for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
