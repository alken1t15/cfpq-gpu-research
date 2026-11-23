"""Attribute small D2H transfers to stages in the luindex CUDA trace."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    uri = args.trace.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        if db.execute("SELECT count(DISTINCT globalPid) FROM CUPTI_ACTIVITY_KIND_MEMCPY").fetchone()[0] != 1:
            raise ValueError("Expected a single profiled process")
        if db.execute("SELECT label FROM ENUM_CUDA_MEMCPY_OPER WHERE id=2").fetchone() != ("Device-to-Host",):
            raise ValueError("Unexpected CUDA copy-kind mapping")
        events = db.execute("""
            SELECT correlationId, 'copy', bytes FROM CUPTI_ACTIVITY_KIND_MEMCPY
            WHERE copyKind=2 AND bytes IN (4,36)
            UNION ALL
            SELECT k.correlationId, 'count', 0 FROM CUPTI_ACTIVITY_KIND_KERNEL k
            JOIN StringIds s ON s.id=k.demangledName
            WHERE s.value LIKE '%kernel_call_impl%count_nz_functor%'
            UNION ALL
            SELECT k.correlationId, 'fill', 0 FROM CUPTI_ACTIVITY_KIND_KERNEL k
            JOIN StringIds s ON s.id=k.demangledName
            WHERE s.value LIKE '%fill_nz_functor%'
            UNION ALL
            SELECT r.correlationId, 'count_sync', 0 FROM CUPTI_ACTIVITY_KIND_RUNTIME r
            JOIN StringIds s ON s.id=r.nameId WHERE s.value LIKE 'cudaDeviceSynchronize_v%'
            ORDER BY 1,2
        """)
        counts = Counter()
        state = "before_count"
        for _, event, size in events:
            if event == "count":
                counts["count_starts"] += 1
                state = "count_before_host_vectors"
            elif event == "count_sync":
                counts["count_syncs"] += 1
                state = "first_read_after_count_sync"
            elif event == "fill":
                counts["fill_markers"] += 1
                state = "fill_window"
            elif size == 36:
                counts[f"36_bytes_{state}"] += 1
                state = "count_after_host_vectors"
            else:
                counts[f"4_bytes_{state}"] += 1
                if state == "first_read_after_count_sync":
                    state = "after_first_read"
    text = json.dumps(counts, indent=2, sort_keys=True) + "\n"
    args.out.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
