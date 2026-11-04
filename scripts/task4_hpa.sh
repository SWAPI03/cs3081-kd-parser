#!/usr/bin/env bash
# Task 4, step 4: evidence that the HPA scales 1 -> 2 under load and back to 1 afterwards.
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/lib.sh
OUT=results/task4_hpa.txt
set_min_replicas 1
{
log "waiting for the HPA to settle at 1 replica (idle)"
for _ in $(seq 1 90); do [ "$(kubectl -n app get deploy parser -o jsonpath='{.status.readyReplicas}')" = 1 ] && break; sleep 5; done
kubectl -n app get hpa parser
log "starting load (4 min)"
start_load task4_hpa 4m
end=$(( $(date +%s) + 600 ))
while [ "$(date +%s)" -lt "$end" ]; do
  line=$(kubectl -n app get hpa parser --no-headers | awk '{print "targets=" $4 " replicas=" $7}')
  load=$(kill -0 "$LOAD_PID" 2>/dev/null && echo "load=on" || echo "load=off")
  echo "$(stamp) $load $line"
  if [ "$load" = "load=off" ] && [[ "$line" == *"replicas=1"* ]]; then break; fi
  sleep 10
done
echo; kubectl -n app describe hpa parser | sed -n '/Events:/,$p'
} 2>&1 | tee "$OUT"
