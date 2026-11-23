"""Evaluate the next CUDA candidate only after overnight correctness checks."""
import json
import difflib
from pathlib import Path
import runpy
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/flpq-all"
COUNTS = ROOT / "build/gpu-count-host-bins"
TRIAL = ROOT / "build/gpu-fill-host-bins"


def build_fill_candidate(report):
    """Reuse the verified count build and replace only its multiply object."""
    header = ROOT / "src/cfra/cuBool/deps/nsparse-um/include/nsparse/detail/fill_nz.h"
    original = header.read_text()
    code = original
    operator = code.index("  container_t<index_type> operator()")
    helpers, body = code[:operator], code[operator:]
    for name in ("bin_offset", "bin_size"):
        old = f"const container_t<index_type>& {name}"
        if helpers.count(old) != 3:
            raise ValueError(f"Unexpected fill helpers for {name}")
        helpers = helpers.replace(old, f"const thrust::host_vector<index_type>& {name}")
    marker = "    exec_pwarp_row(c_col_idx"
    if body.count(marker) != 1:
        raise ValueError("Unexpected fill dispatch")
    before, dispatch = body.split(marker, 1)
    dispatch, rest = dispatch.split("    return std::move(col_idx);", 1)
    dispatch = dispatch.replace("permutation_buffer, bin_offset, bin_size,",
                                "permutation_buffer, host_bin_offset, host_bin_size,")
    code = ("#include <thrust/host_vector.h>\n" + helpers + before
            + "    const thrust::host_vector<index_type> host_bin_offset = bin_offset;\n"
            + "    const thrust::host_vector<index_type> host_bin_size = bin_size;\n\n"
            + marker + dispatch + "    return std::move(col_idx);" + rest)
    overlay = TRIAL / "nsparse/detail/fill_nz.h"
    overlay.parent.mkdir(parents=True)
    overlay.write_text(code)
    (report / "fill-candidate.patch").write_text("".join(difflib.unified_diff(
        original.splitlines(keepends=True), code.splitlines(keepends=True),
        fromfile=str(header.relative_to(ROOT)), tofile=str(header.relative_to(ROOT)))))
    libdir = COUNTS / "cuBool/cubool"
    flags = []
    for line in (libdir / "CMakeFiles/cubool.dir/flags.make").read_text().splitlines():
        if line.startswith(("CUDA_DEFINES =", "CUDA_INCLUDES =", "CUDA_FLAGS =")):
            flags.extend(shlex.split(line.split("=", 1)[1]))
    obj = TRIAL / "multiply.cu.o"
    trial_lib = TRIAL / "cuBool/cubool/libcubool.so"
    trial_lib.parent.mkdir(parents=True)
    commands = [["/usr/local/cuda-12.4/bin/nvcc", "-ccbin=/usr/bin/g++-11", "-I" + str(TRIAL), *flags,
                 "-c", str(ROOT / "src/cfra/cuBool/cubool/sources/cuda/cuda_matrix_multiply.cu"),
                 "-o", str(obj)]]
    link = shlex.split((libdir / "CMakeFiles/cubool.dir/link.txt").read_text())
    link[link.index("-o") + 1] = str(trial_lib)
    matches = [i for i, token in enumerate(link) if token.endswith("/cuda_matrix_multiply.cu.o")]
    if len(matches) != 1:
        raise ValueError("Expected one CUDA multiply object")
    link[matches[0]] = str(obj)
    commands.append(link)
    (report / "fill-build-commands.json").write_text(json.dumps(commands, indent=2))
    for command in commands:
        subprocess.run(command, cwd=libdir, check=True, timeout=900)
    shutil.copy2(COUNTS / "cfra", TRIAL / "cfra")


def main():
    report = Path(sys.argv[1]).resolve()
    findings = report / "followup-summary.md"

    def note(message):
        with findings.open("a", encoding="utf-8") as log:
            print(message, file=log)

    note("# Overnight follow-up\n")
    try:
        rows = [json.loads(line) for line in (report / "catalog/results.jsonl").read_text().splitlines()]
        runs = {r["run"]: r for r in json.loads((report / "diagnostics/results.json").read_text())}
        if (report / "exit-code").read_text().strip() != "0" or len(rows) != 21 or any(
            r["status"] != "pass" for r in rows
        ):
            note("Stopped after validation failure. See catalog and diagnostic logs.")
            return 1
        if len(runs) != 4 or len({(r["iterations"], r["mxm"]) for r in runs.values()}) != 1:
            note("CFRA workload differs or diagnostic runs are incomplete. Compare iterations and MxM before optimizing.")
            return 1
        importer = runpy.run_path(str(ROOT / "scripts/check-gpu-flpq-data.py"))
        manifests = list((report / "catalog").glob("inputs-*.json"))
        if len(manifests) != 7:
            raise ValueError("Incomplete input manifest set")
        for path in manifests:
            references = [DATA / folder / path.name for folder in ("cuda-baseline", "cuda-baseline-resume")]
            if not any(ref.exists() and json.loads(ref.read_text()) == json.loads(path.read_text())
                       for ref in references):
                raise ValueError(f"No matching input manifest for {path.name}")
        builds = json.loads((DATA / "gpu-count-host-bins/manifest.json").read_text())["builds"]
        importer["verify_hashes"]({**builds["baseline"], **builds["trial"]})
        note("All checks passed and CFRA counts agree in all four diagnostic runs.")
        command = [sys.executable, str(ROOT / "scripts/check-gpu-empty-fill-alias.py")]
        with (report / "xz-pairs.log").open("wb") as log:
            xz = subprocess.run([*command, "--count-host-bins", "--graph", "xz"], stdout=log,
                                stderr=subprocess.STDOUT, timeout=12000)
        if xz.returncode:
            note("xz checks or measurements failed. See xz-pairs.log.")
            return 1
        xz_summary = json.loads((DATA / "gpu-count-host-bins-xz/summary.json").read_text())
        note(f"- xz baseline / count candidate median wall time: {xz_summary['baseline']['median']:.3f} / "
             f"{xz_summary['trial']['median']:.3f} s.")
        note("- Building an isolated fill_nz candidate that batches bin metadata reads after a nonempty product.")
        build_fill_candidate(report)
        with (report / "fill-pairs.log").open("wb") as log:
            fill = subprocess.run([*command, "--fill-host-bins"], stdout=log,
                                  stderr=subprocess.STDOUT, timeout=12000)
        if fill.returncode:
            note("fill_nz candidate failed a gate. See fill-pairs.log.")
            return 1
        result = json.loads((DATA / "gpu-fill-host-bins/summary.json").read_text())
        note(f"- luindex count baseline / fill candidate median wall time: {result['baseline']['median']:.3f} / "
             f"{result['trial']['median']:.3f} s. Review all five pairs before integrating.")
        return 0
    except (OSError, ValueError, subprocess.SubprocessError, KeyError) as error:
        note(f"Stopped: {error}")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
