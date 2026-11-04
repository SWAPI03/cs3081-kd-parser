#!/usr/bin/env bash
# Task 4, step 6: delete one Pod during the load test; Kubernetes restores the replica count.
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/lib.sh
OUT=results/task4_recovery.txt
set_min_replicas 2; wait_for_ready 2
trap 'set_min_replicas 1' EXIT
{
log "starting load (3 min)"
start_load task4_recovery 3m
sleep 40
log "BEFORE:"; kubectl -n app get pods -l app=parser -o wide
victim=$(kubectl -n app get pods -l app=parser -o jsonpath='{.items[0].metadata.name}')
log "deleting $victim"; t0=$(date +%s)
kubectl -n app delete pod "$victim" --wait=false
sleep 3
until [ "$(ready_pods)" -eq 2 ] && ! kubectl -n app get pod "$victim" >/dev/null 2>&1; do sleep 1; done
log "2 replicas Ready again after $(( $(date +%s) - t0 )) s"
log "AFTER:"; kubectl -n app get pods -l app=parser -o wide
kubectl -n app get deploy parser
wait "$LOAD_PID" || true
echo; echo "# Locust result for the whole window"; load_summary results/task4_recovery_stats.csv
} 2>&1 | tee "$OUT"
