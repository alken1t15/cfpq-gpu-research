"""Summarize exact empty-product probes separately from original operations."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'experiments/2026-11-09-late-deltas'


def main():
    summary = {}
    for graph in ('pizza', 'luindex'):
        deltas, ops = [], []
        for line in (OUT/(graph+'.progress')).read_text().splitlines():
            if line.startswith(('DELTAS ', 'OPS ')):
                row = {k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',line)}
                (deltas if line.startswith('DELTAS ') else ops).append(row)
        tested = sum(r['tested'] for r in deltas)
        empty = sum(r['empty_products'] for r in deltas)
        summary[graph] = dict(per_iteration_deltas=deltas, per_iteration_ops=ops,
            original_mxm=sum(r['mxm'] for r in deltas), original_add=sum(r['add'] for r in ops),
            original_diff=sum(r['diff'] for r in ops), extra_product_probes=tested,
            empty_products=empty, empty_fraction=empty/tested if tested else None,
            note='Input delta_sum repeats pairs reused by several rules; not unique pair count. Extra probes start at iteration 33.')
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps({g:{k:v for k,v in s.items() if not k.startswith('per_iteration')} for g,s in summary.items()},indent=2))


if __name__ == '__main__':
    main()
