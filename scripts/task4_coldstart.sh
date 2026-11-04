#!/usr/bin/env bash
# Task 4, step 7: delete all Pods, three times. Time from Pod creation to Ready, log evidence of
# the model download, and evidence that the Service has no ready endpoints while loading.
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/lib.sh
OUT=results/task4_coldstart.txt
set_min_replicas 2; wait_for_ready 2
trap 'set_min_replicas 1' EXIT
: > results/task4_coldstart_logs.txt
times=()
{
for run in 1 2 3; do
  log "run $run: deleting all Pods"
  kubectl -n app delete pod -l app=parser --wait=false
  sleep 4
  echo "# endpoints while the new Pods load the model (no ready addresses expected):"
  kubectl -n app get endpointslices -l kubernetes.io/service-name=parser \
    -o jsonpath='{range .items[*].endpoints[*]}{.targetRef.name} ready={.conditions.ready}{"\n"}{end}'
  kubectl -n app get endpoints parser
  wait_for_ready 2
  for pod in $(kubectl -n app get pods -l app=parser -o name); do
    created=$(kubectl -n app get "$pod" -o jsonpath='{.metadata.creationTimestamp}')
    ready=$(kubectl -n app get "$pod" -o jsonpath='{.status.conditions[?(@.type=="Ready")].lastTransitionTime}')
    secs=$(( $(date -d "$ready" +%s) - $(date -d "$created" +%s) ))
    echo "run $run  $(basename "$pod")  created $created  ready $ready  -> ${secs} s"
    times+=("$secs")
    { echo "===== run $run $(basename "$pod")"; kubectl -n app logs "$pod" | head -n 12; } >> results/task4_coldstart_logs.txt
  done
done
median=$(printf '%s\n' "${times[@]}" | sort -n | awk '{a[NR]=$1} END {print (NR%2 ? a[(NR+1)/2] : (a[NR/2]+a[NR/2+1])/2)}')
echo; echo "creation -> Ready over 3 runs (6 Pods): ${times[*]} s; median ${median} s"
} 2>&1 | tee "$OUT"
