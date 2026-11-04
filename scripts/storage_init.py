"""Create the two buckets and upload the inputs (Task 1, step 2).

  datasets/commands_pool.jsonl          from data/commands_pool.jsonl
  datasets/teacher/shard-*.jsonl        from datasets/teacher/ (if the repo already has them)
  datasets/v1/train.jsonl (+ .sha256)   from datasets/v1/       (if the repo already has them)

The last two let a fresh clone run `make train` without re-running the teacher.
Runs on the laptop against http://localhost:8333 (NodePort into the cluster).
"""
import glob
import os
import sys
import time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "worker"))
import s3util  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402


def wait_for_s3(s3, seconds=180):
    deadline = time.time() + seconds
    while True:
        try:
            s3.list_buckets()
            return
        except ClientError:
            raise  # wrong keys etc.: fail now, waiting will not help
        except Exception as e:  # connection refused: SeaweedFS still starting
            if time.time() > deadline:
                raise SystemExit(f"S3 endpoint not ready: {e}")
            time.sleep(3)


def upload_file(s3, path, key):
    with open(path, "rb") as f:
        s3util.put_bytes(s3, "datasets", key, f.read())
    print(f"  s3://datasets/{key}")


def main():
    os.chdir(ROOT)
    s3 = s3util.client()
    wait_for_s3(s3)
    for bucket in ("datasets", "models"):
        s3util.ensure_bucket(s3, bucket)
    print("buckets:", [b["Name"] for b in s3.list_buckets()["Buckets"]])
    upload_file(s3, "data/commands_pool.jsonl", "commands_pool.jsonl")
    for path in sorted(glob.glob("datasets/teacher/shard-*.jsonl")):
        upload_file(s3, path, "teacher/" + os.path.basename(path))
    for name in ("train.jsonl", "train.sha256"):
        if os.path.exists(f"datasets/v1/{name}"):
            upload_file(s3, f"datasets/v1/{name}", f"v1/{name}")


if __name__ == "__main__":
    main()
