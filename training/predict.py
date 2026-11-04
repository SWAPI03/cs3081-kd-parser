"""Run a model on validation.jsonl and write its raw outputs for tools/score.py (Task 2, step 6).

    python training/predict.py --model models/v1 --out results/pred_student_v1.jsonl
    python training/predict.py --model EleutherAI/pythia-70m --out results/pred_base.jsonl
Uses service/inference.py, so prompt and decoding are exactly those of the deployed service.
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "service"))
from inference import Student  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="model folder, or a Hugging Face model id")
    ap.add_argument("--out", required=True)
    ap.add_argument("--data", default=os.path.join(ROOT, "data", "validation.jsonl"))
    ap.add_argument("--max-new-tokens", type=int, default=64)
    a = ap.parse_args()

    student = Student(a.model, max_new_tokens=a.max_new_tokens)
    rows = [json.loads(line) for line in open(a.data, encoding="utf-8") if line.strip()]
    start = time.time()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps({"id": r["id"], "prediction": student.raw_output(r["text"])},
                               ensure_ascii=False) + "\n")
    print(f"{len(rows)} predictions -> {a.out} ({(time.time() - start) / len(rows):.2f}s each)")


if __name__ == "__main__":
    main()
