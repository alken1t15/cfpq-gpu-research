#!/usr/bin/env bash
set -euo pipefail
workspace=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
out="$workspace/experiments/2026-11-06-gpu-repeatability"
local_out="$workspace/build/gpu-host-profile"
perf_bin=/usr/lib/linux-tools/5.15.0-202-generic/perf
mkdir -p "$local_out"
export LD_LIBRARY_PATH="$workspace/build/gpu-row-mask-integrated/cuBool/cubool"
set +e
"$perf_bin" record -e cpu-clock:u -F 99 --call-graph dwarf,4096 \
  -o "$local_out/perf.data" -- timeout --signal=TERM 60s \
  "$workspace/build/gpu-row-mask-integrated/cfra" \
  --graph "$workspace/data/trial-catalog/luindex/cfra-graph.txt" \
  --grammar "$workspace/data/trial-catalog/luindex/java_points_to.cnf" \
  --algo incremental > "$out/host-profile.stdout" 2> "$out/host-profile.stderr"
status=$?
set -e
printf '%s\n' "$status" > "$out/host-profile.exit"
"$perf_bin" report -i "$local_out/perf.data" --stdio --no-children \
  --sort dso,symbol --percent-limit 0.5 > "$out/host-self-report.txt" 2> "$out/host-report.stderr"
"$perf_bin" report -i "$local_out/perf.data" --stdio --children \
  --sort dso,symbol --percent-limit 2 > "$out/host-children-report.txt" 2>> "$out/host-report.stderr"
"$perf_bin" report -i "$local_out/perf.data" --stdio --no-children \
  --sort dso --percent-limit 0 > "$out/host-dso-report.txt" 2>> "$out/host-report.stderr"
