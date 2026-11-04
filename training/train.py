"""Fine-tune Pythia-70M on the teacher's replies: sequence-level knowledge distillation (Task 2).

Each training example is the text
    Command: <the command>
    JSON: <the teacher's JSON reply><end-of-text>
The loss is computed only on the reply and the end-of-text token (the "Command" part is given,
not predicted). Learning to emit end-of-text is what makes the student stop after the JSON.

Usage (normally through make):
    python training/train.py --version v1            # full run -> models/v1/, uploaded
    python training/train.py --version v1 --subset 50  # quick check, nothing uploaded
    python training/train.py --version v2            # same recipe, the v2 seed from config.yaml
All hyper-parameters come from training/config.yaml.
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import random
import sys
import tarfile
import time

import numpy as np
import torch
import yaml
from transformers import AutoModelForCausalLM, AutoTokenizer, get_linear_schedule_with_warmup

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "worker"))
sys.path.insert(0, os.path.join(ROOT, "service"))
from inference import prompt_for  # noqa: E402  (same prompt format as the service)


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)


def load_records(cfg):
    """train.jsonl from object storage (checksum verified); local copy if storage is unreachable."""
    data = None
    try:
        import s3util
        s3 = s3util.client()
        data = s3util.get_bytes(s3, cfg["data"]["bucket"], cfg["data"]["key"])
        expected = s3util.get_bytes(s3, cfg["data"]["bucket"], cfg["data"]["checksum_key"])
        source = f"s3://{cfg['data']['bucket']}/{cfg['data']['key']}"
    except Exception as e:  # storage not running: fall back to the copy in the repository
        print(f"[train] object storage unavailable ({type(e).__name__}); using the local copy")
    if data is None:
        with open(os.path.join(ROOT, "datasets", "v1", "train.jsonl"), "rb") as f:
            data = f.read()
        with open(os.path.join(ROOT, "datasets", "v1", "train.sha256"), "rb") as f:
            expected = f.read()
        source = "datasets/v1/train.jsonl"
    digest = hashlib.sha256(data).hexdigest()
    if expected and expected.split()[0].decode() != digest:
        sys.exit(f"checksum mismatch for {source}: {digest} != {expected.split()[0].decode()}")
    print(f"[train] {source} sha256={digest[:16]}... verified")
    return [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]


def encode(record, tokenizer, max_len):
    """input_ids for prompt + reply + EOS, and labels with the prompt positions set to -100."""
    prompt_ids = tokenizer(prompt_for(record["text"]))["input_ids"]
    reply_ids = tokenizer(" " + record["target"])["input_ids"] + [tokenizer.eos_token_id]
    ids = (prompt_ids + reply_ids)[:max_len]
    labels = ([-100] * len(prompt_ids) + reply_ids)[:max_len]
    return ids, labels


def batches(examples, batch_size, pad_id, rng):
    order = list(range(len(examples)))
    rng.shuffle(order)
    for i in range(0, len(order), batch_size):
        chunk = [examples[j] for j in order[i:i + batch_size]]
        width = max(len(ids) for ids, _ in chunk)
        input_ids = torch.full((len(chunk), width), pad_id, dtype=torch.long)
        labels = torch.full((len(chunk), width), -100, dtype=torch.long)   # padding: no loss
        attention = torch.zeros((len(chunk), width), dtype=torch.long)
        for row, (ids, lab) in enumerate(chunk):
            input_ids[row, :len(ids)] = torch.tensor(ids)
            labels[row, :len(lab)] = torch.tensor(lab)
            attention[row, :len(ids)] = 1
        yield input_ids, attention, labels


def deterministic_tar_gz(src_dir, out_path):
    """Pack the model folder so the same files always give the same bytes (and checksum)."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name in sorted(os.listdir(src_dir)):
            if name == "model.sha256":
                continue
            info = tar.gettarinfo(os.path.join(src_dir, name), arcname=name)
            info.mtime, info.uid, info.gid, info.uname, info.gname = 0, 0, 0, "", ""
            with open(os.path.join(src_dir, name), "rb") as f:
                tar.addfile(info, f)
    with open(out_path, "wb") as f, gzip.GzipFile(fileobj=f, mode="wb", mtime=0, filename="") as gz:
        gz.write(raw.getvalue())


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1")
    ap.add_argument("--subset", type=int, help="train on the first N records only (quick check)")
    a = ap.parse_args()

    with open(os.path.join(ROOT, "training", "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg.update(cfg["versions"][a.version])
    set_seed(cfg["seed"])
    torch.set_num_threads(max(1, os.cpu_count() or 1))

    records = load_records(cfg)[: cfg["train_records"]]
    if a.subset:
        records = records[: a.subset]
    tokenizer = AutoTokenizer.from_pretrained(cfg["student_model"], revision=cfg["model_revision"])
    model = AutoModelForCausalLM.from_pretrained(cfg["student_model"], revision=cfg["model_revision"],
                                                 torch_dtype=torch.float32)
    examples = [encode(r, tokenizer, cfg["max_seq_length"]) for r in records]
    longest = max(len(ids) for ids, _ in examples)
    print(f"[train] version={a.version} seed={cfg['seed']} examples={len(examples)} "
          f"longest={longest} tokens (limit {cfg['max_seq_length']})")

    steps_per_epoch = (len(examples) + cfg["batch_size"] - 1) // cfg["batch_size"]
    total_steps = steps_per_epoch * cfg["epochs"]
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg["learning_rate"],
                                  weight_decay=cfg["weight_decay"])
    scheduler = get_linear_schedule_with_warmup(optimizer, int(cfg["warmup_ratio"] * total_steps),
                                                total_steps)
    rng = random.Random(cfg["seed"])

    losses = []
    model.train()
    start = time.time()
    for epoch in range(1, cfg["epochs"] + 1):
        total, count = 0.0, 0
        for input_ids, attention, labels in batches(examples, cfg["batch_size"],
                                                    tokenizer.eos_token_id, rng):
            loss = model(input_ids=input_ids, attention_mask=attention, labels=labels).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), cfg["max_grad_norm"])
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            total += loss.item()
            count += 1
        losses.append(total / count)
        print(f"[train] epoch {epoch}/{cfg['epochs']}  loss {losses[-1]:.4f}  "
              f"({time.time() - start:.0f}s)", flush=True)

    # loss per epoch: training/loss.csv for v1, loss_<version>.csv otherwise
    name = "loss_subset.csv" if a.subset else ("loss.csv" if a.version == "v1" else f"loss_{a.version}.csv")
    with open(os.path.join(ROOT, "training", name), "w", newline="\n") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["epoch", "loss"])
        w.writerows([[i, f"{v:.6f}"] for i, v in enumerate(losses, 1)])
    print(f"[train] wrote training/{name}")

    out_dir = os.path.join(ROOT, "models", f"subset-{a.subset}" if a.subset else a.version)
    os.makedirs(out_dir, exist_ok=True)
    model.save_pretrained(out_dir, safe_serialization=True)
    tokenizer.save_pretrained(out_dir)
    if a.subset:
        print(f"[train] subset run finished; model in {out_dir} (not uploaded)")
        return

    tar_path = os.path.join(ROOT, "models", f"model-{a.version}.tar.gz")
    deterministic_tar_gz(out_dir, tar_path)
    digest = sha256_file(tar_path)
    with open(os.path.join(out_dir, "model.sha256"), "w", newline="\n") as f:
        f.write(f"{digest}  model-{a.version}.tar.gz\n")
    print(f"[train] {tar_path} sha256 {digest}")

    import s3util
    s3 = s3util.client()
    for fname in sorted(os.listdir(out_dir)):
        with open(os.path.join(out_dir, fname), "rb") as f:
            s3util.put_bytes(s3, "models", f"{a.version}/{fname}", f.read())
        print(f"[train] uploaded s3://models/{a.version}/{fname}")


if __name__ == "__main__":
    main()
