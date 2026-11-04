"""Task 7: estimated cost of 1,000 requests, every step shown.

cost per 1,000 requests = hourly cost of all running replicas / requests served per hour * 1000
Each replica is billed for its CPU LIMIT and memory LIMIT (read from k8s/app/deployment.yaml)
for every hour it runs. Throughput comes from the standard load test (results/loadtest_stats.csv).
"""
import csv
import json
import os
import sys

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def to_vcpu(v):
    v = str(v)
    return float(v[:-1]) / 1000 if v.endswith("m") else float(v)


def to_gib(v):
    v = str(v)
    units = {"Gi": 1, "Mi": 1 / 1024, "Ki": 1 / 1024 ** 2}
    for suffix, factor in units.items():
        if v.endswith(suffix):
            return float(v[: -len(suffix)]) * factor
    return float(v) / 1024 ** 3


def main():
    stats = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "results", "loadtest_stats.csv")
    rate = json.load(open(os.path.join(ROOT, "data", "rate_card.json")))
    dep = yaml.safe_load(open(os.path.join(ROOT, "k8s", "app", "deployment.yaml")))
    limits = dep["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]
    replicas = 2   # the load test runs with exactly two replicas (HPA maximum)
    cpu, mem = to_vcpu(limits["cpu"]), to_gib(limits["memory"])
    row = [r for r in csv.DictReader(open(stats)) if r["Name"] == "Aggregated"][0]
    rps = float(row["Requests/s"])
    ok = int(row["Request Count"]) - int(row["Failure Count"])
    served_rps = rps * ok / max(int(row["Request Count"]), 1)   # count only successful requests

    per_replica = cpu * rate["vcpu_hour"] + mem * rate["gib_memory_hour"]
    hourly = replicas * per_replica
    per_hour = served_rps * 3600
    cost = hourly / per_hour * 1000
    lines = [
        f"rate card: {rate['vcpu_hour']} {rate['currency']}/vCPU-hour, {rate['gib_memory_hour']} {rate['currency']}/GiB-hour",
        f"1. one replica   = {cpu:g} vCPU x {rate['vcpu_hour']} + {mem:g} GiB x {rate['gib_memory_hour']} = {per_replica:.4f} {rate['currency']}/hour",
        f"2. {replicas} replicas      = {replicas} x {per_replica:.4f} = {hourly:.4f} {rate['currency']}/hour",
        f"3. throughput    = {served_rps:.4f} successful requests/s (load test) x 3600 = {per_hour:.1f} requests/hour",
        f"4. cost / 1,000  = {hourly:.4f} / {per_hour:.1f} x 1000 = {cost:.4f} {rate['currency']}",
    ]
    out = os.path.join(ROOT, "results", "task7_cost.txt")
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
