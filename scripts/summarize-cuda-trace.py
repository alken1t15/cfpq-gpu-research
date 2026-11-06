"""Summarize Nsight SQLite intervals without adding overlapping durations."""
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]


def union_ns(intervals):
    total = 0
    end = None
    for begin, stop in sorted(intervals):
        total += max(0, stop - max(begin, end if end is not None else begin))
        end = max(stop, end if end is not None else stop)
    return total


def main():
    summaries = {}
    for mode in ('small', 'luindex'):
        path = ROOT / 'build/gpu-cuda-trace' / (mode + '.sqlite')
        if not path.exists():
            continue
        con = sqlite3.connect(path)
        tables = {r[0] for r in con.execute('select name from sqlite_master where type=?', ('table',))}
        result = {}
        gpu = []
        for name in ('RUNTIME', 'DRIVER', 'KERNEL', 'MEMCPY', 'MEMSET'):
            table = 'CUPTI_ACTIVITY_KIND_' + name
            if table not in tables:
                continue
            intervals = con.execute('select start,end from ' + table).fetchall()
            result[name.lower()] = dict(count=len(intervals), sum_ns=sum(b-a for a,b in intervals),
                                        union_ns=union_ns(intervals),
                                        span_ns=max((b for a,b in intervals), default=0)-min((a for a,b in intervals), default=0))
            if name in ('KERNEL', 'MEMCPY', 'MEMSET'):
                gpu.extend(intervals)
        runtime = 'CUPTI_ACTIVITY_KIND_RUNTIME'
        if runtime in tables:
            rows = con.execute('select s.value,count(*),sum(r.end-r.start) from ' + runtime +
                               ' r join StringIds s on s.id=r.nameId group by s.value order by 3 desc').fetchall()
            result['api'] = [dict(name=n, count=c, total_ns=t) for n,c,t in rows]
        result['gpu_activity_union_ns'] = union_ns(gpu)
        result['gpu_activity_span_ns'] = max((b for a,b in gpu), default=0)-min((a for a,b in gpu), default=0)
        if 'CUPTI_ACTIVITY_KIND_MEMCPY' in tables:
            rows = con.execute('select copyKind,bytes,count(*),sum(end-start) from CUPTI_ACTIVITY_KIND_MEMCPY '
                               'group by copyKind,bytes order by 3 desc limit 16').fetchall()
            result['copy_sizes'] = [dict(copy_kind=k, bytes=b, count=c, total_ns=t) for k,b,c,t in rows]
        summaries[mode] = result
        con.close()
    out = ROOT / 'experiments/2026-11-06-cuda-trace/timeline-summary.json'
    out.write_text(json.dumps(summaries, indent=2))
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    main()
