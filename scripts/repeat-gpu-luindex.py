"""Preliminary sequential repeatability check of the integrated GPU binary."""
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/2026-11-06-gpu-repeatability'
BUILD = ROOT / 'build/gpu-row-mask-integrated'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / 'raw.json').exists():
        raise RuntimeError('Existing results must be archived before another run')
    binary = BUILD / 'cfra'
    library = BUILD / 'cuBool/cubool/libcubool.so'
    data = ROOT / 'data/trial-catalog/luindex'
    graph, grammar = data / 'cfra-graph.txt', data / 'java_points_to.cnf'
    files = [binary, library, graph, grammar]
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in files}
    integrated = json.loads((ROOT / 'experiments/2026-11-06-row-mask-integration/manifest.json').read_text())
    for p in (binary, library):
        assert hashes[str(p.relative_to(ROOT))] == integrated['binary_sha256'][str(p.relative_to(ROOT))]
    command = [str(binary), '--graph', str(graph), '--grammar', str(grammar), '--algo', 'incremental']
    env = dict(os.environ, LD_LIBRARY_PATH=str(library.parent))
    manifest = dict(source_head=subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
                    hashes=hashes, command=command, timeout_seconds=300,
                    warmup_processes=1, measured_processes=2,
                    scope='Full subprocess wall time including startup, input, CUDA initialization, analysis, output and finalize',
                    note='Fresh process each time; warmup warms system caches, not an in-process CUDA context. Preliminary sample, not a stable performance baseline.')
    for name, cmd in [('gpu', ['nvidia-smi']), ('linkage', ['ldd', str(binary)]),
                      ('system', ['uname', '-a']), ('cpu', ['lscpu'])]:
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
        (OUT / (name + '.txt')).write_text(r.stdout + r.stderr)
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    rows = []
    for i in range(3):
        print('START', i, 'warmup' if i == 0 else 'measured', flush=True)
        begin = time.perf_counter()
        try:
            run = subprocess.run(command, capture_output=True, text=True, timeout=300, env=env)
            row = dict(exit_code=run.returncode, stdout=run.stdout, stderr=run.stderr)
        except subprocess.TimeoutExpired as error:
            def decode(value):
                return value.decode(errors='replace') if isinstance(value, bytes) else value or ''
            row = dict(status='timeout', stdout=decode(error.stdout), stderr=decode(error.stderr))
        row.update(run=i, warmup=i == 0, wall_seconds=time.perf_counter() - begin)
        count = re.search(r'#SEdges:\s*(\d+)', row['stdout'])
        analysis = re.search(r'AnalysisTime:\s*([\d.eE+-]+)', row['stdout'])
        row.update(actual_pairs=int(count[1]) if count else None,
                   analysis_seconds=float(analysis[1]) if analysis else None)
        row['passed'] = row.get('exit_code') == 0 and row['actual_pairs'] == 9677
        rows.append(row)
        (OUT / 'raw.json').write_text(json.dumps(rows, indent=2))
        print('END', i, row['wall_seconds'], row['actual_pairs'], row.get('status', row.get('exit_code')), flush=True)
        if not row['passed']:
            return 1
    assert hashes == {str(p.relative_to(ROOT)): digest(p) for p in files}
    summary = dict(passed=sum(r['passed'] for r in rows), total=len(rows))
    for field in ('wall_seconds', 'analysis_seconds'):
        values = [r[field] for r in rows if not r['warmup']]
        summary[field] = dict(n=len(values), minimum=min(values), maximum=max(values),
                              median=statistics.median(values), sample_stdev=statistics.stdev(values))
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
