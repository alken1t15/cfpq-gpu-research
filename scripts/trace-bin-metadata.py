"""Compare complete identical pizza CUDA traces, not equal-duration windows."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'experiments/2026-11-06-bin-metadata'
LOCAL = ROOT/'build/gpu-bin-metadata-trace'
BASE = ROOT/'build/gpu-row-mask-integrated'
TRIAL = ROOT/'build/gpu-bin-metadata'
if '--empty-fill' in sys.argv:
    OUT = ROOT/'experiments/2026-11-10-empty-fill'
    LOCAL = ROOT/'build/gpu-empty-fill-trace'
    TRIAL = ROOT/'build/gpu-empty-fill'


def main():
    LOCAL.mkdir(parents=True, exist_ok=True)
    results = {}
    data = ROOT/'data/trial-catalog/pizza'
    for label, lib in [('baseline', BASE/'cuBool/cubool'), ('trial', TRIAL)]:
        prefix = LOCAL/label
        cmd = ['nsys', 'profile', '--trace=cuda', '--sample=none', '--cpuctxsw=none', '--output='+str(prefix),
               str(BASE/'cfra'), '--graph', str(data/'cfra-graph.txt'), '--grammar',
               str(data/'nested_parentheses_subClassOf_type.cnf'), '--algo', 'incremental']
        env = dict(os.environ, LD_LIBRARY_PATH=str(lib))
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env)
        (OUT/(label+'-trace.stdout')).write_text(r.stdout)
        (OUT/(label+'-trace.stderr')).write_text(r.stderr)
        assert r.returncode == 0 and '#SEdges: 1356' in r.stdout
        stats = ['nsys', 'stats', '--report=cuda_api_sum,cuda_gpu_mem_time_sum', '--format=csv', str(prefix.with_suffix('.nsys-rep'))]
        s = subprocess.run(stats, capture_output=True, text=True, timeout=180, env=env)
        (OUT/(label+'-trace-stats.csv')).write_text(s.stdout)
        assert s.returncode == 0
        con = sqlite3.connect(prefix.with_suffix('.sqlite'))
        copies = con.execute('select bytes,count(*) from CUPTI_ACTIVITY_KIND_MEMCPY where copyKind=2 group by bytes order by bytes').fetchall()
        calls = con.execute('select s.value,count(*) from CUPTI_ACTIVITY_KIND_RUNTIME r join StringIds s on s.id=r.nameId group by s.value').fetchall()
        results[label] = dict(command=cmd, stats_command=stats, exit_code=r.returncode,
                              dtoh_sizes=[dict(bytes=b, count=n) for b,n in copies], api=dict(calls))
        con.close()
        (OUT/'trace-comparison.json').write_text(json.dumps(results, indent=2))
        print(label, results[label], flush=True)


if __name__ == '__main__':
    main()
