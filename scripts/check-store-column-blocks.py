"""Check column-block Boolean products and accumulation against a pair-set oracle."""
import argparse
from contextlib import ExitStack
import ctypes as C
import json
import random
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/flpq-all"
INDEX = C.c_uint
MATRIX = C.c_void_p


def check_blocks(lib, n, left, rights, targets):
    with ExitStack() as cleanup:
        def new(rows, cols):
            matrix = MATRIX()
            lib.cuBool_Matrix_New(C.byref(matrix), rows, cols)
            cleanup.callback(lib.cuBool_Matrix_Free, matrix)
            return matrix

        def build(matrix, pairs):
            if pairs:
                rows, cols = zip(*sorted(pairs))
                lib.cuBool_Matrix_Build(matrix, (INDEX * len(rows))(*rows),
                                        (INDEX * len(cols))(*cols), len(rows), 0)

        def pairs(matrix):
            count = INDEX()
            lib.cuBool_Matrix_Nvals(matrix, C.byref(count))
            rows, cols = (INDEX * count.value)(), (INDEX * count.value)()
            lib.cuBool_Matrix_ExtractPairs(matrix, rows, cols, C.byref(count))
            return set(zip(rows, cols))

        a = new(n, n)
        packed = new(n, n * len(rights))
        product = new(n, n * len(rights))
        build(a, left)
        build(packed, {(u, v + n * i) for i, right in enumerate(rights) for u, v in right})
        lib.cuBool_MxM(product, a, packed, 0)
        for i, (right, old) in enumerate(zip(rights, targets)):
            unpacked, previous, merged, separate, b = [new(n, n) for _ in range(5)]
            build(previous, old)
            build(separate, old)
            build(b, right)
            if left and any(rights):
                lib.cuBool_Matrix_ExtractSubMatrix(unpacked, product, 0, i * n, n, n, 0)
            lib.cuBool_Matrix_EWiseAdd(merged, previous, unpacked, 0)
            lib.cuBool_MxM(separate, a, b, 8)
            expected = old | {(u, w) for u, v in left for x, w in right if v == x}
            if pairs(merged) != expected or pairs(separate) != expected:
                raise ValueError(f"Incorrect product in block {i}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    importer = runpy.run_path(str(ROOT / "scripts/check-gpu-flpq-data.py"))
    hashes = json.loads((DATA / "gpu-fill-host-bins/manifest.json").read_text())["builds"]["trial"]
    importer["verify_hashes"](hashes)
    library = ROOT / next(path for path in hashes if path.endswith("/libcubool.so"))
    lib = C.CDLL(str(library))

    def checked(result, func, args):
        if result:
            raise RuntimeError(f"{func.__name__} returned status {result}")
        return result

    for name, types in {
        "Initialize": [INDEX], "Finalize": [], "Matrix_New": [C.POINTER(MATRIX), INDEX, INDEX],
        "Matrix_Free": [MATRIX], "Matrix_Build": [MATRIX, C.POINTER(INDEX), C.POINTER(INDEX), INDEX, INDEX],
        "Matrix_Nvals": [MATRIX, C.POINTER(INDEX)],
        "Matrix_ExtractPairs": [MATRIX, C.POINTER(INDEX), C.POINTER(INDEX), C.POINTER(INDEX)],
        "Matrix_ExtractSubMatrix": [MATRIX, MATRIX, INDEX, INDEX, INDEX, INDEX, INDEX],
        "Matrix_EWiseAdd": [MATRIX, MATRIX, MATRIX, INDEX], "MxM": [MATRIX, MATRIX, MATRIX, INDEX],
    }.items():
        func = getattr(lib, "cuBool_" + name)
        func.argtypes = types
        func.restype = C.c_int
        func.errcheck = checked
    rng = random.Random(20261124)
    cases = blocks = 0
    lib.cuBool_Initialize(0)
    try:
        for n in (1, 2, 5, 17, 33):
            universe = [(u, v) for u in range(n) for v in range(n)]
            for width in (1, 2, 4, 9):
                for density in (0, .08, .4):
                    def sample():
                        return {pair for pair in universe if rng.random() < density}
                    left = sample()
                    rights = [sample() if i % 3 != 1 else set() for i in range(width)]
                    targets = [sample() for _ in range(width)]
                    check_blocks(lib, n, left, rights, targets)
                    cases += 1
                    blocks += width
    finally:
        lib.cuBool_Finalize()
    result = dict(cases=cases, blocks=blocks, library=str(library), sha256=hashes, seed=20261124)
    with args.out.open("x") as output:
        json.dump(result, output, indent=2)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
