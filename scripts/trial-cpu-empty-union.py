"""Isolated CPU fast-path trial; baseline source and shared library stay intact."""
import hashlib
import json
import os
import re
import shlex
import statistics
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src/cfra'
OUT = ROOT / 'experiments/2026-11-03-empty-union-trial'
BUILD = ROOT / 'build/cpu-empty-union-trial'
LIB = SRC / 'build-cpu-gcc13/cuBool/cubool'


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    original = SRC / 'cuBool/cubool/sources/sequential/sq_matrix.cpp'
    text = original.read_text()
    needle = '            this->allocateStorage();\n            sq_ewiseadd(this->mData, out, out2);'
    assert text.count(needle) == 1
    text = text.replace(needle, '''            this->allocateStorage();
            if (out.nvals == 0) return;
            if (this->mData.nvals == 0) {
                this->mData = std::move(out);
                return;
            }
            sq_ewiseadd(this->mData, out, out2);''')
    generated = OUT / 'optimized-sq_matrix.cpp'
    generated.write_text(text)
    flags = []
    for line in (LIB / 'CMakeFiles/cubool.dir/flags.make').read_text().splitlines():
        if line.startswith(('CXX_DEFINES =', 'CXX_INCLUDES =', 'CXX_FLAGS =')):
            flags += shlex.split(line.split('=', 1)[1])
    obj = BUILD / 'optimized-sq_matrix.o'
    objects = [p for p in (LIB / 'CMakeFiles/cubool.dir').rglob('*.o') if p.name != 'sq_matrix.cpp.o']
    commands = [['g++-13', *flags, '-c', str(generated), '-o', str(obj)],
                ['g++-13', '-shared', '-Wl,-soname,libcubool.so', *map(str, objects), str(obj),
                 '-o', str(BUILD / 'libcubool.so')]]
    (OUT / 'build-commands.json').write_text(json.dumps(commands, indent=2))
    for cmd in commands:
        subprocess.run(cmd, check=True)
    envs = {'baseline': dict(os.environ, LD_LIBRARY_PATH=str(LIB)),
            'fast_path': dict(os.environ, LD_LIBRARY_PATH=str(BUILD))}
    # Reuse all declared edge/diagnostic tests without overwriting old artifacts.
    regression = {}
    for script, artifact in [('check-small-cpu.py', None),
        ('check-edge-cases.py', ROOT / 'experiments/2026-11-03-edge-cases/results.json'),
        ('check-template-warning.py', ROOT / 'experiments/2026-11-03-template-warning/results.json')]:
        saved = artifact.read_bytes() if artifact else None
        try:
            run = subprocess.run(['python3', str(ROOT / 'scripts' / script)], env=envs['fast_path'],
                                 capture_output=True, text=True, timeout=120)
            regression[script] = dict(exit_code=run.returncode, stdout=run.stdout, stderr=run.stderr)
            if artifact:
                (OUT / (script + '.results.json')).write_bytes(artifact.read_bytes())
            assert run.returncode == 0, run.stdout + run.stderr
        finally:
            if artifact:
                artifact.write_bytes(saved)
    (OUT / 'regression.json').write_text(json.dumps(regression, indent=2))
    binary = SRC / 'build-cpu-gcc13/cfra'
    graph = ROOT / 'data/catalog-v6/luindex/cfra-adapted.txt'
    grammar = ROOT / 'data/catalog-v6/luindex/java_points_to.cnf'
    manifest = dict(binary_sha256=digest(binary), baseline_library_sha256=digest(LIB / 'libcubool.so'),
        trial_library_sha256=digest(BUILD / 'libcubool.so'), original_source_sha256=digest(original),
        trial_source_sha256=digest(generated), graph_sha256=digest(graph), grammar_sha256=digest(grammar),
        warmup_per_variant=1, measured_per_variant=5, timeout_seconds=120,
        order='baseline/fast_path on even rounds, reversed on odd rounds; sequential fresh processes')
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    records = []
    for repeat in range(6):
        order = ('baseline', 'fast_path') if repeat % 2 == 0 else ('fast_path', 'baseline')
        for variant in order:
            begin = time.perf_counter()
            run = subprocess.run([str(binary), '--graph', str(graph), '--grammar', str(grammar),
                '--algo', 'incremental', '--cpu'], env=envs[variant], capture_output=True, text=True, timeout=120)
            wall = time.perf_counter() - begin
            count = re.search(r'#SEdges:\s*(\d+)', run.stdout)
            analysis = re.search(r'AnalysisTime:\s*([\d.eE+-]+)', run.stdout)
            row = dict(variant=variant, repeat=repeat, warmup=repeat == 0,
                wall_seconds=wall, analysis_seconds=float(analysis[1]) if analysis else None,
                pairs=int(count[1]) if count else None, exit_code=run.returncode,
                stdout=run.stdout, stderr=run.stderr)
            records.append(row)
            (OUT / 'raw.json').write_text(json.dumps(records, indent=2))
            assert run.returncode == 0 and row['pairs'] == 9677 and not run.stderr
            print(repeat, variant, round(wall, 3), row['pairs'], flush=True)
    summary = {}
    for variant in envs:
        summary[variant] = {}
        for key in ('wall_seconds', 'analysis_seconds'):
            values = [r[key] for r in records if not r['warmup'] and r['variant'] == variant]
            summary[variant][key] = dict(n=len(values), median=statistics.median(values),
                minimum=min(values), maximum=max(values), sample_stdev=statistics.stdev(values))
    summary['wall_speedup_ratio_of_medians'] = summary['baseline']['wall_seconds']['median'] / summary['fast_path']['wall_seconds']['median']
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2))
    assert digest(LIB / 'libcubool.so') == manifest['baseline_library_sha256']


if __name__ == '__main__':
    main()
