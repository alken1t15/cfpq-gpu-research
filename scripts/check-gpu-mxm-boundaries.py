"""Distinct-output MxM against a set oracle across row/warp/bin boundaries."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import random


def cases():
    rng = random.Random(20261106)
    for m in (1,2,3,7,8,9,31,32,33,63,64,65,127,128,129):
        k, n = 7, 33
        a = {(u,v) for u in range(m) for v in range(k) if rng.random() < .35}
        b = {(v,w) for v in range(k) for w in range((0,1,2,7,20,32,33)[v])}
        yield f'rows-{m}', (m,k,n), a, b
    for n in (1,2,3,7,8,9,31,32,33,63,64,65,127,128,129,255,256,257,
              511,512,513,1023,1024,1025,2047,2048,2049,4095,4096,4097):
        yield f'cols-{n}', (3,2,n), {(0,0),(1,0),(1,1),(2,1)}, {(v,w) for v in range(2) for w in range(n)}
    for i in range(24):
        m,k,n = (rng.choice((1,3,7,17,33,65)) for _ in range(3))
        a = {(u,v) for u in range(m) for v in range(k) if rng.random() < .12}
        b = {(v,w) for v in range(k) for w in range(n) if rng.random() < .12}
        yield f'random-{i}', (m,k,n), a,b


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('library')
    parser.add_argument('output')
    args = parser.parse_args()
    lib = C.CDLL(args.library)
    ix,h = C.c_uint,C.c_void_p
    signatures = {'cuBool_Initialize':[ix], 'cuBool_Finalize':[],
        'cuBool_Matrix_New':[C.POINTER(h),ix,ix], 'cuBool_Matrix_Free':[h],
        'cuBool_Matrix_Build':[h,C.POINTER(ix),C.POINTER(ix),ix,ix],
        'cuBool_Matrix_Nvals':[h,C.POINTER(ix)],
        'cuBool_Matrix_ExtractPairs':[h,C.POINTER(ix),C.POINTER(ix),C.POINTER(ix)],
        'cuBool_MxM':[h,h,h,ix]}
    for name, signature in signatures.items():
        getattr(lib,name).argtypes=signature
        getattr(lib,name).restype=C.c_int
    def call(name,*values):
        code=getattr(lib,name)(*values)
        assert code==0,(name,code)
    def matrix(rows,cols,pairs):
        handle=h()
        call('cuBool_Matrix_New',C.byref(handle),rows,cols)
        if pairs:
            pairs=sorted(pairs)
            rr=(ix*len(pairs))(*(p[0] for p in pairs))
            cc=(ix*len(pairs))(*(p[1] for p in pairs))
            call('cuBool_Matrix_Build',handle,rr,cc,len(pairs),0)
        return handle
    rows=[]
    call('cuBool_Initialize',0)
    try:
        for name,(m,k,n),a,b in cases():
            product={(u,w) for u,v in a for x,w in b if v==x}
            for accumulate in (False,True):
                initial={(0,n-1),(m-1,0)}
                handles=[matrix(m,k,a),matrix(k,n,b),matrix(m,n,initial)]
                try:
                    call('cuBool_MxM',handles[2],handles[0],handles[1],8 if accumulate else 0)
                    size=ix()
                    call('cuBool_Matrix_Nvals',handles[2],C.byref(size))
                    rr,cc=(ix*size.value)(),(ix*size.value)()
                    call('cuBool_Matrix_ExtractPairs',handles[2],rr,cc,C.byref(size))
                    actual=set(zip(rr,cc))
                    expected=product|initial if accumulate else product
                    rows.append(dict(case=name,shape=[m,k,n],accumulate=accumulate,
                        expected_count=len(expected),actual_count=len(actual),actual_nvals=size.value,
                        passed=actual==expected and size.value==len(expected),
                        missing=sorted(expected-actual)[:16],extra=sorted(actual-expected)[:16]))
                finally:
                    for handle in handles: call('cuBool_Matrix_Free',handle)
                Path(args.output).write_text(json.dumps(dict(library=args.library,
                    sha256=hashlib.sha256(Path(args.library).read_bytes()).hexdigest(),seed=20261106,
                    passed=sum(r['passed'] for r in rows),total=len(rows),results=rows),indent=2))
            print(name,rows[-2]['passed'],rows[-1]['passed'],flush=True)
    finally:
        call('cuBool_Finalize')
    return 0 if all(r['passed'] for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
