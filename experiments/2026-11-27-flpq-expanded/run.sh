set -eu
exec 9>data/flpq-all/overnight-count-host-bins.lock
flock -n 9
out=data/flpq-all/flpq-expanded-2026-11-27
cases=experiments/2026-11-27-flpq-expanded/cases.csv
mkdir "$out"
stage() {
    local name=$1 rc=0
    shift
    echo "START $name $(date -Is)"
    "$@" >"$out/$name.log" 2>&1 || rc=$?
    printf '%s\t%s\n' "$name" "$rc" >>"$out/status.tsv"
    echo "END $name exit=$rc $(date -Is)"
}
export CUDA_VISIBLE_DEVICES=
export LD_LIBRARY_PATH=/root/cfpq-homka/local/lib
stage prepare python3 scripts/prepare-cfg-bench.py --case-list "$cases" --out "$out/inputs"
stage cpu python3 scripts/run-cfg-bench.py --repo /root/cfpq-homka/CFG_bench --inputs "$out/inputs" --out "$out/cpu"
unset CUDA_VISIBLE_DEVICES LD_LIBRARY_PATH
while IFS=, read -r graph grammar; do
    stage "gpu-$graph" python3 scripts/trial-store-column-blocks.py --case-list "$cases" --graph "$graph" --compare-cache --pairs 5 --out "$out/gpu-$graph"
done < <(tr -d '\r"' < "$cases" | tail -n +2)
stage comparison python3 experiments/2026-11-27-flpq-expanded/summarize.py "$out"
perf=/usr/lib/linux-tools/5.15.0-202-generic/perf
for graph in airflow luindex; do
    stage "cpu-profile-$graph" env CUDA_VISIBLE_DEVICES= LD_LIBRARY_PATH=/root/cfpq-homka/local/lib "$perf" record -e cpu-clock:u -F 499 -g -o "$out/$graph.perf" -- /root/cfpq-homka/CFG_bench/build/cfg_bench -t -a CFL_adv -efbl -c "$(realpath "data/flpq-all/cfg-bench-inputs/$graph/case.csv")"
    if test -s "$out/$graph.perf"; then
        stage "cpu-symbols-$graph" "$perf" report -i "$out/$graph.perf" --stdio --no-children
    fi
done
stage gpu-profile-airflow python3 scripts/trial-store-column-blocks.py --graph airflow --compare-cache --profile --out "$out/gpu-profile-airflow"
