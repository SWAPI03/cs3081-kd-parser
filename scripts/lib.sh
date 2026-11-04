# Shared helpers for the Task 3/4/7 scripts. Source it: . scripts/lib.sh
CLUSTER=kdcloud
INGRESS=http://localhost:8080
LOCUST=.venv/bin/locust
mkdir -p results

stamp() { date '+%H:%M:%S'; }
log() { echo "[$(stamp)] $*"; }

# Number of Ready Pods of the service.
ready_pods() {
  kubectl -n app get pods -l app=parser \
    -o jsonpath='{range .items[*]}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}' | grep -c True || true
}

set_min_replicas() {   # set the HPA minimum (2 for tests that need exactly two replicas)
  kubectl -n app patch hpa parser --type merge -p "{\"spec\":{\"minReplicas\":$1}}" >/dev/null
}

wait_for_ready() {     # wait_for_ready N: until exactly N Pods are Ready and no Pod is terminating
  local want=$1
  for _ in $(seq 1 180); do
    local total; total=$(kubectl -n app get pods -l app=parser --no-headers 2>/dev/null | wc -l)
    if [ "$(ready_pods)" -eq "$want" ] && [ "$total" -eq "$want" ]; then return 0; fi
    sleep 2
  done
  log "timed out waiting for $want ready Pods"; kubectl -n app get pods; return 1
}

# start_load NAME DURATION: Locust in the background, files results/NAME_stats.csv etc.
start_load() {
  LOADTEST_HEADERS_OUT="results/$1_headers.json" $LOCUST -f tools/locustfile.py --headless \
    --users 4 --spawn-rate 4 --run-time "$2" --host "$INGRESS" --csv "results/$1" \
    > "results/$1_locust.txt" 2>&1 &
  LOAD_PID=$!
}

# failure summary from a Locust stats file
load_summary() {
  .venv/bin/python - "$1" <<'PY'
import csv, sys
row = [r for r in csv.DictReader(open(sys.argv[1])) if r["Name"] == "Aggregated"][0]
n, f = int(row["Request Count"]), int(row["Failure Count"])
print(f"requests={n} failures={f} failure_rate={100.0 * f / max(n, 1):.2f}% "
      f"p50={row['50%']}ms p95={row['95%']}ms rps={float(row['Requests/s']):.2f}")
PY
}

probe() {   # one request through the Ingress, headers + body
  curl -s -i -X POST "$INGRESS/parse" -H 'Content-Type: application/json' \
    -d '{"text": "what is the weather in london tomorrow"}'
  echo
}
