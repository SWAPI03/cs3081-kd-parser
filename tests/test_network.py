"""Task 5: the subnet plan and the NACL against the sample packets."""
import json
import os
import subprocess
import sys

import subnets

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_subnet_plan():
    rows = {r["name"]: r for r in subnets.allocate()}
    assert rows["app"]["cidr"] == "10.20.0.0/22" and rows["app"]["usable"] == 1022
    assert rows["public"]["cidr"] == "10.20.4.0/24" and rows["public"]["broadcast"] == "10.20.4.255"
    assert rows["data"]["cidr"] == "10.20.5.0/25" and rows["data"]["last"] == "10.20.5.126"
    assert rows["management"]["cidr"] == "10.20.5.128/27" and rows["management"]["usable"] == 30
    for r in rows.values():
        assert r["usable"] >= r["needed"]


def test_subnets_md_matches_calculation():
    text = open(os.path.join(ROOT, "network", "subnets.md"), encoding="utf-8").read()
    for r in subnets.allocate():
        assert f"| {r['name']} | {r['needed']} | {r['network']} | /{r['prefix']} |" in text


def test_nacl_passes_sample_packets():
    out = subprocess.run([sys.executable, "tools/nacl_sim.py", "network/nacl.json",
                          "network/packets_sample.jsonl", "--check"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    assert "6 / 6" in out


def test_deny_rule_comes_before_web_allows():
    rules = json.load(open(os.path.join(ROOT, "network", "nacl.json")))["inbound"]
    deny = min(r["rule"] for r in rules if r["action"] == "deny")
    web = [r["rule"] for r in rules if r.get("port_from") in (80, 443)]
    assert deny < min(web)
