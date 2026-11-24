#!/usr/bin/env bash
set -eu
cd -- "$(dirname -- "$0")/.."
out=${1:?Specify a new report directory}
cases=experiments/2026-11-21-flpq-gpu-suite/benchmark-cases.csv
exec 9>data/flpq-all/overnight-count-host-bins.lock
flock -n 9
mkdir -- "$out"
status=0
stage() {
    local name=$1
    shift
    local rc=0
    echo "START $name $(date -Is)"
    "$@" >"$out/$name.log" 2>&1 || rc=$?
    printf '%s\t%s\n' "$name" "$rc" >>"$out/status.tsv"
    echo "END $name exit=$rc $(date -Is)"
    if (( rc != 0 )); then status=1; fi
}
stage report python3 scripts/check-gpu-flpq-data.py --fill-host-bins --benchmark \
    --case-list "$cases" --out "$out/report"
while IFS=, read -r graph grammar; do
    stage "cache-$graph" python3 scripts/trial-store-column-blocks.py --graph "$graph" \
        --compare-cache --pairs 15 --out "$out/cache-$graph"
done < <(tr -d '\r' <"$cases" | tail -n +2)
stage cache-lusearch python3 scripts/trial-store-column-blocks.py --graph lusearch \
    --compare-cache --pairs 15 --out "$out/cache-lusearch"
printf '%s\n' "$status" >"$out/exit-code"
exit "$status"
