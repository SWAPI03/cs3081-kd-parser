#!/usr/bin/env bash
# Build the service image, make sure the models are in object storage, deploy (Task 4).
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/lib.sh

docker build -f service/Dockerfile -t kd-parser:v1 .
k3d image import kd-parser:v1 -c "$CLUSTER"

# The service downloads its model from s3://models/<version>/ at start-up.
# If it is not there yet (fresh clone), fetch it from the GitHub Release.
.venv/bin/python scripts/seed_models.py || {
  log "no model available yet: train first (make train), then run: make deploy"; exit 0; }

kubectl apply -f k8s/app/
kubectl -n app rollout status deploy/parser --timeout=600s
sleep 5
{ echo "# kubectl -n app get deploy,svc,ingress,hpa,pods -o wide"
  kubectl -n app get deploy,svc,ingress,hpa,pods -o wide
  echo; echo "# POST /parse through the Ingress"; probe; } | tee results/task4_deploy.txt
