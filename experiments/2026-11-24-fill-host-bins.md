# GPU CFPQ: batching `fill_nz` bin metadata reads

Status: completed. Date: 2026-11-24.

## Question and hypothesis

The previous `count_nz` change moved bin metadata to host vectors and reduced scalar 4-byte D2H transfers in the luindex trace from 416,415 to 391,073. The fill path still made host reads of device-vector metadata at each bin. This trial makes one host copy of `bin_offset` and `bin_size` after the zero-result early return and passes those vectors to the fill helpers. The expected benefit is fewer repeated scalar metadata reads. This report does not claim a measured fill-specific trace reduction.

## Provenance

- Main repository branch: `research/overnight-count-host-bins`, starting commit `2aa5641f217f9a4f1baff8c20e5a7ccb04f15794`.
- The baseline and candidate use the same CFRA binary SHA-256 `79417c6f4fe0de84a18ea65b488f352f246b50e4f81be0df55762f4411ba9b18`; the cuBool library differs: baseline `f67fe5592a439042571c9629c844551465f211b7487ba8e1da1e141811a0d8e0`, candidate `debb4eeca991b1d3444f864e89affbde0ec3547f64c5b15b1995c18843a9c566`.
- The candidate source was generated from `src/cfra/cuBool/deps/nsparse-um/include/nsparse/detail/fill_nz.h` at the starting commit and compiled as the only replaced CUDA multiply object. The final checked-in source has the same code as the generated candidate header (`build/gpu-fill-host-bins/nsparse/detail/fill_nz.h`, LF SHA-256 `f8652a697cc2a1e4ec02e0f5170873620268b84d96205535b404c4dae89cb8f3`); the checked-in CRLF file SHA-256 is `7c67453186f4fd955c9fd133be067612cf1fffe4e8b44235eeb4a25a35aad459`.
- Luindex prepared input SHA-256: graph `12b3a475bf86953838b29a7a9d20e5b602c9e2fce12e727b42a03499345b65c3`; grammar `179f94c638f4f5945e33f15224d6bae8ac0c1acb03b633939d55c6983b75809a`.
- Results and raw output are local under `data/flpq-all/overnight-2026-11-24/` and `data/flpq-all/gpu-fill-host-bins/`.

## Environment and method

CUDA 12.4 under WSL, NVIDIA RTX 3060 Laptop. Baseline and candidate were run in one alternating sequence after one warmup each, five pairs, 900-second per-process timeout, with no Nsight profiling during timing. The application `AnalysisTime` excludes graph/grammar loading; the paired wall times below are the runner's process duration. Profiling is reported separately.

## Reproduction

The overnight follow-up ran `python3 scripts/check-gpu-empty-fill-alias.py --fill-host-bins`. It built the isolated CUDA multiply object with nvcc 12.4 and relinked it with the count-host-bins build. The command record is local at `data/flpq-all/overnight-2026-11-24/fill-build-commands.json`.

## Correctness and workload

- The 21-configuration count-host-bins catalog passed 21/21 checks; all seven input manifests matched the previous CUDA baseline.
- Baseline and count-host-bins luindex diagnostics each returned 9,677 pairs with 42 iterations and 96,039 CFRA MxM calls, in both plain and Nsight runs. Nsight trace capture/export completed.
- MxM pair regressions, matrix primitive probes, and boundary checks completed successfully; the pizza incremental check returned 1,356 pairs.
- All ten measured luindex runs (five per build) returned 9,677 pairs, exit code 0. No mismatches or timeouts were recorded.

## Results

| Experiment | Baseline median | Candidate median | Paired observation |
|---|---:|---:|---|
| xz, count-host-bins vs empty-fill | 42.726 s | 35.319 s | candidate faster in all five pairs; 1.210× median ratio |
| luindex, fill-host-bins vs count-host-bins | 118.281 s | 113.460 s | candidate faster in all five pairs; 1.042× median ratio |

The fill candidate's samples were 111.508, 110.163, 114.369, 114.146, and 113.460 s; corresponding baseline samples were 118.030, 118.281, 122.671, 116.829, and 120.940 s. Both builds returned the expected 9,677 pairs in every run.

In the earlier count-host-bins trace, Nsight-instrumented `AnalysisTime` was 154.173 s vs 124.374 s, the profiler query counted 50,979 vs 96,039 kernels matching the `count_nz_functor` name, and 416,415 vs 391,073 4-byte D2H copies (baseline vs count candidate). The CFRA iteration/MxM totals and answers matched. The kernel-count change is not explained by this experiment. These measurements are for count-host-bins, not the fill candidate. Full `.nsys-rep` and SQLite files remain local.

## Conclusion and limits

The isolated fill candidate passed its recorded correctness gates and was faster in all five same-input luindex pairs, with a 4.1% median wall-time reduction. This is a promising result from one graph and five pairs, not a broad performance claim. The xz gain belongs to the preceding count-host-bins change, not this fill change. The fill-specific D2H count has not been measured. Keep evaluating per-graph behavior and explain the profiler's count-kernel discrepancy before drawing conclusions from it.
