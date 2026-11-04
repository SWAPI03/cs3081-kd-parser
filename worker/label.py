"""Teacher-labelling worker (Task 1, steps 4 and 5).

Environment variables:
  SHARD_INDEX   which shard this worker handles, starting from 0
  SHARD_COUNT   how many workers there are in total
  S3_ENDPOINT, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY   object storage
  OLLAMA_URL    where the teacher runs (optional; see teacher.resolve_url)

The worker takes every command whose line number (counting from 0) leaves remainder
SHARD_INDEX when divided by SHARD_COUNT, asks the teacher about it, and writes
{"id", "text", "teacher_raw"} lines to its own object: datasets/teacher/shard-<SHARD_INDEX>.jsonl.

Resumable: the shard object is uploaded every CHECKPOINT_EVERY commands. If the Pod dies,
Kubernetes restarts it, and the new Pod skips the ids that are already in the object.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s3util  # noqa: E402
import teacher  # noqa: E402

BUCKET = os.environ.get("DATASETS_BUCKET", "datasets")
POOL_KEY = os.environ.get("POOL_KEY", "commands_pool.jsonl")
CHECKPOINT_EVERY = int(os.environ.get("CHECKPOINT_EVERY", "25"))


def my_commands(pool_lines, index, count):
    """The commands this shard owns: line number % count == index."""
    mine = []
    for line_no, line in enumerate(pool_lines):
        if line.strip() and line_no % count == index:
            mine.append(json.loads(line))
    return mine


def main():
    index = int(os.environ["SHARD_INDEX"])
    count = int(os.environ["SHARD_COUNT"])
    if not 0 <= index < count:
        sys.exit(f"SHARD_INDEX={index} must be in [0, {count})")
    out_key = f"teacher/shard-{index}.jsonl"

    s3 = s3util.client()
    pool = s3util.get_bytes(s3, BUCKET, POOL_KEY)
    if pool is None:
        sys.exit(f"s3://{BUCKET}/{POOL_KEY} not found; run `make up` first")
    todo = my_commands(pool.decode("utf-8").splitlines(), index, count)

    # Resume: keep lines already uploaded by an earlier run of this shard.
    done_lines = []
    existing = s3util.get_bytes(s3, BUCKET, out_key)
    if existing:
        done_lines = [ln for ln in existing.decode("utf-8").splitlines() if ln.strip()]
    done_ids = {json.loads(ln)["id"] for ln in done_lines}
    todo = [c for c in todo if c["id"] not in done_ids]

    url = teacher.resolve_url()
    template = teacher.load_prompt()
    total = len(todo) + len(done_lines)
    print(f"[shard {index}/{count}] {total} commands, {len(done_lines)} already done; "
          f"teacher at {url}; writing s3://{BUCKET}/{out_key}", flush=True)

    start = time.time()
    for n, cmd in enumerate(todo, 1):
        raw = teacher.ask(url, teacher.build_prompt(template, cmd["text"]))
        # teacher_raw is stored exactly as the teacher produced it (no editing).
        done_lines.append(json.dumps({"id": cmd["id"], "text": cmd["text"], "teacher_raw": raw},
                                     ensure_ascii=False))
        if n % CHECKPOINT_EVERY == 0 or n == len(todo):
            s3util.put_bytes(s3, BUCKET, out_key, ("\n".join(done_lines) + "\n").encode("utf-8"))
            rate = n / (time.time() - start)
            eta_min = (len(todo) - n) / rate / 60 if rate else 0
            print(f"[shard {index}] {len(done_lines)}/{total} done, "
                  f"{rate * 60:.1f} cmd/min, ETA {eta_min:.0f} min", flush=True)
    if not todo:
        print(f"[shard {index}] nothing to do", flush=True)
    print(f"[shard {index}] finished: {len(done_lines)} lines in s3://{BUCKET}/{out_key}", flush=True)


if __name__ == "__main__":
    main()
