"""Compare full tiny matrix answers with a set oracle, including aliasing."""
import argparse
import ctypes as C
import json
import random


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('library')
    parser.add_argument('--gpu', action='store_true')
    parser.add_argument('--collect-failures', action='store_true')
    args = parser.parse_args()
    lib = C.CDLL(args.library)
    index, handle = C.c_uint, C.c_void_p
    signatures = {
        'cuBool_Initialize': [index], 'cuBool_Finalize': [],
        'cuBool_Matrix_New': [C.POINTER(handle), index, index],
        'cuBool_Matrix_Free': [handle],
        'cuBool_Matrix_Build': [handle, C.POINTER(index), C.POINTER(index), index, index],
        'cuBool_Matrix_SetElement': [handle, index, index],
        'cuBool_Matrix_Nvals': [handle, C.POINTER(index)],
        'cuBool_Matrix_ExtractPairs': [handle, C.POINTER(index), C.POINTER(index), C.POINTER(index)],
        'cuBool_MxM': [handle, handle, handle, index],
    }
    for name, signature in signatures.items():
        getattr(lib, name).argtypes = signature
        getattr(lib, name).restype = C.c_int

    def call(name, *values):
        status = getattr(lib, name)(*values)
        assert status == 0, (name, status)

    universe = [(u, v) for u in range(3) for v in range(3)]
    rng = random.Random(20261103)
    fixtures = [(set(), set(), set()), ({(0, 1)}, {(1, 2)}, set()),
                ({(0, 1)}, {(2, 0)}, {(1, 1)}),
                (set(), {(1, 2)}, {(0, 0)}),
                ({(0, 0)}, {(0, 0)}, {(0, 0)}),
                (set(universe), set(universe), set())]
    for _ in range(48):
        fixtures.append(tuple({p for p in universe if rng.random() < rng.choice((0.0, 0.2, 0.7))} for _ in range(3)))
    call('cuBool_Initialize', 0 if args.gpu else 1)
    device = None
    if args.gpu:
        class Caps(C.Structure):
            _fields_ = [('name', C.c_char * 256), ('cudaSupported', C.c_bool),
                        ('managedMem', C.c_bool)] + [(name, C.c_int) for name in
                        ('major', 'minor', 'warp', 'globalMemoryKiBs',
                         'sharedMemoryPerMultiProcKiBs', 'sharedMemoryPerBlockKiBs')]
        caps = Caps()
        lib.cuBool_GetDeviceCaps.argtypes = [C.POINTER(Caps)]
        lib.cuBool_GetDeviceCaps.restype = C.c_int
        call('cuBool_GetDeviceCaps', C.byref(caps))
        assert caps.cudaSupported, 'CUDA backend required; CPU fallback rejected'
        device = caps.name.decode()
    checks = 0
    failures = []
    try:
        for fixture in fixtures:
            for pending in (False, True):
                for accumulate in (False, True):
                    for alias in ('distinct', 'left', 'right', 'both'):
                        matrices = []
                        try:
                            for pairs in fixture:
                                h = handle()
                                call('cuBool_Matrix_New', C.byref(h), 3, 3)
                                matrices.append(h)
                                if pending:
                                    for u, v in sorted(pairs):
                                        call('cuBool_Matrix_SetElement', h, u, v)
                                elif pairs:
                                    ordered = sorted(pairs)
                                    rows = (index * len(pairs))(*(p[0] for p in ordered))
                                    cols = (index * len(pairs))(*(p[1] for p in ordered))
                                    call('cuBool_Matrix_Build', h, rows, cols, len(pairs), 0)
                            left, right = matrices[:2]
                            a, b = fixture[:2]
                            target, old = matrices[2], fixture[2]
                            if alias in ('left', 'both'):
                                target, old = left, a
                            if alias == 'right':
                                target, old = right, b
                            if alias == 'both':
                                right, b = left, a
                            expected = {(u, w) for u, v in a for x, w in b if v == x}
                            if accumulate:
                                expected |= old
                            call('cuBool_MxM', target, left, right, 8 if accumulate else 0)
                            count = index()
                            call('cuBool_Matrix_Nvals', target, C.byref(count))
                            rows, cols = (index * count.value)(), (index * count.value)()
                            call('cuBool_Matrix_ExtractPairs', target, rows, cols, C.byref(count))
                            actual = set(zip(rows, cols))
                            if actual != expected:
                                if not args.collect_failures:
                                    raise AssertionError((fixture, pending, accumulate, alias, expected, actual))
                                failures.append(dict(fixture=[sorted(p) for p in fixture], pending=pending,
                                    accumulate=accumulate, alias=alias, expected=sorted(expected), actual=sorted(actual)))
                            checks += 1
                        finally:
                            for h in matrices:
                                call('cuBool_Matrix_Free', h)
    finally:
        call('cuBool_Finalize')
    print(json.dumps(dict(library=args.library, backend='gpu' if args.gpu else 'cpu', device=device,
                          passed=checks-len(failures), total=checks, failures=failures, fixtures=len(fixtures),
                          seed=20261103, verification='full pair sets; aliases; accumulate on/off; deferred SetElement and Build')))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
