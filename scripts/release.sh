#!/usr/bin/env bash
# make release: publish the model artefacts as GitHub Release assets:
#   model-v1.tar.gz, model-v2.tar.gz   model + tokenizer (checksum = models/<version>/model.sha256)
#   model-v1.sha256, model-v2.sha256   the checksums
#   MODEL_VERSIONS.txt                 version information (base model, data, recipe, seeds, libraries)
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/release.conf
for v in v1 v2; do   # the asset must match the recorded checksum
  [ "$(sha256sum "models/model-$v.tar.gz" | cut -d' ' -f1)" = "$(cut -d' ' -f1 "models/$v/model.sha256")" ] \
    || { echo "models/model-$v.tar.gz does not match models/$v/model.sha256"; exit 1; }
  cp "models/$v/model.sha256" "models/model-$v.sha256"
done
loss() { tail -1 "$1" | cut -d, -f2; }
cat > models/MODEL_VERSIONS.txt <<TXT
Student models for the CS3081 mini project (Swapnil Yadav, 230103015)
Repository: https://github.com/$GITHUB_REPO

Base model: EleutherAI/pythia-70m (revision main), fine-tuned on the CPU (training/config.yaml).
Training data: datasets/v1/train.jsonl, first 1,500 records, sha256 $(cut -d' ' -f1 datasets/v1/train.sha256)
Recipe: learning rate 2e-4, batch size 16, 5 epochs, max sequence length 128, linear warm-up 5%

v1  seed 42  final loss $(loss training/loss.csv)  model-v1.tar.gz  sha256 $(cut -d' ' -f1 models/v1/model.sha256)
v2  seed 7   final loss $(loss training/loss_v2.csv)  model-v2.tar.gz  sha256 $(cut -d' ' -f1 models/v2/model.sha256)

Each archive holds the model (model.safetensors, config.json, generation_config.json) and the
tokenizer (tokenizer.json, tokenizer_config.json, special_tokens_map.json).
Libraries: torch 2.4.1+cpu, transformers 4.44.2, tokenizers 0.19.1, safetensors 0.4.5
Verify: sha256sum -c model-v1.sha256   (in the folder that holds model-v1.tar.gz)
TXT
ASSETS="models/model-v1.tar.gz models/model-v2.tar.gz models/model-v1.sha256 models/model-v2.sha256 models/MODEL_VERSIONS.txt"
if gh release view "$RELEASE_TAG" -R "$GITHUB_REPO" >/dev/null 2>&1; then
  gh release upload "$RELEASE_TAG" $ASSETS -R "$GITHUB_REPO" --clobber
else
  gh release create "$RELEASE_TAG" $ASSETS -R "$GITHUB_REPO" --title "Student models" --notes-file models/MODEL_VERSIONS.txt
fi
gh release view "$RELEASE_TAG" -R "$GITHUB_REPO" | tee results/task2_release.txt
