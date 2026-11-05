"""Compile isolated count kernels with one synchronization change per trial."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/2026-11-06-mxm-diagnosis'
BUILD = ROOT / 'build/mxm-diagnosis'
INCLUDE = ROOT / 'src/cfra/cuBool/deps/nsparse-um/include'


def main():
    original = (INCLUDE / 'nsparse/detail/count_nz.cuh').read_text()
    variants = {
        'baseline': original,
        'sync_before_mask': original.replace('auto mask = __activemask();', '__syncwarp();\n  auto mask = __activemask();'),
        'early_mask': original.replace('  T nz = 0;\n\n  for (T j = rpt_a[rid] + i;',
                                      '  T nz = 0;\n  auto stable_mask = __activemask();\n\n  for (T j = rpt_a[rid] + i;')
                              .replace('auto mask = __activemask();', 'auto mask = stable_mask;'),
    }
    results = []
    for name, text in variants.items():
        dest = BUILD / name / 'nsparse/detail/count_nz.cuh'
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
        binary = BUILD / name / 'probe'
        cmd = ['/usr/local/cuda-12.4/bin/nvcc', '-ccbin', '/usr/bin/g++-11', '-std=c++14',
               '-O3', '-arch=sm_86', '--expt-extended-lambda', '--expt-relaxed-constexpr',
               '-I'+str(BUILD / name), '-I'+str(INCLUDE), str(OUT / 'count-probe.cu'), '-o', str(binary)]
        compiled = subprocess.run(cmd, capture_output=True, text=True)
        row = dict(variant=name, command=cmd, compile_exit=compiled.returncode,
                   compile_stderr=compiled.stderr, header_sha256=hashlib.sha256(text.encode()).hexdigest())
        if compiled.returncode == 0:
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
            row.update(exit_code=run.returncode, stdout=run.stdout, stderr=run.stderr,
                       expected='[0,2,3]', passed=run.returncode == 0 and run.stdout.splitlines() == ['[0,2,3]']*5)
        results.append(row)
        (OUT / 'count-results.json').write_text(json.dumps(results, indent=2))
        print(name, row.get('stdout', row['compile_stderr']).strip(), flush=True)
    return 0 if all(r['compile_exit'] == 0 for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
