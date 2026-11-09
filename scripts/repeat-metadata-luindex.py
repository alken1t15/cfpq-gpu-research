"""Warm each library, then run two luindex pairs with reversed order."""
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'experiments/2026-11-09-metadata-repeat'
BASE = ROOT/'build/gpu-row-mask-integrated'
TRIAL = ROOT/'build/gpu-bin-metadata'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT/'results.json'
    if target.exists():
        raise RuntimeError('Existing results must be preserved')
    data = ROOT/'data/trial-catalog/luindex'
    command = [str(BASE/'cfra'), '--graph', str(data/'cfra-graph.txt'),
               '--grammar', str(data/'java_points_to.cnf'), '--algo', 'incremental']
    libraries = dict(baseline=BASE/'cuBool/cubool', trial=TRIAL)
    paths = [BASE/'cfra', *(p/'libcubool.so' for p in libraries.values()), data/'cfra-graph.txt', data/'java_points_to.cnf']
    def hashes():
        return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    before = hashes()
    expected = json.loads((ROOT/'experiments/2026-11-06-bin-metadata/manifest.json').read_text())
    assert before[str(paths[1].relative_to(ROOT))] == expected['baseline_sha256']
    assert before[str(paths[2].relative_to(ROOT))] == expected['trial_sha256']
    schedule = [('warmup', 'baseline'), ('warmup', 'trial'),
                ('pair1', 'baseline'), ('pair1', 'trial'), ('pair2', 'trial'), ('pair2', 'baseline')]
    result = dict(source_head=subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
                  command=command, hashes=before, schedule=schedule, timeout_seconds=300, runs=[],
                  scope='Fresh process full wall time through finalize; no profiler; warmup warms system caches, not shared CUDA context.')
    target.write_text(json.dumps(result, indent=2))
    for phase, label in schedule:
        print('START', phase, label, flush=True)
        begin = time.perf_counter()
        try:
            r = subprocess.run(command, capture_output=True, text=True, timeout=300,
                               env=dict(os.environ, LD_LIBRARY_PATH=str(libraries[label])))
            row = dict(exit_code=r.returncode, stdout=r.stdout, stderr=r.stderr)
        except subprocess.TimeoutExpired as e:
            def decode(v):
                return v.decode(errors='replace') if isinstance(v, bytes) else v or ''
            row = dict(status='timeout', stdout=decode(e.stdout), stderr=decode(e.stderr))
        row.update(phase=phase, library=label, wall_seconds=time.perf_counter()-begin)
        match = re.search(r'#SEdges:\s*(\d+)', row['stdout'])
        row['actual_pairs'] = int(match[1]) if match else None
        row['passed'] = row.get('exit_code') == 0 and row['actual_pairs'] == 9677
        result['runs'].append(row)
        result['hashes_unchanged'] = hashes() == before
        target.write_text(json.dumps(result, indent=2))
        print('END', phase, label, row['wall_seconds'], row['actual_pairs'], row.get('status', row.get('exit_code')), flush=True)
        if not row['passed'] or not result['hashes_unchanged']:
            return 1
    result['summary'] = {}
    for label in libraries:
        values = [r['wall_seconds'] for r in result['runs'] if r['library'] == label and r['phase'] != 'warmup']
        result['summary'][label] = dict(values=values, median=statistics.median(values), minimum=min(values), maximum=max(values))
    target.write_text(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
