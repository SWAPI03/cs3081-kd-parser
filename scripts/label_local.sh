#!/usr/bin/env bash
# FALLBACK ONLY: run the same two workers as laptop processes instead of Pods.
# Use this only if the Pods cannot reach Ollama. It still writes shard-0 and shard-1 to object
# storage, but it does NOT satisfy "workers ran in namespace pipeline" (costs 2 marks).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p results
export S3_ENDPOINT=http://localhost:8333 SHARD_COUNT=2
SHARD_INDEX=0 .venv/bin/python worker/label.py > results/task1_local_shard-0.log 2>&1 &
SHARD_INDEX=1 .venv/bin/python worker/label.py > results/task1_local_shard-1.log 2>&1 &
echo "two local workers started; follow with: tail -f results/task1_local_shard-*.log"
wait
