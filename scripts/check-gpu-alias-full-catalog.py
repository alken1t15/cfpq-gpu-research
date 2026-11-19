import hashlib,json,os,re,subprocess,time
import argparse
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=root/'experiments/2026-11-19-gpu-alias'
build=root/'build/gpu-mxm-alias'
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
for name, sha in json.loads((out/'manifest.json').read_text())['sha256'].items():
    assert digest(root/name)==sha,name
inputs=json.loads((root/'experiments/2026-11-03-trial-catalog/inputs.json').read_text())
rows=[]
parser=argparse.ArgumentParser()
parser.add_argument('--retry-timeouts', action='store_true')
parser.add_argument('--rerun', action='store_true')
args=parser.parse_args()
if args.retry_timeouts and args.rerun:
    parser.error('Choose one mode')
initial=out/'full-catalog.json'
target=out/'full-catalog-retry.json' if args.retry_timeouts else out/'full-catalog-rerun.json' if args.rerun else initial
limit=900 if args.retry_timeouts or args.rerun else 300
retry=set()
if args.retry_timeouts:
    previous=json.loads(initial.read_text())
    if len(previous)!=3*len(inputs):
        raise SystemExit('Wait for the initial series to finish')
    retry={(r['graph'],r['algo']) for r in previous if r.get('status')=='timeout'}
if target.exists(): raise SystemExit('Preserve existing results first')
for item in inputs:
    data=root/'data/trial-catalog'/item['graph']
    assert digest(data/'cfra-graph.txt')==item['graph_sha256']
    assert digest(data/item['grammar'])==item['grammar_sha256']
for item in inputs:
    data=root/'data/trial-catalog'/item['graph']
    for algo in ('incremental','base','lazy'):
        if args.retry_timeouts and (item['graph'],algo) not in retry:
            continue
        cmd=[str(build/'cfra'),'--graph',str(data/'cfra-graph.txt'),'--grammar',str(data/item['grammar']),'--algo',algo]
        row=dict(graph=item['graph'],algo=algo,expected=item['expected'],command=cmd,timeout_seconds=limit)
        print('START',item['graph'],algo,flush=True)
        start=time.monotonic()
        try:
            r=subprocess.run(cmd,env=dict(os.environ,LD_LIBRARY_PATH=str(build/'cuBool/cubool')),capture_output=True,text=True,timeout=limit)
            row.update(exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr)
        except subprocess.TimeoutExpired as e:
            row.update(status='timeout',stdout=(e.stdout or b'').decode(errors='replace'),stderr=(e.stderr or b'').decode(errors='replace'))
        match=re.search(r'#SEdges:\s*(\d+)',row['stdout'])
        row.update(actual=int(match[1]) if match else None,wall_seconds=time.monotonic()-start)
        row['passed']=row.get('exit_code')==0 and row['actual']==row['expected']
        rows.append(row)
        target.write_text(json.dumps(rows,indent=2)+'\n')
        print('END',row['graph'],algo,row['actual'],row.get('status',row.get('exit_code')),round(row['wall_seconds'],2),flush=True)
raise SystemExit(not all(row['passed'] for row in rows))
