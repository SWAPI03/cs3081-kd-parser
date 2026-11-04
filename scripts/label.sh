#!/usr/bin/env bash
# Run the two labelling workers in namespace "pipeline" and save the evidence (Task 1).
set -euo pipefail
cd "$(dirname "$0")/.."
CLUSTER=kdcloud
mkdir -p results

docker build -f worker/Dockerfile -t kd-worker:v1 .
k3d image import kd-worker:v1 -c "$CLUSTER"

# A finished Job cannot be re-applied with a new template: delete the old one first.
kubectl -n pipeline delete job teacher-label --ignore-not-found
kubectl apply -f k8s/pipeline/label-job.yaml
sleep 10
kubectl -n pipeline get pods -l app=teacher-label -o wide | tee results/task1_workers_running.txt

kubectl -n pipeline wait --for=condition=Ready pod -l app=teacher-label --timeout=300s || true
# Progress every 30 s until the Job completes (or fails).
while true; do
  done_=$(kubectl -n pipeline get job teacher-label -o jsonpath='{.status.conditions[?(@.type=="Complete")].status}')
  failed=$(kubectl -n pipeline get job teacher-label -o jsonpath='{.status.conditions[?(@.type=="Failed")].status}')
  for pod in $(kubectl -n pipeline get pods -l app=teacher-label -o name); do
    echo "$(date +%H:%M:%S) $(basename "$pod"): $(kubectl -n pipeline logs "$pod" --tail=1 2>&1)"
  done
  [ "$done_" = True ] && break
  [ "$failed" = True ] && { echo "Job FAILED: kubectl -n pipeline logs -l app=teacher-label"; exit 1; }
  sleep 30
done
{
  echo "# kubectl -n pipeline get job,pods -o wide"
  kubectl -n pipeline get job,pods -o wide
  echo
  echo "# SHARD_INDEX of each Pod (from the Indexed Job annotation)"
  kubectl -n pipeline get pods -l app=teacher-label \
    -o custom-columns='POD:.metadata.name,SHARD_INDEX:.metadata.annotations.batch\.kubernetes\.io/job-completion-index,STATUS:.status.phase'
} | tee results/task1_workers.txt
for pod in $(kubectl -n pipeline get pods -l app=teacher-label -o name); do
  kubectl -n pipeline logs "$pod" > "results/task1_$(basename "$pod").log"
done
echo "Labelling finished. Next: make clean-data"
