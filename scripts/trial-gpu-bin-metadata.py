"""Generate and build a metadata-only trial without modifying production headers."""
import difflib
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/2026-11-06-bin-metadata'
BUILD = ROOT / 'build/gpu-bin-metadata'
LIB = ROOT / 'build/gpu-row-mask-integrated/cuBool/cubool'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    before = digest(LIB / 'libcubool.so')
    patches = []
    for name in ('count_nz.h', 'fill_nz.h'):
        source = ROOT / 'src/cfra/cuBool/deps/nsparse-um/include/nsparse/detail' / name
        original = source.read_text()
        changed = original.replace('#include <thrust/device_vector.h>', '#include <thrust/device_vector.h>\n#include <thrust/host_vector.h>')
        # Only launch-helper parameters become host references. Device binning
        # still uses the original device vectors and captures their pointers.
        changed = changed.replace('const container_t<index_type>& bin_offset', 'const thrust::host_vector<index_type>& bin_offset')
        changed = changed.replace('const container_t<index_type>& bin_size', 'const thrust::host_vector<index_type>& bin_size')
        changed = changed.replace('thrust::host_vector<index_type> bin_offset,', 'const thrust::host_vector<index_type>& bin_offset,')
        changed = changed.replace('thrust::host_vector<index_type> bin_size,', 'const thrust::host_vector<index_type>& bin_size,')
        marker = '    exec_pwarp_row(c_col_idx'
        assert changed.count(marker) == 1
        changed = changed.replace(marker,
            '    // Binning is complete before these synchronous host copies.\n'
            '    const thrust::host_vector<index_type> host_bin_offset = bin_offset;\n'
            '    const thrust::host_vector<index_type> host_bin_size = bin_size;\n\n' + marker)
        start = changed.index(marker)
        changed = changed[:start] + changed[start:].replace('permutation_buffer, bin_offset, bin_size,',
                                                           'permutation_buffer, host_bin_offset, host_bin_size,')
        target = BUILD / 'nsparse/detail' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(changed)
        patches.extend(difflib.unified_diff(original.splitlines(True), changed.splitlines(True),
            fromfile='a/deps/nsparse-um/include/nsparse/detail/' + name,
            tofile='b/deps/nsparse-um/include/nsparse/detail/' + name))
    (OUT / 'metadata.patch').write_text(''.join(patches))
    flags = []
    for line in (LIB / 'CMakeFiles/cubool.dir/flags.make').read_text().splitlines():
        if line.startswith(('CUDA_DEFINES =', 'CUDA_INCLUDES =', 'CUDA_FLAGS =')):
            flags += shlex.split(line.split('=', 1)[1])
    obj = BUILD / 'multiply.cu.o'
    command = ['/usr/local/cuda-12.4/bin/nvcc', '-ccbin=/usr/bin/g++-11', '-I' + str(BUILD),
               *flags, '-c', str(ROOT / 'src/cfra/cuBool/cubool/sources/cuda/cuda_matrix_multiply.cu'), '-o', str(obj)]
    link = shlex.split((LIB / 'CMakeFiles/cubool.dir/link.txt').read_text())
    link[link.index('-o') + 1] = str(BUILD / 'libcubool.so')
    for i, token in enumerate(link):
        if token.endswith('sources/cuda/cuda_matrix_multiply.cu.o'):
            link[i] = str(obj)
        elif token.endswith('.o') and not token.startswith('/'):
            link[i] = str(LIB / token)
    (OUT / 'build-commands.json').write_text(json.dumps([command, link], indent=2))
    for cmd in (command, link):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        with (OUT / 'build.log').open('a') as log:
            log.write(r.stdout + r.stderr)
        if r.returncode:
            raise RuntimeError(r.returncode)
    assert before == digest(LIB / 'libcubool.so')
    (OUT / 'manifest.json').write_text(json.dumps(dict(source_head=subprocess.check_output(
        ['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
        baseline_sha256=before, trial_sha256=digest(BUILD / 'libcubool.so')), indent=2))


if __name__ == '__main__':
    main()
