#!/usr/bin/env bash
# Task 3: run the container with 1 CPU and 1 GiB, check the endpoints and FAULT_INJECT,
# send 50 requests one after another, and record the peak memory.
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/lib.sh
OUT=results/task3_container.txt
NET=k3d-$CLUSTER     # same Docker network as the cluster, so the container reaches SeaweedFS
S3=http://k3d-$CLUSTER-server-0:30333
set -a; . ./.env; set +a

run() {  # run NAME PORT FAULT
  docker rm -f "$1" >/dev/null 2>&1 || true
  docker run -d --name "$1" --network "$NET" -p "$2":8000 --cpus=1 --memory=1g \
    -e MODEL_URI=s3://models/v1 -e MODEL_VERSION=v1 -e S3_ENDPOINT="$S3" -e MAX_NEW_TOKENS=64 \
    -e FAULT_INJECT="$3" -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY kd-parser:v1 >/dev/null
}

docker images kd-parser:v1 --format 'image {{.Repository}}:{{.Tag}} size {{.Size}}' | tee results/task3_image_size.txt
run kd-test 18000 0
{
echo "# docker run --cpus=1 --memory=1g kd-parser:v1  ($(date))"
echo "readyz right after start: $(curl -s -o /dev/null -w '%{http_code}' localhost:18000/readyz || echo down)"
for _ in $(seq 1 120); do [ "$(curl -s -o /dev/null -w '%{http_code}' localhost:18000/readyz)" = 200 ] && break; sleep 1; done
echo "healthz: $(curl -s -o /dev/null -w '%{http_code}' localhost:18000/healthz)   readyz after load: $(curl -s -o /dev/null -w '%{http_code}' localhost:18000/readyz)"
echo; echo "# POST /parse"; curl -s -i -X POST localhost:18000/parse -H 'Content-Type: application/json' -d '{"text":"set an alarm for seven thirty am tomorrow"}'; echo
echo; echo "# container log"; docker logs kd-test 2>&1 | tail -n 8
} | tee "$OUT"

# Peak memory: sample docker stats every 0.5 s while 50 requests are sent one after another.
( while true; do docker stats --no-stream --format '{{.MemUsage}}' kd-test; sleep 0.5; done ) > results/task3_mem_samples.txt 2>/dev/null &
SAMPLER=$!
ok=0; fail=0; start=$(date +%s)
mapfile -t TEXTS < <(.venv/bin/python -c "import json;[print(json.loads(l)['text']) for l in open('data/validation.jsonl')]")
for i in $(seq 0 49); do
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST localhost:18000/parse -H 'Content-Type: application/json' \
         -d "$(.venv/bin/python -c 'import json,sys;print(json.dumps({"text":sys.argv[1]}))' "${TEXTS[$i]}")")
  [ "$code" = 200 ] && ok=$((ok+1)) || fail=$((fail+1))
done
end=$(date +%s); kill $SAMPLER
{
echo; echo "# 50 sequential requests at --cpus=1 --memory=1g"
echo "HTTP 200: $ok   other: $fail   time: $((end-start)) s"
echo "OOMKilled: $(docker inspect -f '{{.State.OOMKilled}}' kd-test)   still running: $(docker inspect -f '{{.State.Running}}' kd-test)"
echo "peak memory (docker stats, sampled every 0.5 s): $(sed 's# /.*##' results/task3_mem_samples.txt | sort -h | tail -1) of 1GiB"
docker stats --no-stream kd-test
} | tee -a "$OUT"

run kd-fault 18001 1
for _ in $(seq 1 120); do [ "$(curl -s -o /dev/null -w '%{http_code}' localhost:18001/readyz)" = 200 ] && break; sleep 1; done
{ echo; echo "# FAULT_INJECT=1"; curl -s -i -X POST localhost:18001/parse -H 'Content-Type: application/json' -d '{"text":"what time is it in tokyo"}'; echo; } | tee -a "$OUT"
docker rm -f kd-test kd-fault >/dev/null
