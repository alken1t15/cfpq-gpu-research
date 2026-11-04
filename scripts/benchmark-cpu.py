"""Record a sequential process-level CPU baseline on prepared luindex."""
import hashlib
import json
import statistics
import subprocess
import time
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/2026-11-03-cpu-baseline'
SOURCE = ROOT / 'src/cfra'
DATA = ROOT / 'data/catalog-v6/luindex'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    binary = SOURCE / 'build-cpu-gcc13/cfra'
    graph, grammar = DATA / 'cfra-adapted.txt', DATA / 'java_points_to.cnf'
    patch = subprocess.check_output(['git', '-C', str(SOURCE), 'diff'])
    (OUT / 'tracked-changes.patch').write_bytes(patch)
    manifest = dict(base_sha=subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip(),
        binary_sha256=digest(binary), graph_sha256=digest(graph), grammar_sha256=digest(grammar),
        patch_sha256=hashlib.sha256(patch).hexdigest(), expected_pairs=9677,
        backend='cuBool CPU sequential', algorithm='incremental', warmup_processes=1, measured_processes=5,
        timeout_seconds=120, note='Fresh process per run; warmup warms system caches, not an in-process backend.')
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    rows = []
    for index in range(6):
        command = [str(binary), '--graph', str(graph), '--grammar', str(grammar), '--algo', 'incremental', '--cpu']
        begin = time.perf_counter()
        run = subprocess.run(command, capture_output=True, text=True, timeout=120)
        wall = time.perf_counter() - begin
        count = re.search(r'#SEdges:\s*(\d+)', run.stdout)
        analysis = re.search(r'AnalysisTime:\s*([\d.eE+-]+)', run.stdout)
        row = dict(run=index, warmup=index == 0, wall_seconds=wall,
                   analysis_seconds=float(analysis[1]) if analysis else None,
                   actual_pairs=int(count[1]) if count else None,
                   exit_code=run.returncode, stdout=run.stdout, stderr=run.stderr)
        rows.append(row)
        (OUT / 'raw.json').write_text(json.dumps(rows, indent=2))
        print(index, 'warmup' if index == 0 else 'measured', round(wall, 3), row['actual_pairs'], flush=True)
        if run.returncode or row['actual_pairs'] != 9677 or not analysis or run.stderr:
            raise RuntimeError('Baseline acceptance failed; inspect raw.json')
    assert digest(binary) == manifest['binary_sha256']
    summary = {}
    for field in ('wall_seconds', 'analysis_seconds'):
        values = [r[field] for r in rows if not r['warmup']]
        summary[field] = dict(n=len(values), median=statistics.median(values),
                             minimum=min(values), maximum=max(values), mean=statistics.mean(values),
                             sample_stdev=statistics.stdev(values))
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
