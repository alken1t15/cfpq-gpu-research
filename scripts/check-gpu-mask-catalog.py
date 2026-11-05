"""Bounded catalog checks of the isolated mask trial, preserving prior runs."""
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/2026-11-06-mxm-diagnosis'


def main():
    lib = ROOT / 'build/gpu-cubool-pr19/cuBool/cubool/libcubool.so'
    cmd = ['python3', str(ROOT / 'scripts/check-cubool-mxm-pairs.py'), str(lib), '--gpu', '--collect-failures']
    run = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    (OUT / 'matrix-baseline.json').write_text(run.stdout)
    (OUT / 'matrix-baseline.stderr').write_text(run.stderr)
    inputs = json.loads((ROOT / 'experiments/2026-11-03-trial-catalog/inputs.json').read_text())
    binary = ROOT / 'build/gpu-cubool-pr19/cfra'
    env = dict(os.environ, LD_LIBRARY_PATH=str(ROOT / 'build/mxm-diagnosis'))
    rows = []
    for item in inputs:
        if item['graph'] == 'gson':
            continue
        algos = ('incremental',) if item['graph'] == 'luindex' else ('base', 'incremental', 'lazy')
        for algo in algos:
            directory = ROOT / 'data/trial-catalog' / item['graph']
            command = [str(binary), '--graph', str(directory / 'cfra-graph.txt'),
                       '--grammar', str(directory / item['grammar']), '--algo', algo]
            row = dict(graph=item['graph'], algo=algo, expected=item['expected'], command=command)
            try:
                run = subprocess.run(command, capture_output=True, text=True, env=env, timeout=30)
                match = re.search(r'#SEdges:\s*(\d+)', run.stdout)
                row.update(exit_code=run.returncode, actual=int(match[1]) if match else None,
                           stdout=run.stdout, stderr=run.stderr)
            except subprocess.TimeoutExpired:
                row.update(status='timeout', actual=None)
            row['passed'] = row['actual'] == item['expected'] and row.get('exit_code') == 0
            rows.append(row)
            (OUT / 'catalog-trial.json').write_text(json.dumps(rows, indent=2))
            print(item['graph'], algo, row['actual'], '/', item['expected'], flush=True)


if __name__ == '__main__':
    main()
