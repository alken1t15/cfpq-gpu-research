"""Collect CUDA-only Nsight traces; keep binary artifacts under build/."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/2026-11-06-cuda-trace'
LOCAL = ROOT / 'build/gpu-cuda-trace'
BUILD = ROOT / 'build/gpu-row-mask-integrated'


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'small'
    if mode not in ('small', 'luindex'):
        raise ValueError(mode)
    OUT.mkdir(parents=True, exist_ok=True)
    LOCAL.mkdir(parents=True, exist_ok=True)
    record = OUT / (mode + '-manifest.json')
    if record.exists():
        raise RuntimeError('Archive previous artifacts before repeating')
    library = BUILD / 'cuBool/cubool/libcubool.so'
    env = dict(os.environ, LD_LIBRARY_PATH=str(library.parent))
    if mode == 'small':
        app = [str(BUILD / 'cuBool/cubool/tests/test_matrix_mxm'),
               '--gtest_filter=cuBool_Matrix.MultiplyDivergentSmallRows']
    else:
        data = ROOT / 'data/trial-catalog/luindex'
        app = [str(BUILD / 'cfra'), '--graph', str(data / 'cfra-graph.txt'),
               '--grammar', str(data / 'java_points_to.cnf'), '--algo', 'incremental']
    prefix = LOCAL / mode
    cmd = ['nsys', 'profile', '--trace=cuda', '--sample=none', '--cpuctxsw=none',
           '--output=' + str(prefix)]
    if mode == 'luindex':
        cmd += ['--duration=30', '--kill=sigterm']
    cmd += app
    metadata = dict(mode=mode, command=cmd, source_head=subprocess.check_output(
        ['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
        library_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),
        app_sha256=hashlib.sha256(Path(app[0]).read_bytes()).hexdigest())
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=240, env=env)
    (OUT / (mode + '.stdout')).write_text(result.stdout)
    (OUT / (mode + '.stderr')).write_text(result.stderr)
    metadata['exit_code'] = result.returncode
    record.write_text(json.dumps(metadata, indent=2))
    print(mode, 'profile exit', result.returncode, flush=True)
    report = prefix.with_suffix('.nsys-rep')
    if not report.exists():
        return 1
    stats = ['nsys', 'stats', '--report=cuda_api_sum,cuda_gpu_kern_sum,cuda_gpu_mem_time_sum',
             '--format=csv', str(report)]
    r = subprocess.run(stats, capture_output=True, text=True, timeout=180, env=env)
    (OUT / (mode + '-stats.csv')).write_text(r.stdout)
    (OUT / (mode + '-stats.stderr')).write_text(r.stderr)
    metadata.update(stats_command=stats, stats_exit_code=r.returncode,
                    report_sha256=hashlib.sha256(report.read_bytes()).hexdigest())
    record.write_text(json.dumps(metadata, indent=2))
    return r.returncode


if __name__ == '__main__':
    raise SystemExit(main())
