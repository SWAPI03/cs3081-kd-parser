"""Run the teacher on validation.jsonl with the SAME prompt and settings as Task 1.

  python scripts/eval_teacher.py --limit 20     # quick prompt check before labelling (pilot)
  python scripts/eval_teacher.py                # all 100 -> results/pred_teacher.jsonl
                                                #           results/teacher_validation.json
"""
import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "worker"))
import teacher  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="only the first N commands (pilot)")
    a = ap.parse_args()
    os.chdir(ROOT)

    gold = [json.loads(ln) for ln in open("data/validation.jsonl", encoding="utf-8") if ln.strip()]
    if a.limit:
        gold = gold[: a.limit]
    out_dir = "results/pilot" if a.limit else "results"
    os.makedirs(out_dir, exist_ok=True)
    pred_path = f"{out_dir}/pred_teacher.jsonl"
    gold_path = f"{out_dir}/gold_subset.jsonl" if a.limit else "data/validation.jsonl"
    report_path = f"{out_dir}/teacher_score.json" if a.limit else "results/teacher_validation.json"

    url = teacher.resolve_url()
    template = teacher.load_prompt()
    print(f"teacher at {url}, {len(gold)} commands", flush=True)
    start = time.time()
    with open(pred_path, "w", encoding="utf-8", newline="\n") as f:
        for i, g in enumerate(gold, 1):
            raw = teacher.ask(url, teacher.build_prompt(template, g["text"]))
            f.write(json.dumps({"id": g["id"], "prediction": raw}, ensure_ascii=False) + "\n")
            if a.limit or i % 10 == 0:
                print(f"  {i:3d}  {g['text'][:45]:45s} -> {raw.strip()}", flush=True)
    print(f"{len(gold)} commands in {time.time() - start:.0f}s "
          f"({(time.time() - start) / len(gold):.1f}s each)")
    if a.limit:
        with open(gold_path, "w", encoding="utf-8", newline="\n") as f:
            f.writelines(json.dumps(g) + "\n" for g in gold)
    subprocess.run([sys.executable, "tools/score.py", pred_path, gold_path, "--out", report_path],
                   check=True)


if __name__ == "__main__":
    main()
