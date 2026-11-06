"""Validate isolated metadata trial, then compare complete pizza queries."""
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/2026-11-06-bin-metadata'
BASE = ROOT / 'build/gpu-row-mask-integrated'
TRIAL = ROOT / 'build/gpu-bin-metadata'


def main():
    rows = json.loads((OUT/'checks.json').read_text()) if '--timing-only' in sys.argv else []
    def run(name, cmd, lib, timeout=180):
        env = dict(os.environ, LD_LIBRARY_PATH=str(lib))
        begin = time.perf_counter()
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)
            row = dict(name=name, exit_code=r.returncode, stdout=r.stdout, stderr=r.stderr)
        except subprocess.TimeoutExpired as e:
            row = dict(name=name, status='timeout', stdout=(e.stdout or b'').decode(), stderr=(e.stderr or b'').decode())
        row['wall_seconds'] = time.perf_counter()-begin
        rows.append(row)
        (OUT / 'checks.json').write_text(json.dumps(rows, indent=2))
        print(name, row.get('exit_code', row.get('status')), row['wall_seconds'], flush=True)
        return row
    for label, lib in ([] if '--timing-only' in sys.argv else [('baseline', BASE/'cuBool/cubool'), ('trial', TRIAL)]):
        r = run(label+'-cpp', [str(BASE/'cuBool/cubool/tests/test_matrix_mxm'),
                '--gtest_filter=cuBool_Matrix.MultiplyDivergentSmallRows:cuBool_Matrix.MultiplySmall'], lib)
        assert r.get('exit_code') == 0
        for script, args in [('probe-matrix-primitives.py', ['--gpu']),
                             ('check-gpu-mxm-boundaries.py', [str(OUT/(label+'-boundaries.json'))]),
                             ('check-cubool-mxm-pairs.py', ['--gpu', '--collect-failures'])]:
            r = run(label+'-'+script, [sys.executable, str(ROOT/'scripts'/script), str(lib/'libcubool.so'), *args], lib)
            if script == 'check-cubool-mxm-pairs.py':
                d = json.loads(r['stdout'])
                assert d['total'] == 864 and all(f['alias'] != 'distinct' and not f['accumulate'] for f in d['failures'])
            else:
                assert r.get('exit_code') == 0
    inputs = json.loads((ROOT/'experiments/2026-11-03-trial-catalog/inputs.json').read_text())
    for item in ([] if '--timing-only' in sys.argv else inputs):
        if item['graph'] in ('gson', 'luindex'):
            continue
        for algo in ('base', 'incremental', 'lazy'):
            data = ROOT/'data/trial-catalog'/item['graph']
            r = run('trial-'+item['graph']+'-'+algo, [str(BASE/'cfra'), '--graph', str(data/'cfra-graph.txt'),
                    '--grammar', str(data/item['grammar']), '--algo', algo], TRIAL)
            assert r.get('exit_code') == 0 and re.search(r'#SEdges:\s*'+str(item['expected'])+r'\b', r['stdout'])
    # Alternate order to reduce systematic ordering bias. One warmup each.
    measured = dict(baseline=[], trial=[])
    data = ROOT/'data/trial-catalog/pizza'
    cmd = [str(BASE/'cfra'), '--graph', str(data/'cfra-graph.txt'), '--grammar', str(data/'nested_parentheses_subClassOf_type.cnf'), '--algo', 'incremental']
    for i in range(6):
        order = [('baseline', BASE/'cuBool/cubool'), ('trial', TRIAL)]
        if i % 2:
            order.reverse()
        for label, lib in order:
            r = run(f'timing-{i}-{label}', cmd, lib)
            assert r.get('exit_code') == 0 and '#SEdges: 1356' in r['stdout']
            if i:
                measured[label].append(r['wall_seconds'])
    summary = {k: dict(values=v, median=statistics.median(v), minimum=min(v), maximum=max(v)) for k,v in measured.items()}
    (OUT/'timing-summary.json').write_text(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
