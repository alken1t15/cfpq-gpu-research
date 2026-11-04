"""Build an isolated instrumented cuBool; leave baseline files untouched."""
import hashlib
import json
import os
import re
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/cfra'
OUT = ROOT / 'experiments/2026-11-03-mxm-counters'
BUILD = ROOT / 'build/cpu-mxm-counters'
LIBDIR = SOURCE / 'build-cpu-gcc13/cuBool/cubool'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    baseline = json.loads((ROOT / 'experiments/2026-11-03-cpu-baseline/manifest.json').read_text())
    binary = SOURCE / 'build-cpu-gcc13/cfra'
    assert digest(binary) == baseline['binary_sha256']
    original = SOURCE / 'cuBool/cubool/sources/sequential/sq_matrix.cpp'
    text = original.read_text()
    declaration = '''
#include <chrono>
#include <cstdio>
#include <cstdint>
namespace {
struct MxmCounters {
    uint64_t calls=0, accumulated=0, empty_product=0, empty_target=0, both=0;
    uint64_t empty_union_ns=0, other_union_ns=0, row_visits=0;
    uint64_t product_nnz=0, target_nnz=0;
    ~MxmCounters() {
        std::fprintf(stderr, "MXM_COUNTERS {\\"calls\\":%llu,\\"accumulated\\":%llu,"
            "\\"empty_product\\":%llu,\\"empty_target\\":%llu,\\"both\\":%llu,"
            "\\"empty_union_ns\\":%llu,\\"other_union_ns\\":%llu,"
            "\\"row_visits\\":%llu,\\"product_nnz\\":%llu,\\"target_nnz\\":%llu}\\n",
            (unsigned long long)calls, (unsigned long long)accumulated,
            (unsigned long long)empty_product, (unsigned long long)empty_target,
            (unsigned long long)both, (unsigned long long)empty_union_ns,
            (unsigned long long)other_union_ns, (unsigned long long)row_visits,
            (unsigned long long)product_nnz, (unsigned long long)target_nnz);
    }
} mxm_counters;
}
'''
    text = text.replace('namespace cubool {', declaration + '\nnamespace cubool {', 1)
    needle = '        sq_spgemm(a->mData, b->mData, out);'
    assert text.count(needle) == 1
    text = text.replace(needle, '        ++mxm_counters.calls;\n' + needle)
    needle = '            sq_ewiseadd(this->mData, out, out2);'
    assert text.count(needle) == 1
    text = text.replace(needle, '''            ++mxm_counters.accumulated;
            bool empty_product = out.nvals == 0;
            bool empty_target = this->mData.nvals == 0;
            mxm_counters.empty_product += empty_product;
            mxm_counters.empty_target += empty_target;
            mxm_counters.both += empty_product && empty_target;
            mxm_counters.row_visits += out.nrows;
            mxm_counters.product_nnz += out.nvals;
            mxm_counters.target_nnz += this->mData.nvals;
            auto union_start = std::chrono::steady_clock::now();
''' + needle + '''
            auto union_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now() - union_start).count();
            if (empty_product || empty_target) mxm_counters.empty_union_ns += union_ns;
            else mxm_counters.other_union_ns += union_ns;
''')
    generated = OUT / 'instrumented-sq_matrix.cpp'
    generated.write_text(text)
    flags_file = LIBDIR / 'CMakeFiles/cubool.dir/flags.make'
    flags = []
    for line in flags_file.read_text().splitlines():
        if line.startswith(('CXX_DEFINES =', 'CXX_INCLUDES =', 'CXX_FLAGS =')):
            flags += shlex.split(line.split('=', 1)[1])
    obj = BUILD / 'instrumented-sq_matrix.o'
    commands = [['g++-13', *flags, '-c', str(generated), '-o', str(obj)]]
    objects = [p for p in (LIBDIR / 'CMakeFiles/cubool.dir').rglob('*.o') if p.name != 'sq_matrix.cpp.o']
    commands.append(['g++-13', '-shared', '-Wl,-soname,libcubool.so', *map(str, objects), str(obj),
                     '-o', str(BUILD / 'libcubool.so')])
    (OUT / 'build-commands.json').write_text(json.dumps(commands, indent=2))
    library_hash = digest(LIBDIR / 'libcubool.so')
    for command in commands:
        subprocess.run(command, check=True)
    env = dict(os.environ, LD_LIBRARY_PATH=str(BUILD))
    command = [str(binary), '--graph', str(ROOT / 'data/catalog-v6/luindex/cfra-adapted.txt'),
               '--grammar', str(ROOT / 'data/catalog-v6/luindex/java_points_to.cnf'),
               '--algo', 'incremental', '--cpu']
    run = subprocess.run(command, env=env, capture_output=True, text=True, timeout=120)
    (OUT / 'query.stdout').write_text(run.stdout)
    (OUT / 'query.stderr').write_text(run.stderr)
    assert run.returncode == 0 and '#SEdges: 9677\n' in run.stdout
    match = re.search(r'^MXM_COUNTERS (.+)$', run.stderr, re.M)
    assert match, run.stderr
    counts = json.loads(match[1])
    (OUT / 'counters.json').write_text(json.dumps(counts, indent=2))
    assert digest(binary) == baseline['binary_sha256'] and digest(LIBDIR / 'libcubool.so') == library_hash
    (OUT / 'manifest.json').write_text(json.dumps(dict(binary_sha256=digest(binary),
        baseline_library_sha256=library_hash, instrumented_library_sha256=digest(BUILD / 'libcubool.so'),
        original_source_sha256=digest(original), instrumented_source_sha256=digest(generated),
        command=command, LD_LIBRARY_PATH=str(BUILD), exit_code=run.returncode), indent=2))
    print(json.dumps(counts, indent=2))


if __name__ == '__main__':
    main()
