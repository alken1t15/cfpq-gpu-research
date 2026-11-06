"""Build and validate the integrated row-mask fix; preserve prior baselines."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/2026-11-06-row-mask-integration'
BUILD = ROOT / 'build/gpu-row-mask-integrated'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = dict(source_head=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
                    commands=[], gpu_only=True)
    for relative in ('src/cfra/cuBool/deps/nsparse-um/include/nsparse/detail/count_nz.cuh',
                     'src/cfra/cuBool/cubool/tests/test_matrix_mxm.cpp'):
        manifest.setdefault('source_sha256',{})[relative]=hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()
    (OUT/'source.patch').write_bytes(subprocess.check_output(['git','-C',str(ROOT),'diff','--','src/cfra']))
    def save():
        (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    def run(name,cmd,timeout=180,env=None):
        print('START',name,flush=True)
        try:
            process=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout,env=env)
            result=dict(exit_code=process.returncode,stdout=process.stdout,stderr=process.stderr)
        except subprocess.TimeoutExpired as error:
            def decode(value):
                return value.decode(errors='replace') if isinstance(value,bytes) else value or ''
            result=dict(status='timeout',stdout=decode(error.stdout),stderr=decode(error.stderr))
        (OUT/(name+'.stdout')).write_text(result['stdout'])
        (OUT/(name+'.stderr')).write_text(result['stderr'])
        manifest['commands'].append(dict(name=name,command=cmd,timeout_seconds=timeout,
                                        **{k:v for k,v in result.items() if k not in ('stdout','stderr')}))
        save()
        print('END',name,{k:v for k,v in result.items() if k not in ('stdout','stderr')},flush=True)
        return result
    configure=['cmake','-S',str(ROOT/'src/cfra'),'-B',str(BUILD),'-DCMAKE_BUILD_TYPE=Release',
        '-DCMAKE_C_COMPILER=gcc-13','-DCMAKE_CXX_COMPILER=g++-13',
        '-DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.4/bin/nvcc','-DCMAKE_CUDA_HOST_COMPILER=/usr/bin/g++-11',
        '-DCMAKE_CUDA_ARCHITECTURES=86','-DCUBOOL_WITH_CUDA=ON','-DCUBOOL_WITH_SEQUENTIAL=OFF',
        '-DCUBOOL_BUILD_TESTS=ON','-DCUBOOL_COPY_TO_PY_PACKAGE=OFF']
    if run('configure',configure,300).get('exit_code')!=0: return 2
    if run('build',['cmake','--build',str(BUILD),'--target','cfra','test_matrix_mxm','-j2'],1200).get('exit_code')!=0: return 2
    library=BUILD/'cuBool/cubool/libcubool.so'
    binary=BUILD/'cfra'
    for path in (library,binary):
        manifest.setdefault('binary_sha256',{})[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    env=dict(os.environ,LD_LIBRARY_PATH=str(library.parent))
    test=run('cpp-regression',[str(BUILD/'cuBool/cubool/tests/test_matrix_mxm'),
        '--gtest_filter=cuBool_Matrix.MultiplyDivergentSmallRows:cuBool_Matrix.MultiplySmall'],180,env)
    primitive=run('primitives',[sys.executable,str(ROOT/'scripts/probe-matrix-primitives.py'),str(library),'--gpu'],120,env)
    boundary=run('boundaries',[sys.executable,str(ROOT/'scripts/check-gpu-mxm-boundaries.py'),str(library),str(OUT/'boundaries.json')],180,env)
    tiny=run('matrix-alias-diagnostics',[sys.executable,str(ROOT/'scripts/check-cubool-mxm-pairs.py'),str(library),
        '--gpu','--collect-failures'],180,env)
    inputs=json.loads((ROOT/'experiments/2026-11-03-trial-catalog/inputs.json').read_text())
    catalog=[]
    for item in inputs:
        if item['graph']=='gson': continue
        for algo in (('incremental',) if item['graph']=='luindex' else ('base','incremental','lazy')):
            data=ROOT/'data/trial-catalog'/item['graph']
            result=run(item['graph']+'-'+algo,[str(binary),'--graph',str(data/'cfra-graph.txt'),
                '--grammar',str(data/item['grammar']),'--algo',algo],180 if item['graph']=='luindex' else 60,env)
            match=re.search(r'#SEdges:\s*(\d+)',result['stdout'])
            row=dict(graph=item['graph'],algo=algo,expected=item['expected'],actual=int(match[1]) if match else None,
                     **result)
            row['passed']=row.get('exit_code')==0 and row['actual']==row['expected']
            catalog.append(row)
            (OUT/'catalog.json').write_text(json.dumps(catalog,indent=2))
    diagnostic=json.loads(tiny['stdout']) if tiny.get('exit_code') in (0,1) else None
    relevant_ok=diagnostic is not None and all(f['alias']!='distinct' and not f['accumulate'] for f in diagnostic['failures'])
    summary=dict(cpp_passed=test.get('exit_code')==0,primitives_passed=primitive.get('exit_code')==0,
        boundaries_passed=boundary.get('exit_code')==0,
        alias_diagnostic_passed=diagnostic['passed'] if diagnostic else None,
        no_distinct_or_accumulate_failures=relevant_ok,
        catalog_passed=sum(r['passed'] for r in catalog),catalog_total=len(catalog))
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
    print(summary,flush=True)
    return 0 if all((summary['cpp_passed'],summary['primitives_passed'],summary['boundaries_passed'],
                    relevant_ok,all(r['passed'] for r in catalog))) else 1


if __name__=='__main__':
    raise SystemExit(main())
