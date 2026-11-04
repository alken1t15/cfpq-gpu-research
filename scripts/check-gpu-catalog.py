"""GPU-only CFRA correctness on prepared catalog inputs."""
import ctypes as C
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/2026-11-03-gpu-correctness'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    binary = ROOT / 'src/cfra/build-gpu-cuda124/cfra'
    library = ROOT / 'src/cfra/build-gpu-cuda124/cuBool/cubool/libcubool.so'
    lib = C.CDLL(str(library))
    class Caps(C.Structure):
        _fields_ = [('name', C.c_char * 256), ('cudaSupported', C.c_bool), ('managedMem', C.c_bool)] + [
            (name, C.c_int) for name in ('major', 'minor', 'warp', 'globalMemoryKiBs',
                                       'sharedMemoryPerMultiProcKiBs', 'sharedMemoryPerBlockKiBs')]
    lib.cuBool_Initialize.argtypes = [C.c_uint]
    lib.cuBool_GetDeviceCaps.argtypes = [C.POINTER(Caps)]
    assert lib.cuBool_Initialize(0) == 0
    caps = Caps()
    try:
        assert lib.cuBool_GetDeviceCaps(C.byref(caps)) == 0 and caps.cudaSupported
    finally:
        assert lib.cuBool_Finalize() == 0
    manifest = dict(device=caps.name.decode(), cuda_supported=bool(caps.cudaSupported),
        compute_capability=f'{caps.major}.{caps.minor}', memory_KiB=caps.globalMemoryKiBs,
        binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        library_sha256=hashlib.sha256(library.read_bytes()).hexdigest(), cpu_fallback=False)
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    inputs = json.loads((ROOT / 'experiments/2026-11-03-trial-catalog/inputs.json').read_text())
    results = []
    env = dict(os.environ, LD_LIBRARY_PATH=str(library.parent))
    for item in inputs:
        directory = ROOT / 'data/trial-catalog' / item['graph']
        for algo in ('base', 'incremental', 'lazy'):
            cmd = [str(binary), '--graph', str(directory / 'cfra-graph.txt'),
                   '--grammar', str(directory / item['grammar']), '--algo', algo]
            try:
                run = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=180)
                match = re.search(r'#SEdges:\s*(\d+)', run.stdout)
                row = dict(exit_code=run.returncode, actual=int(match[1]) if match else None,
                           stdout=run.stdout, stderr=run.stderr)
            except subprocess.TimeoutExpired:
                row = dict(status='timeout', actual=None)
            row.update(graph=item['graph'], algo=algo, expected=item['expected'])
            row['passed'] = row['actual'] == item['expected'] and row.get('exit_code') == 0
            results.append(row)
            (OUT / 'results.json').write_text(json.dumps(results, indent=2))
            print(item['graph'], algo, row['actual'], row['expected'], row['passed'], flush=True)
    return 0 if all(r['passed'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
