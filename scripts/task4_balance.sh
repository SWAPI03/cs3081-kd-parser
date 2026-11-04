#!/usr/bin/env bash
# Task 4, step 8 + Task 7: the standard load test through the Ingress with exactly two Ready
# replicas. Writes results/loadtest_stats.csv and results/loadtest_headers.json, and samples
# `kubectl top pods` during the run.
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/lib.sh
set_min_replicas 2; wait_for_ready 2
trap 'set_min_replicas 1' EXIT
kubectl -n app get pods -l app=parser -o wide | tee results/task4_balance_pods.txt
( sleep 30; for i in 1 2 3 4 5 6; do echo "# $(stamp)"; kubectl top pods -n app; sleep 15; done ) \
  > results/task7_top_pods.txt 2>&1 &
TOP=$!
.venv/bin/locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m \
  --host http://localhost:8080 --csv results/loadtest 2>&1 | tee results/loadtest_locust.txt || true
wait $TOP || true
echo; load_summary results/loadtest_stats.csv | tee results/task7_loadtest_summary.txt
cat results/loadtest_headers.json
