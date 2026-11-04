"""Clean the teacher's replies into the training set (Task 1, step 6).

Reads every shard (datasets/teacher/shard-*.jsonl), removes bad records, and writes the rest,
in id order, to datasets/v1/train.jsonl plus its SHA-256 checksum in datasets/v1/train.sha256.

Removal rules, applied in this order. Each removed record is counted under ONE reason only.
  duplicates  the same command text appears under several ids: keep the smallest id
              (checked first, so the copy that is kept is always the smallest id)
  (a)         teacher_raw is not valid JSON
  (b)         it is not an object whose keys are exactly intent, date, time, place
  (c)         intent is not one of the eight in data/schema.json
  (d)         a slot value is neither null nor text that appears in the command.
              "Appears" = the value, lower-cased with spaces collapsed, is found in the command
              as whole words (so "at" does not match inside "what"). An empty string or a
              non-string value (number, list...) also fails this rule.

Each kept record is {"id", "text", "teacher_raw", "target"}. teacher_raw is untouched;
target is the same parsed object written back out with a fixed key order and spacing, so all
training targets have one identical format.

Reproducible by construction: sorted by id, fixed json.dumps settings, "\n" line endings,
UTF-8. Running it twice on the same shards gives the same bytes and the same checksum.

Usage:
  python worker/clean.py                 # shards from object storage, results uploaded back
  python worker/clean.py --local DIR     # shards from DIR/teacher/, nothing uploaded
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
KEYS = ["intent", "date", "time", "place"]
SLOTS = ["date", "time", "place"]


def load_intents(path=os.path.join(ROOT, "data", "schema.json")):
    with open(path, encoding="utf-8") as f:
        return set(json.load(f)["intents"])


def norm(s):
    return " ".join(s.lower().split())


def slot_in_command(value, command):
    if not isinstance(value, str) or not value.strip():
        return False
    return re.search(r"(?<!\w)" + re.escape(norm(value)) + r"(?!\w)", norm(command)) is not None


def id_key(record_id):
    return (len(record_id), record_id)


def check(record, intents):
    """Return None if the record is good, else the reason letter: 'a', 'b', 'c' or 'd'."""
    try:
        obj = json.loads(record["teacher_raw"])
    except (json.JSONDecodeError, TypeError):
        return "a"
    if not isinstance(obj, dict) or sorted(obj.keys()) != sorted(KEYS):
        return "b"
    if not isinstance(obj["intent"], str) or obj["intent"] not in intents:
        return "c"
    for slot in SLOTS:
        if obj[slot] is not None and not slot_in_command(obj[slot], record["text"]):
            return "d"
    return None


def canonical(record):
    obj = json.loads(record["teacher_raw"])
    return json.dumps({k: obj[k] for k in KEYS}, ensure_ascii=False)


def clean(records, intents):
    """Return (kept_records, counts). Pure function: easy to unit-test."""
    counts = {"input": len(records), "a_invalid_json": 0, "b_wrong_keys": 0,
              "c_bad_intent": 0, "d_bad_slot": 0, "duplicates": 0, "kept": 0}

    records = sorted(records, key=lambda r: id_key(r["id"]))
    seen_text, unique = set(), []
    for r in records:
        t = norm(r["text"])
        if t in seen_text:
            counts["duplicates"] += 1
        else:
            seen_text.add(t)
            unique.append(r)

    names = {"a": "a_invalid_json", "b": "b_wrong_keys", "c": "c_bad_intent", "d": "d_bad_slot"}
    kept = []
    for r in unique:
        reason = check(r, intents)
        if reason:
            counts[names[reason]] += 1
        else:
            kept.append({"id": r["id"], "text": r["text"], "teacher_raw": r["teacher_raw"],
                         "target": canonical(r)})
    counts["kept"] = len(kept)
    removed = sum(v for k, v in counts.items() if k not in ("input", "kept"))
    assert counts["input"] == removed + counts["kept"], counts
    return kept, counts


def serialise(kept):
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept).encode("utf-8")


def coverage(records, pool_ids):
    """Every pool id must appear in exactly one shard: report gaps and repeats."""
    from collections import Counter
    c = Counter(r["id"] for r in records)
    return {"pool_ids": len(pool_ids),
            "missing": sorted(set(pool_ids) - set(c), key=id_key),
            "repeated": sorted([i for i, n in c.items() if n > 1], key=id_key),
            "unknown": sorted(set(c) - set(pool_ids), key=id_key)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", help="read shards from LOCAL/teacher/ instead of object storage")
    ap.add_argument("--out", default=os.path.join(ROOT, "datasets"),
                    help="local folder that mirrors the datasets bucket")
    ap.add_argument("--counts", default=os.path.join(ROOT, "results", "clean_counts.json"))
    a = ap.parse_args()

    shard_texts = {}
    if a.local:
        for path in sorted(glob.glob(os.path.join(a.local, "teacher", "shard-*.jsonl"))):
            with open(path, encoding="utf-8") as f:
                shard_texts[os.path.basename(path)] = f.read()
    else:
        import s3util
        s3 = s3util.client()
        for key in s3util.list_keys(s3, "datasets", "teacher/shard-"):
            data = s3util.get_bytes(s3, "datasets", key).decode("utf-8")
            shard_texts[os.path.basename(key)] = data
            # keep a copy in the repo so anyone can re-run clean.py and check the checksum
            os.makedirs(os.path.join(a.out, "teacher"), exist_ok=True)
            with open(os.path.join(a.out, "teacher", os.path.basename(key)), "w",
                      encoding="utf-8", newline="\n") as f:
                f.write(data)
    if not shard_texts:
        sys.exit("no shard files found")

    records = []
    for name, text in shard_texts.items():
        records += [json.loads(ln) for ln in text.splitlines() if ln.strip()]

    with open(os.path.join(ROOT, "data", "commands_pool.jsonl"), encoding="utf-8") as f:
        pool_ids = [json.loads(ln)["id"] for ln in f if ln.strip()]
    cov = coverage(records, pool_ids)

    kept, counts = clean(records, load_intents())
    data = serialise(kept)
    digest = hashlib.sha256(data).hexdigest()
    sha_line = f"{digest}  train.jsonl\n".encode()

    os.makedirs(os.path.join(a.out, "v1"), exist_ok=True)
    with open(os.path.join(a.out, "v1", "train.jsonl"), "wb") as f:
        f.write(data)
    with open(os.path.join(a.out, "v1", "train.sha256"), "wb") as f:
        f.write(sha_line)
    if not a.local:
        s3util.put_bytes(s3, "datasets", "v1/train.jsonl", data)
        s3util.put_bytes(s3, "datasets", "v1/train.sha256", sha_line)

    report = {"shards": sorted(shard_texts), "counts": counts,
              "coverage": {"pool_ids": cov["pool_ids"], "missing": len(cov["missing"]),
                           "repeated": len(cov["repeated"]), "unknown": len(cov["unknown"])},
              "sha256": digest}
    os.makedirs(os.path.dirname(a.counts), exist_ok=True)
    with open(a.counts, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print(json.dumps(report, indent=2))
    if cov["missing"] or cov["repeated"] or cov["unknown"]:
        print("WARNING: shard coverage problem:", {k: v[:10] for k, v in cov.items()
                                                  if k != "pool_ids"}, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
