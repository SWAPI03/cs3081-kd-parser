#!/usr/bin/env bash
# make eval: raw outputs + score reports for the untrained Pythia-70M and the students (Task 2).
# The teacher is scored separately with `make eval-teacher` (needs Ollama).
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
bash scripts/train.sh deps
for v in v1 v2; do
  [ -f "models/$v/config.json" ] || { echo "models/$v missing locally: run make train / train-v2"; exit 1; }
done
$PY training/predict.py --model EleutherAI/pythia-70m --out results/pred_base.jsonl
$PY tools/score.py results/pred_base.jsonl data/validation.jsonl --out results/score_base.json
for v in v1 v2; do
  $PY training/predict.py --model "models/$v" --out "results/pred_student_$v.jsonl"
  $PY tools/score.py "results/pred_student_$v.jsonl" data/validation.jsonl --out "results/score_student_$v.json"
done
$PY scripts/score_table.py | tee results/score_table.md
