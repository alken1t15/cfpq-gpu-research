"""Test whether wrong row counts make fill write past the logical allocation."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/2026-11-06-fixed-mask'
BUILD = ROOT / 'build/gpu-fixed-mask'
INCLUDE = ROOT / 'src/cfra/cuBool/deps/nsparse-um/include'


def main():
    text = (ROOT / 'experiments/2026-11-06-mxm-diagnosis/count-probe.cu').read_text()
    text = text.replace('#include <cstdio>', '#include <cstdio>\n#include <nsparse/detail/fill_nz.cuh>')
    marker = '        printf("[%u,%u,%u]\\n",nz[0],nz[1],nz[2]);'
    replacement = r'''
        T *offsets, *output;
        CUDA_OK(cudaMallocManaged(&offsets,4*sizeof(T)));
        CUDA_OK(cudaMallocManaged(&output,8*sizeof(T)));
        offsets[0]=0;
        for(int i=0;i<3;++i) offsets[i+1]=offsets[i]+nz[i];
        T logical_size=offsets[3];
        for(int i=0;i<8;++i) output[i]=777;
        nsparse::fill_nz_pwarp_row<T,4,256,32><<<1,256>>>(
            thrust::device_pointer_cast(cr),thrust::device_pointer_cast(cr),
            thrust::device_pointer_cast(ar),thrust::device_pointer_cast(ac),
            thrust::device_pointer_cast(br),thrust::device_pointer_cast(bc),
            thrust::device_pointer_cast(perm),thrust::device_pointer_cast(output),
            thrust::device_pointer_cast(offsets),3u);
        CUDA_OK(cudaGetLastError());
        CUDA_OK(cudaDeviceSynchronize());
        int changed_guard=0;
        for(T i=logical_size;i<8;++i) if(output[i]!=777) ++changed_guard;
        printf("logical_size=%u changed_guard=%d output=",logical_size,changed_guard);
        for(int i=0;i<8;++i) printf("%u,",output[i]);
        printf("\n");
        cudaFree(offsets); cudaFree(output);
'''
    assert text.count(marker) == 1
    text = text.replace(marker,replacement)
    source = OUT / 'fill-guard.cu'
    source.write_text(text)
    rows=[]
    for name in ('baseline','fixed'):
        binary=BUILD / ('fill-guard-'+name)
        cmd=['/usr/local/cuda-12.4/bin/nvcc','-ccbin','/usr/bin/g++-11','-std=c++14',
             '-O3','-arch=sm_86','--expt-extended-lambda','--expt-relaxed-constexpr']
        if name=='fixed': cmd+=['-I'+str(BUILD)]
        cmd+=['-I'+str(INCLUDE),str(source),'-o',str(binary)]
        compiled=subprocess.run(cmd,capture_output=True,text=True)
        row=dict(variant=name,command=cmd,compile_exit=compiled.returncode,compile_stderr=compiled.stderr)
        if compiled.returncode==0:
            run=subprocess.run([str(binary)],capture_output=True,text=True,timeout=30)
            row.update(exit_code=run.returncode,stdout=run.stdout,stderr=run.stderr)
            print(name,run.stdout,flush=True)
        rows.append(row)
        (OUT/'fill-guard-results.json').write_text(json.dumps(rows,indent=2))


if __name__=='__main__':
    main()
