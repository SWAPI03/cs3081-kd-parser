#!/usr/bin/env bash
# `make up`: build and deploy the whole system from a fresh clone.
#   1. Python venv with the laptop-side tools
#   2. k3d cluster from cluster/k3d.yaml
#   3. namespaces, Secrets, SeaweedFS; buckets + commands_pool.jsonl uploaded
#   4. (once the service exists) service image + model + Deployment/Service/Ingress/HPA
set -euo pipefail
cd "$(dirname "$0")/.."
CLUSTER=kdcloud

for tool in docker k3d kubectl python3; do
  command -v "$tool" >/dev/null || { echo "missing tool: $tool (see README, Prerequisites)"; exit 1; }
done

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements-dev.txt
fi

if k3d cluster list "$CLUSTER" >/dev/null 2>&1; then
  echo "[up] cluster $CLUSTER already exists"
else
  k3d cluster create --config cluster/k3d.yaml
fi

kubectl apply -f k8s/namespaces.yaml
bash scripts/secrets.sh
kubectl apply -f k8s/data/seaweedfs.yaml
kubectl -n data rollout status deploy/seaweedfs --timeout=300s
.venv/bin/python scripts/storage_init.py

if [ -f scripts/deploy_app.sh ]; then
  bash scripts/deploy_app.sh
fi
echo "[up] done"
