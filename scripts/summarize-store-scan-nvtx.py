from collections import defaultdict
from pathlib import Path
import argparse
import sqlite3
parser = argparse.ArgumentParser(description="Attribute CUB scans to NVTX ranges in Nsight SQLite traces")
parser.add_argument("traces", metavar="TRACE.sqlite", nargs="+", type=Path)
args = parser.parse_args()

for path in args.traces:
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        print(path, flush=True)
        names = dict(db.execute("select id, value from StringIds"))
        ranges = defaultdict(list)
        for start, end, tid, label, label_id in db.execute(
            "select start,end,globalTid,text,textId from NVTX_EVENTS where end is not null order by start"
        ):
            label = label or names.get(label_id, "")
            if label.startswith(("incremental/", "store_blocks/")):
                ranges[tid].append((start, end, label))
        if not ranges:
            raise ValueError(f"No CFRA NVTX ranges in {path}")
        print("ranges", sum(map(len, ranges.values())), flush=True)
        scans = dict(db.execute(
            "select correlationId,end-start from CUPTI_ACTIVITY_KIND_KERNEL where shortName in "
            "(select id from StringIds where value='DeviceScanKernel')"
        ))
        offset = defaultdict(int)
        previous = {}
        totals = defaultdict(lambda: [0, 0, 0, 0])
        for start, end, tid, cid, name_id in db.execute(
            "select start,end,globalTid,correlationId,nameId from CUPTI_ACTIVITY_KIND_RUNTIME order by start"
        ):
            intervals = ranges[tid]
            i = offset[tid]
            while i < len(intervals) and intervals[i][1] <= start:
                i += 1
            offset[tid] = i
            label = intervals[i][2] if i < len(intervals) and intervals[i][0] <= start < intervals[i][1] else "outside"
            if cid in scans:
                stat = totals[label]
                stat[0] += 1
                stat[1] += scans[cid]
            if names[name_id].startswith("cudaStreamSynchronize") and previous.get(tid) in scans:
                stat = totals[label]
                stat[2] += 1
                stat[3] += end-start
            previous[tid] = cid
        if sum(stat[0] for stat in totals.values()) != len(scans):
            raise ValueError(f"Incomplete scan-to-launch mapping in {path}")
        print("range, scan count, GPU seconds, sync count, host sync seconds", flush=True)
        for label, (count, gpu, sync_count, sync_time) in sorted(totals.items(), key=lambda item: -item[1][3]):
            print(label, count, round(gpu/1e9, 6), sync_count, round(sync_time/1e9, 6), flush=True)
