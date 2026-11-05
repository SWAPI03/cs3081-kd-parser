#!/usr/bin/env bash
# Task 4, step 5: rolling update v1 -> v2 while the load test runs, then roll back.
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/lib.sh
OUT=results/task4_rollout.txt
set_min_replicas 2; wait_for_ready 2
trap 'set_min_replicas 1' EXIT

{
log "two v1 replicas ready; starting load (5 min)"
start_load task4_rollout 5m
sleep 40
log "BEFORE:"; probe | grep -iE 'HTTP/|x-model-version|x-served-by'
log "rolling update to v2"
kubectl -n app set env deployment/parser MODEL_VERSION=v2 MODEL_URI=s3://models/v2
kubectl -n app rollout status deployment/parser --timeout=300s
wait_for_ready 2   # old Pods finish their 10 s preStop pause and disappear
log "AFTER UPDATE (4 requests):"; for _ in 1 2 3 4; do probe | grep -iE 'x-model-version|x-served-by' | tr '\r\n' '  '; echo; done
sleep 40
log "rolling back with kubectl rollout undo"
kubectl -n app rollout undo deployment/parser
kubectl -n app rollout status deployment/parser --timeout=300s
wait_for_ready 2
log "AFTER ROLLBACK (4 requests):"; for _ in 1 2 3 4; do probe | grep -iE 'x-model-version|x-served-by' | tr '\r\n' '  '; echo; done
kubectl -n app rollout history deployment/parser
log "waiting for the load test to finish"
wait "$LOAD_PID" || true
echo; echo "# Locust result for the whole window (results/task4_rollout_stats.csv)"
load_summary results/task4_rollout_stats.csv
echo "# successful requests by version and replica"; cat results/task4_rollout_headers.json
} 2>&1 | tee "$OUT"
