"""Small independent, distinct-output probes for CPU/GPU primitive semantics."""
import argparse
import ctypes as C
import json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('library')
    parser.add_argument('--gpu', action='store_true')
    args = parser.parse_args()
    lib = C.CDLL(args.library)
    h, ix = C.c_void_p, C.c_uint
    signatures = {'cuBool_Initialize': [ix], 'cuBool_Finalize': [],
        'cuBool_Matrix_New': [C.POINTER(h), ix, ix], 'cuBool_Matrix_Free': [h],
        'cuBool_Matrix_Build': [h, C.POINTER(ix), C.POINTER(ix), ix, ix],
        'cuBool_Matrix_Nvals': [h, C.POINTER(ix)],
        'cuBool_Matrix_ExtractPairs': [h, C.POINTER(ix), C.POINTER(ix), C.POINTER(ix)]}
    operations = ('cuBool_Matrix_EWiseAdd', 'cuBool_Matrix_EWiseMult',
                  'cuBool_Matrix_EWiseMulInverted', 'cuBool_MxM')
    for name in operations:
        signatures[name] = [h, h, h, ix]
    for name, signature in signatures.items():
        getattr(lib, name).argtypes, getattr(lib, name).restype = signature, C.c_int
    def call(name, *args):
        status = getattr(lib, name)(*args)
        assert status == 0, (name, status)
    cases = [(set(), set()), ({(0, 1)}, set()), (set(), {(1, 2)}),
             ({(0, 1)}, {(1, 2)}), ({(0, 1), (1, 2)}, {(0, 1)}),
             ({(1, 0), (1, 1), (2, 0), (2, 2)}, {(0, 0), (1, 1), (2, 1), (2, 2)})]
    call('cuBool_Initialize', 0 if args.gpu else 1)
    results = []
    try:
        for a, b in cases:
            expected = [a | b, a & b, a - b, {(u, w) for u, v in a for x, w in b if v == x}]
            for name, wanted in zip(operations, expected):
                matrices = []
                try:
                    for pairs in (a, b, set()):
                        matrix = h()
                        call('cuBool_Matrix_New', C.byref(matrix), 3, 3)
                        matrices.append(matrix)
                        if pairs:
                            items = sorted(pairs)
                            rows = (ix * len(items))(*(p[0] for p in items))
                            cols = (ix * len(items))(*(p[1] for p in items))
                            call('cuBool_Matrix_Build', matrix, rows, cols, len(items), 0)
                    call(name, matrices[2], matrices[0], matrices[1], 0)
                    n = ix()
                    call('cuBool_Matrix_Nvals', matrices[2], C.byref(n))
                    rows, cols = (ix * n.value)(), (ix * n.value)()
                    call('cuBool_Matrix_ExtractPairs', matrices[2], rows, cols, C.byref(n))
                    actual = set(zip(rows, cols))
                    results.append(dict(operation=name, a=sorted(a), b=sorted(b),
                                        expected=sorted(wanted), actual=sorted(actual), passed=actual == wanted))
                finally:
                    for matrix in matrices:
                        call('cuBool_Matrix_Free', matrix)
    finally:
        call('cuBool_Finalize')
    print(json.dumps(dict(library=args.library, gpu=args.gpu, total=len(results),
                         passed=sum(r['passed'] for r in results), results=results), indent=2))
    return 0 if all(r['passed'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
