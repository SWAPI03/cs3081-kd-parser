"""Upload an already-trained model folder to object storage without retraining.

    python scripts/upload_model.py v1      # models/v1/*  ->  s3://models/v1/
Used by `make upload-model V=v1` (for example after an upload was interrupted).
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "worker"))
import s3util  # noqa: E402


def main():
    version = sys.argv[1]
    folder = os.path.join(ROOT, "models", version)
    if not os.path.exists(os.path.join(folder, "model.safetensors")):
        sys.exit(f"{folder} has no trained model; run make train first")
    s3 = s3util.client()
    s3util.ensure_bucket(s3, "models")
    for fname in sorted(os.listdir(folder)):
        s3util.upload_file(s3, os.path.join(folder, fname), "models", f"{version}/{fname}")
        print(f"uploaded s3://models/{version}/{fname}")


if __name__ == "__main__":
    main()
