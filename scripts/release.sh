#!/usr/bin/env bash
# make release: publish model-v1.tar.gz and model-v2.tar.gz as GitHub Release assets.
# The checksum of each asset equals models/<version>/model.sha256.
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/release.conf
for v in v1 v2; do   # the asset must match the recorded checksum
  [ "$(sha256sum "models/model-$v.tar.gz" | cut -d' ' -f1)" = "$(cut -d' ' -f1 "models/$v/model.sha256")" ] \
    || { echo "models/model-$v.tar.gz does not match models/$v/model.sha256"; exit 1; }
done
if gh release view "$RELEASE_TAG" -R "$GITHUB_REPO" >/dev/null 2>&1; then
  gh release upload "$RELEASE_TAG" models/model-v1.tar.gz models/model-v2.tar.gz -R "$GITHUB_REPO" --clobber
else
  gh release create "$RELEASE_TAG" models/model-v1.tar.gz models/model-v2.tar.gz -R "$GITHUB_REPO" \
    --title "Student models" \
    --notes "Pythia-70M students. sha256: v1 $(cut -d' ' -f1 models/v1/model.sha256), v2 $(cut -d' ' -f1 models/v2/model.sha256)"
fi
gh release view "$RELEASE_TAG" -R "$GITHUB_REPO" | tee results/task2_release.txt
