"""One sequential trial/baseline luindex pair; preliminary, not a benchmark."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'experiments/2026-11-06-bin-metadata'
BASE = ROOT/'build/gpu-row-mask-integrated'
TRIAL = ROOT/'build/gpu-bin-metadata'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    target = OUT/'luindex-pair.json'
    if target.exists():
        raise RuntimeError('Archive existing pair before rerun')
    data = ROOT/'data/trial-catalog/luindex'
    cmd = [str(BASE/'cfra'), '--graph', str(data/'cfra-graph.txt'),
           '--grammar', str(data/'java_points_to.cnf'), '--algo', 'incremental']
    paths = [BASE/'cfra', BASE/'cuBool/cubool/libcubool.so', TRIAL/'libcubool.so',
             data/'cfra-graph.txt', data/'java_points_to.cnf']
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in paths}
    expected = json.loads((OUT/'manifest.json').read_text())
    assert digest(paths[1]) == expected['baseline_sha256']
    assert digest(paths[2]) == expected['trial_sha256']
    result = dict(command=cmd, hashes=hashes, timeout_seconds=300,
                  source_head=subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
                  note='One trial then baseline, fresh processes, no warmup; no profiler. Full subprocess wall time. Not a performance baseline.', runs=[])
    for name, lib in [('trial', TRIAL), ('baseline', BASE/'cuBool/cubool')]:
        print('START', name, flush=True)
        begin = time.perf_counter()
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                               env=dict(os.environ, LD_LIBRARY_PATH=str(lib)))
            row = dict(exit_code=r.returncode, stdout=r.stdout, stderr=r.stderr)
        except subprocess.TimeoutExpired as e:
            def decode(value):
                return value.decode(errors='replace') if isinstance(value, bytes) else value or ''
            row = dict(status='timeout', stdout=decode(e.stdout), stderr=decode(e.stderr))
        row.update(name=name, wall_seconds=time.perf_counter()-begin)
        match = re.search(r'#SEdges:\s*(\d+)', row['stdout'])
        row['actual_pairs'] = int(match[1]) if match else None
        row['passed'] = row.get('exit_code') == 0 and row['actual_pairs'] == 9677
        result['runs'].append(row)
        target.write_text(json.dumps(result, indent=2))
        print('END', name, row['wall_seconds'], row['actual_pairs'], row.get('status', row.get('exit_code')), flush=True)
    result['hashes_unchanged'] = hashes == {str(p.relative_to(ROOT)): digest(p) for p in paths}
    target.write_text(json.dumps(result, indent=2))
    return 0 if result['hashes_unchanged'] and all(r['passed'] for r in result['runs']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
