"""Extract iteration durations and gaps from the isolated diagnostic log."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'experiments/2026-11-09-gpu-progress'


def main():
    summary = {}
    for graph in ('pizza', 'luindex'):
        records = []
        for line in (OUT/(graph+'.progress')).read_text().splitlines():
            if line.startswith('PROGRESS '):
                r = dict(re.findall(r'(\w+)=([^ ]+)',line))
                r.update(time=float(r['time']), iter=int(r['iter']), calls=int(r['calls']), delta=int(r['delta']))
                records.append(r)
        starts = {r['iter']:r for r in records if r['event']=='iteration_begin'}
        ends = [r for r in records if r['event']=='iteration_end']
        iterations = [dict(iter=r['iter'], seconds=r['time']-starts[r['iter']]['time'],
                           calls=r['calls']-starts[r['iter']]['calls'], delta=r['delta']) for r in ends]
        summary[graph] = dict(iterations=iterations, final=ends[-1] if ends else None,
            max_observed_log_gap_seconds=max((b['time']-a['time'] for a,b in zip(records,records[1:])),default=None))
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
