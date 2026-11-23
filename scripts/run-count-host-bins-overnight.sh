#!/usr/bin/env bash
set -eu
cd -- "$(dirname -- "$0")/.."
out=${1:?Specify a new report directory}
exec 9>data/flpq-all/overnight-count-host-bins.lock
flock -n 9
mkdir -- "$out"
exec > >(tee "$out/queue.log") 2>&1
status=0
stage() {
    local name=$1
    shift
    echo "START $name $(date -Is)"
    local rc=0
    "$@" >"$out/$name.log" 2>&1 || rc=$?
    printf '%s\t%s\n' "$name" "$rc" >>"$out/status.tsv"
    echo "END $name exit=$rc $(date -Is)"
    if (( rc != 0 )); then status=1; fi
}
stage catalog python3 scripts/check-gpu-flpq-data.py --count-host-bins \
    --case-list experiments/2026-11-21-flpq-gpu-suite/benchmark-cases.csv \
    --out "$out/catalog"
stage diagnostics python3 scripts/diagnose-count-host-bins.py "$out/diagnostics"
printf '%s\n' "$status" >"$out/exit-code"
exit "$status"
