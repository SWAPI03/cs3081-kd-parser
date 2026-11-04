#!/usr/bin/env bash
# Create the S3 credentials and put them into Kubernetes Secrets.
#
# The keys live only in .env (git-ignored) and in the cluster. If .env does not exist,
# random keys are generated, so a fresh clone needs no manual step.
#
# Secrets created:
#   data/seaweedfs-s3-config   the SeaweedFS identity file (s3.json) that defines the key
#   pipeline/s3-credentials    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY for the workers
#   app/s3-credentials         the same, for the inference service
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  ak="kd$(head -c 8 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  sk="$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  printf 'AWS_ACCESS_KEY_ID=%s\nAWS_SECRET_ACCESS_KEY=%s\n' "$ak" "$sk" > .env
  echo "[secrets] generated new keys in .env (git-ignored)"
fi
set -a; . ./.env; set +a

s3json=$(printf '{"identities":[{"name":"kdadmin","credentials":[{"accessKey":"%s","secretKey":"%s"}],"actions":["Admin","Read","Write","List","Tagging"]}]}' \
  "$AWS_ACCESS_KEY_ID" "$AWS_SECRET_ACCESS_KEY")

# "create --dry-run | apply" makes the script safe to run more than once.
kubectl -n data create secret generic seaweedfs-s3-config \
  --from-literal=s3.json="$s3json" --dry-run=client -o yaml | kubectl apply -f -

for ns in pipeline app; do
  kubectl -n "$ns" create secret generic s3-credentials \
    --from-literal=AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
    --from-literal=AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
    --dry-run=client -o yaml | kubectl apply -f -
done
echo "[secrets] done"
