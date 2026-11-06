"""Build one isolated multiply object with an explicit four-lane mask."""
import difflib
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/2026-11-06-fixed-mask'
BUILD = ROOT / 'build/gpu-fixed-mask'
LIB = ROOT / 'build/gpu-cubool-pr19/cuBool/cubool'


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--alias', action='store_true')
    parser.add_argument('--tile', action='store_true')
    args = parser.parse_args()
    if args.alias and args.tile:
        parser.error('Evaluate alias and tile changes separately')
    OUT.mkdir(parents=True, exist_ok=True)
    relative = 'nsparse/detail/count_nz.cuh'
    path = ROOT / 'src/cfra/cuBool/deps/nsparse-um/include' / relative
    original = path.read_text()
    assert original.count('auto mask = __activemask();') == 1
    changed = original.replace('auto mask = __activemask();',
        'static_assert(pwarp > 0 && pwarp <= 32 && (pwarp & (pwarp - 1)) == 0);\n'
        '  // All lanes of a row either return together or reach this reduction.\n'
        '  const unsigned mask = (0xffffffffu >> (32 - pwarp))\n'
        '                        << ((threadIdx.x % 32) / pwarp * pwarp);')
    changed = changed.replace('__shfl_xor_sync(mask, nz, j)', '__shfl_xor_sync(mask, nz, j, pwarp)')
    header = BUILD / relative
    header.parent.mkdir(parents=True, exist_ok=True)
    header.write_text(changed)
    (OUT / 'fixed-mask.patch').write_text(''.join(difflib.unified_diff(
        original.splitlines(True), changed.splitlines(True),
        fromfile='a/deps/nsparse-um/include/'+relative, tofile='b/deps/nsparse-um/include/'+relative)))
    before = digest(LIB / 'libcubool.so')
    flags = []
    for line in (LIB / 'CMakeFiles/cubool.dir/flags.make').read_text().splitlines():
        if line.startswith(('CUDA_DEFINES =', 'CUDA_INCLUDES =', 'CUDA_FLAGS =')):
            flags += shlex.split(line.split('=', 1)[1])
    source = ROOT / 'src/cfra/cuBool/cubool/sources/cuda/cuda_matrix_multiply.cu'
    target = ROOT / 'build/gpu-alias-trial' if args.alias else ROOT / 'build/gpu-group-trial' if args.tile else BUILD
    target.mkdir(parents=True, exist_ok=True)
    if args.tile:
        tile_path = ROOT / 'src/cfra/cuBool/deps/nsparse-um/include/nsparse/detail/fill_nz.cuh'
        tile_original = tile_path.read_text()
        tile_changed = tile_original.replace('  if (rid >= n_rows)\n    return;',
            '  auto row_group = cooperative_groups::tiled_partition<pwarp>(cooperative_groups::this_thread_block());\n\n'
            '  if (rid >= n_rows)\n    return;')
        tile_changed = tile_changed.replace('tiled_partition<pwarp>(this_thread_block()),', 'row_group,')
        assert tile_changed != tile_original and tile_changed.count('auto row_group =') == 1
        generated = target / 'nsparse/detail/fill_nz.cuh'
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_text(tile_changed)
        (OUT / 'tile-before-return.patch').write_text(''.join(difflib.unified_diff(
            tile_original.splitlines(True), tile_changed.splitlines(True),
            fromfile='a/deps/nsparse-um/include/nsparse/detail/fill_nz.cuh',
            tofile='b/deps/nsparse-um/include/nsparse/detail/fill_nz.cuh')))
    if args.alias:
        text = source.read_text()
        marker = '        if (!accumulate) {'
        replacement = '''        if (!accumulate && (this == a || this == b)) {
            CudaMatrix temporary(M, N, mInstance);
            temporary.multiply(aBase, bBase, false, checkTime);
            mMatrixImpl = std::move(temporary.mMatrixImpl);
            return;
        }

'''+marker
        assert text.count(marker) == 1
        modified = text.replace(marker, replacement)
        source = target / 'cuda_matrix_multiply.cu'
        source.write_text(modified)
        (OUT / 'alias.patch').write_text(''.join(difflib.unified_diff(
            text.splitlines(True), modified.splitlines(True),
            fromfile='a/cubool/sources/cuda/cuda_matrix_multiply.cu',
            tofile='b/cubool/sources/cuda/cuda_matrix_multiply.cu')))
    obj = target / 'multiply.cu.o'
    command = ['/usr/local/cuda-12.4/bin/nvcc', '-ccbin=/usr/bin/g++-11',
               '-I'+str(target), '-I'+str(BUILD), *flags, '-lineinfo', '-c', str(source), '-o', str(obj)]
    link = shlex.split((LIB / 'CMakeFiles/cubool.dir/link.txt').read_text())
    link[link.index('-o')+1] = str(target / 'libcubool.so')
    for i, token in enumerate(link):
        if token.endswith('sources/cuda/cuda_matrix_multiply.cu.o'):
            link[i] = str(obj)
        elif token.endswith('.o') and not token.startswith('/'):
            link[i] = str(LIB / token)
    prefix = 'alias-' if args.alias else 'tile-' if args.tile else ''
    (OUT / (prefix+'build-commands.json')).write_text(json.dumps([command, link], indent=2))
    for cmd in (command, link):
        subprocess.run(cmd, check=True)
    assert before == digest(LIB / 'libcubool.so')
    (OUT / (prefix+'manifest.json')).write_text(json.dumps(dict(baseline_sha256=before,
        trial_sha256=digest(target / 'libcubool.so'), header_sha256=digest(header),
        source_sha=subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()), indent=2))


if __name__ == '__main__':
    main()
