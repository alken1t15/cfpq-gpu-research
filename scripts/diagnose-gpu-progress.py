"""Build an isolated host progress logger and run pizza then bounded luindex."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'experiments/2026-11-09-gpu-progress'
BUILD = ROOT/'build/gpu-progress'
BASE = ROOT/'build/gpu-row-mask-integrated'


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    if (OUT/'runs.json').exists():
        raise RuntimeError('Preserve previous results before rerun')
    source = ROOT/'src/cfra/src/incremental_algo/incremental_algo.cpp'
    original = source.read_text()
    changed = original.replace('#include <stdexcept>', '#include <stdexcept>\n#include <iostream>')
    marker = '    int iter = 0;'
    logger = '''    uint64_t diagnostic_calls = 0;
    int iter = 0;
    auto progress = [&](const char* event, const char* operation, uint64_t delta) {
        const auto seconds = std::chrono::duration<double>(
            std::chrono::high_resolution_clock::now() - t0).count();
        std::cerr << "PROGRESS time=" << seconds << " iter=" << iter
                  << " calls=" << diagnostic_calls << " event=" << event
                  << " op=" << operation << " delta=" << delta << std::endl;
    };
    progress("initialized", "none", 0);'''
    changed = changed.replace(marker, logger)
    changed = changed.replace('        iter++;', '        iter++;\n        progress("iteration_begin", "none", 0);')
    changed = changed.replace('        if (dm_total == 0)', '        progress("iteration_end", "none", dm_total);\n        if (dm_total == 0)')
    pattern = r'(?m)^( +)(CB_CHECK\((cuBool_(?:MxM|Matrix_EWiseAdd|Matrix_EWiseMulInverted))\([^\n]+\);)$'
    def wrap(m):
        indent, call, op = m.groups()
        return (indent + '++diagnostic_calls;\n' + indent + 'if (diagnostic_calls % 250 == 0) progress("call_begin", "'+op+'", 0);\n' +
                indent + call + '\n' + indent + 'if (diagnostic_calls % 250 == 0) progress("call_end", "'+op+'", 0);')
    changed, count = re.subn(pattern, wrap, changed)
    assert count == 5, count
    generated = BUILD/'incremental_algo.cpp'
    generated.write_text(changed)
    (OUT/'instrumentation.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True), changed.splitlines(True),
        fromfile='a/src/incremental_algo/incremental_algo.cpp', tofile='b/src/incremental_algo/incremental_algo.cpp')))
    flags = []
    for line in (BASE/'CMakeFiles/cfra.dir/flags.make').read_text().splitlines():
        if line.startswith(('CXX_DEFINES =', 'CXX_INCLUDES =', 'CXX_FLAGS =')):
            flags += shlex.split(line.split('=', 1)[1])
    obj = BUILD/'incremental.o'
    compile_cmd = ['/usr/bin/g++-13', *flags, '-I'+str(source.parent), '-c', str(generated), '-o', str(obj)]
    link = shlex.split((BASE/'CMakeFiles/cfra.dir/link.txt').read_text())
    link[link.index('-o')+1] = str(BUILD/'cfra')
    for i, token in enumerate(link):
        if token.endswith('src/incremental_algo/incremental_algo.cpp.o'):
            link[i] = str(obj)
        elif token.endswith(('.o', '.so')) and not token.startswith('/'):
            link[i] = str(BASE/token)
    manifest = dict(source_head=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
                    source_sha256=digest(source), baseline_binary_sha256=digest(BASE/'cfra'),
                    library_sha256=digest(BASE/'cuBool/cubool/libcubool.so'), build_commands=[compile_cmd, link])
    for cmd in (compile_cmd, link):
        r = subprocess.run(cmd,capture_output=True,text=True,timeout=120)
        with (OUT/'build.log').open('a') as log:
            log.write(r.stdout+r.stderr)
        assert r.returncode == 0, r.stderr
    manifest['diagnostic_binary_sha256'] = digest(BUILD/'cfra')
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    rows = []
    for graph, grammar, expected, limit in [('pizza','nested_parentheses_subClassOf_type.cnf',1356,120),
                                            ('luindex','java_points_to.cnf',9677,300)]:
        data = ROOT/'data/trial-catalog'/graph
        cmd = [str(BUILD/'cfra'),'--graph',str(data/'cfra-graph.txt'),'--grammar',str(data/grammar),'--algo','incremental']
        print('START',graph,flush=True)
        begin = time.monotonic()
        samples = []
        with (OUT/(graph+'.stdout')).open('w') as stdout, (OUT/(graph+'.progress')).open('w') as stderr:
            proc = subprocess.Popen(cmd,stdout=stdout,stderr=stderr,env=dict(os.environ,LD_LIBRARY_PATH=str(BASE/'cuBool/cubool')))
            status = 'completed'
            while proc.poll() is None:
                remaining = limit-(time.monotonic()-begin)
                if remaining <= 0:
                    status = 'timeout'
                    proc.kill()
                    proc.wait()
                    break
                try:
                    proc.wait(timeout=min(10,remaining))
                except subprocess.TimeoutExpired:
                    s = subprocess.run(['nvidia-smi','--query-gpu=utilization.gpu,clocks.sm,power.draw,temperature.gpu,memory.used','--format=csv,noheader'],capture_output=True,text=True,timeout=5)
                    samples.append(dict(elapsed=time.monotonic()-begin,exit_code=s.returncode,stdout=s.stdout,stderr=s.stderr))
                    (OUT/(graph+'-gpu.json')).write_text(json.dumps(samples,indent=2))
        output = (OUT/(graph+'.stdout')).read_text()
        match = re.search(r'#SEdges:\s*(\d+)',output)
        row = dict(graph=graph,command=cmd,status=status,exit_code=proc.returncode,wall_seconds=time.monotonic()-begin,
                   actual=int(match[1]) if match else None,expected=expected)
        rows.append(row)
        (OUT/'runs.json').write_text(json.dumps(rows,indent=2))
        print('END',row,flush=True)
        if graph == 'pizza' and (row['actual'] != expected or proc.returncode):
            return 1
    assert digest(source) == manifest['source_sha256']
    assert digest(BASE/'cfra') == manifest['baseline_binary_sha256']
    assert digest(BASE/'cuBool/cubool/libcubool.so') == manifest['library_sha256']
    return 0


if __name__ == '__main__':
    main()
