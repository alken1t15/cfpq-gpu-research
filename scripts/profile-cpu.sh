#!/usr/bin/env bash
set -euo pipefail
workspace=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
out="$workspace/experiments/2026-11-03-cpu-profile"
perf_bin=/usr/lib/linux-tools/5.15.0-202-generic/perf
mkdir -p "$out"
"$perf_bin" record -e cpu-clock:u -F 199 --call-graph dwarf,8192 \
  -o "$out/perf.data" -- \
  "$workspace/src/cfra/build-cpu-gcc13/cfra" \
  --graph "$workspace/data/catalog-v6/luindex/cfra-adapted.txt" \
  --grammar "$workspace/data/catalog-v6/luindex/java_points_to.cnf" \
  --algo incremental --cpu > "$out/query.stdout" 2> "$out/record.stderr"
grep -qx '#SEdges: 9677' "$out/query.stdout"
"$perf_bin" report -i "$out/perf.data" --stdio --no-children \
  --sort dso,symbol --percent-limit 0.5 > "$out/self-report.txt"
"$perf_bin" report -i "$out/perf.data" --stdio --children \
  --sort dso,symbol --percent-limit 1 > "$out/children-report.txt"
"$perf_bin" report -i "$out/perf.data" --stdio --no-children \
  --sort dso --percent-limit 0 > "$out/dso-report.txt"
