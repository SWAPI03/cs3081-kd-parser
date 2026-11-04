---
title: "Knowledge Distillation and Deployment of a Command Parser on a Local Cloud"
subtitle: "CS3081 Cloud Computing, Mini Project"
author: "Swapnil Yadav (230103015)"
---

**Repository:** [[FILL: https://github.com/SWAPI03/REPO]]  **Assessed commit:** tag `final`

**Measured results vs assumptions.** Every number in **bold** below was measured on my laptop
(Intel i7-14700HX, 16 GB RAM, RTX 4050, Windows 11 + WSL2 + Docker Desktop) and comes from a file
in `results/`, named next to it. Assumptions are marked *Assumption*.

## Architecture

[[FILL: one diagram: laptop (Ollama phi3.5 on GPU) <- k3d cluster (single k3s node): namespace
data (SeaweedFS, buckets datasets + models), namespace pipeline (2 worker Pods), namespace app
(2 parser Pods, Service, Traefik Ingress :8080, HPA). Training on the laptop CPU, model to
s3://models/v1 and v2, and to the GitHub Release.]]

## 1. Object storage and parallel teacher labelling

**Setup.** `cluster/k3d.yaml` defines one k3s server node (k3s v1.31.4) with port 8080 to Traefik
and 8333 to the SeaweedFS S3 API (NodePort 30333). SeaweedFS 3.85 runs in namespace `data` as one
Pod (`weed server -s3`) on a 5 Gi local-path volume. Its access key is generated into the
git-ignored `.env` and given to Pods only through Secrets. `scripts/storage_init.py` creates the
buckets `datasets` and `models` and uploads `commands_pool.jsonl`.

**Teacher.** phi3.5 in Ollama on the laptop (GPU), temperature 0, seed 42, prompt in
`prompts/teacher_prompt.txt`. *Disclosed settings:* `format: "json"` (Ollama only lets the model
emit syntactically valid JSON; the model still chooses keys, intent and slot values) and
`num_predict: 96` (a length cap; a correct reply is about 30 tokens). The same function
(`worker/teacher.py`) is used for labelling and for the teacher's validation score.

**Sharding.** [[CHECK: half a page max]] Two worker Pods run as one Indexed Job in namespace
`pipeline` (`k8s/pipeline/label-job.yaml`). Kubernetes gives each Pod a completion index (0 or 1),
passed to the worker as `SHARD_INDEX`; `SHARD_COUNT` is 2. A worker takes the commands whose line
number modulo `SHARD_COUNT` equals `SHARD_INDEX`, so the shards are disjoint, together cover every
line, and are equal in size (1,500 each). Workers never talk to each other. Each writes its own
object (`datasets/teacher/shard-0.jsonl`, `shard-1.jsonl`) and uploads it every 25 commands; a
restarted Pod reads its object back and continues from the first missing id. Both workers send
requests to the same Ollama server, so the speed-up depends on how many requests Ollama runs in
parallel on one GPU; the design scales out unchanged with more teacher servers. Evidence:
`results/task1_workers.txt` (both Pods, indexes 0 and 1), `results/task1_*.log`.

**Results.** [[FILL from results/clean_counts.json]]

| Input | (a) not JSON | (b) wrong keys | (c) bad intent | (d) slot not in command | Duplicates | Kept |
|---|---|---|---|---|---|---|
| **3000** | ** ** | ** ** | ** ** | ** ** | ** ** | ** ** |

Coverage: every one of the 3,000 ids appears in exactly one shard (**0 missing, 0 repeated**).
Checksum `datasets/v1/train.sha256`: [[FILL]]; re-running `clean.py` reproduces it (sorted by id,
fixed serialisation, `\n` endings). Duplicates are removed first, so the copy kept is always the
smallest id. Labelling time: [[FILL]] minutes.

**Limitations / improvements.** Rule (d) uses whole-word matching after lower-casing; it rejects
correct but reworded values and cannot catch a value that appears in the command but is the wrong
slot. Improvement: a second teacher pass or self-consistency check for rejected commands.

## 2. Training the student (sequence-level distillation)

**Setup.** `make train` reads only `training/config.yaml`: seed 42, learning rate 2e-4, batch 16,
5 epochs, max sequence length 128 (the longest example is [[FILL]] tokens), linear warm-up 5%,
library versions. Training text: `Command: <command>\nJSON: <teacher reply><end-of-text>`; the loss
covers only the reply and the end-of-text token, so the student learns where to stop. The reply is
the teacher's parsed JSON written back with a fixed key order (same content, one consistent
format; the raw reply is kept unchanged in the shards and in `train.jsonl`). The first 1,500
cleaned records are used. v2 uses seed 7. Plain PyTorch loop on the CPU; Hugging Face Transformers
for the model and tokenizer. Models: `s3://models/v1/`, `s3://models/v2/` and the GitHub Release
`models` (`model-v1.tar.gz` checksum = `models/v1/model.sha256` = [[FILL]]).

**Loss per epoch** (`training/loss.csv`, `training/loss_v2.csv`): [[FILL]]
Training time: [[FILL]].

**Validation scores** (`results/`, 100 commands, `tools/score.py`): [[FILL from results/score_table.md]]

| Model | JSON valid | Intent | Date | Time | Place | Full frame |
|---|---|---|---|---|---|---|
| Teacher phi3.5 | | | | | | |
| Untrained Pythia-70M | | | | | | |
| Student v1 | | | | | | |
| Student v2 | | | | | | |

[[FILL: discussion. What changed: base never produces the format; student reaches X% of the
teacher's full frame; where it fails (which slots); validity.]]

**Sequence-level vs logit-based distillation.**
(a) *Sequence-level* distillation trains the student on the teacher's **generated output**: the
teacher's reply is treated as the correct answer and the student is trained with ordinary
cross-entropy to produce the same token sequence. Only text is needed from the teacher.
(b) *Logit-based* (word-level) distillation trains the student to match the teacher's **full
probability distribution over the vocabulary at every position** (soft targets, usually with a KL
divergence and a temperature), so the student also learns how likely the alternatives were.
(c) It is **not possible here** because Ollama returns only the generated text, never the
teacher's logits, and because phi3.5 and Pythia use different tokenizers and vocabularies, so
their per-token distributions do not line up position by position.
(d) *Limitation:* the student can only copy the teacher, including its mistakes. It never sees
the true labels, so the teacher's [[FILL]]% full-frame accuracy is effectively a ceiling, and
`clean.py` removes replies the teacher got visibly wrong, which also removes some hard commands.

## 3. The inference service in a container

**Setup.** FastAPI on port 8000 (`service/app.py`). `POST /parse` returns only the four-key
object with `X-Model-Version` and `X-Served-By` (the Pod name); `/healthz` is always 200;
`/readyz` is 503 until the model is loaded. Configuration only from `MODEL_URI`, `MODEL_VERSION`,
`S3_ENDPOINT`, `MAX_NEW_TOKENS` (and `FAULT_INJECT`); credentials from the Secret
`s3-credentials`. At start-up the model files are downloaded from `MODEL_URI` in a background
thread. Every output is checked against `schema.json` (exact keys, intent in the eight, slots
string or null); otherwise 500 `{"error": "invalid_model_output"}`. Decoding is greedy and stops
at end-of-text or when the JSON object closes. Image: `python:3.11.10-slim`, CPU-only torch
2.4.1, all versions pinned, no weights; one command builds it (`make image`).

**Results** (`results/task3_container.txt`): image **[[FILL]]**; 50 sequential requests at 1 CPU
/ 1 GiB: **[[FILL]]/50** HTTP 200, no OOM kill, peak memory **[[FILL]]**; `FAULT_INJECT=1` gives
HTTP 500 with the exact body.

## 4. Kubernetes deployment, scaling and reliability

**Setup.** Namespace `app`: Deployment `parser` (2 replicas; requests 500m / 512Mi, limits 1 CPU /
1Gi), Service, Traefik Ingress for `/parse`, HPA 1 to 2 replicas at 70% CPU (scale-down
stabilisation shortened to 60 s). Readiness probe on `/readyz`, liveness on `/healthz`. Rolling
update with `maxSurge 1, maxUnavailable 0` and a 10 s `preStop` pause so a Pod leaves the Ingress
before it stops.

**Results.** [[FILL each from results/]]
- Through the Ingress: `results/task4_deploy.txt`.
- No ready endpoints while loading: `results/task4_coldstart.txt`.
- HPA: **1 -> 2 -> 1** replicas, timeline in `results/task4_hpa.txt`.
- Rolling update v1 -> v2 -> rollback under load: **[[FILL]]% failed** of **[[FILL]]** requests;
  `X-Model-Version` v2 after the update and **v1 after `rollout undo`** (`results/task4_rollout.txt`).
- Recovery: replicas back to 2 in **[[FILL]] s**, **[[FILL]]%** failed (`results/task4_recovery.txt`).
- Cold start: **[[FILL]] s, [[FILL]] s, [[FILL]] s**, median **[[FILL]] s**; logs show the download
  from SeaweedFS (`results/task4_coldstart_logs.txt`).
- Load balancing with two Ready replicas: **[[FILL]] / [[FILL]]** requests (`results/loadtest_headers.json`).

**Limitations.** The cluster is one node on one laptop: it shows Pod-level recovery, not fault
tolerance across machines; if the laptop or the node fails, everything fails. Both replicas share
the same CPU, so scaling out adds less capacity than on separate machines. metrics-server samples
every 15 s, so the HPA reacts with a delay; `maxReplicas: 2` caps throughput. The single SeaweedFS
Pod is a single point of failure.

## 5. Subnetting and network access control

Full table, working and rules in `network/subnets.md`; `nacl_sim.py` gives **6 / 6** on the
sample packets (`results/task5_nacl_check.txt`).

| Subnet | Network | Prefix | Usable range | Broadcast | Usable hosts |
|---|---|---|---|---|---|
| app | 10.20.0.0 | /22 | 10.20.0.1 to 10.20.3.254 | 10.20.3.255 | 1022 |
| public | 10.20.4.0 | /24 | 10.20.4.1 to 10.20.4.254 | 10.20.4.255 | 254 |
| data | 10.20.5.0 | /25 | 10.20.5.1 to 10.20.5.126 | 10.20.5.127 | 126 |
| management | 10.20.5.128 | /27 | 10.20.5.129 to 10.20.5.158 | 10.20.5.159 | 30 |

**Why reply rules and rule order matter.** A NACL is stateless: it does not remember connections,
so a reply is checked like any new packet. The response to a client goes out to the client's
ephemeral port (1024 to 65535) and needs its own outbound allow; the app subnet's answer comes back
to the load balancer's ephemeral port and needs its own inbound allow. Rules are evaluated from
the lowest number and the first match wins, so the deny for 198.51.100.0/24 (rule 100) must have a
lower number than the HTTP/HTTPS allows (200, 210); otherwise the allow would match first and the
abusive range would reach the web ports.

## 6. Reproducibility, testing and CI/CD

`make up` builds and deploys everything from a fresh clone in one command (venv, cluster,
SeaweedFS, buckets, data, service image, model from the Release, Deployment); `make down` deletes
the cluster. GitHub Actions (`.github/workflows/ci.yml`): lint (pyflakes) -> unit tests ([[FILL]]
tests: cleaning rules, checksum stability, service API and FAULT_INJECT, subnets, NACL) -> model
evaluation (downloads `model-v1.tar.gz` from the Release, verifies the checksum, runs `score.py`)
-> quality gate (`--min-validity 95`), plus a gitleaks secret scan (reports nothing).
Deliberately failing gate run with the untrained Pythia-70M: [[FILL: link]].
Passing run: [[FILL: link]]. AI use: `AI_USE.md`.

## 7. Performance, cost and review

**Load test** (standard command, through the Ingress, two replicas; `results/loadtest_stats.csv`,
`results/loadtest_locust.txt`): p50 **[[FILL]] ms**, p95 **[[FILL]] ms**, **[[FILL]] req/s**,
error rate **[[FILL]]%**. Per Pod (`kubectl top pods`, `results/task7_top_pods.txt`):
**[[FILL]]**. Cold start median **[[FILL]] s** (Task 4).

**Cost** (`scripts/cost.py`, `results/task7_cost.txt`). *Assumption:* two replicas billed for
their limits (1 vCPU, 1 GiB) for every hour, rate card 3.50 INR/vCPU-hour and 0.45 INR/GiB-hour.
[[FILL: the five lines from results/task7_cost.txt]]

**SLO.** Target: 99% of `/parse` requests return HTTP 200 within 30 s, over one standard
load-test run (2 minutes). Error budget = 1% of [[FILL: N]] requests = **[[FILL]] requests**;
used **[[FILL]]** ([[FILL]]% of the budget).

| Component | Evidence (measured) | Limitation found | Improvement proposed |
|---|---|---|---|
| Data and storage | [[FILL]] of 3,000 kept; labelling [[FILL]] min | single SeaweedFS Pod, no replication | replicated storage / volume snapshots |
| Model quality | full frame [[FILL]]% vs teacher [[FILL]]% | student copies teacher errors | bigger student or logit KD with a same-vocabulary teacher |
| Latency and throughput | p95 [[FILL]] ms, [[FILL]] req/s | one request at a time per Pod on 1 CPU | batching, int8 quantisation |
| Resource utilisation | [[FILL]] CPU, [[FILL]] MiB per Pod | CPU-bound at the limit | right-size the memory limit (~[[FILL]] MiB used of 1 GiB) |
| Reliability and recovery | recovery [[FILL]] s, cold start [[FILL]] s, rollout [[FILL]]% failed | single node | multi-node cluster, PodDisruptionBudget |
| Security and cost | 0 gitleaks findings; [[FILL]] INR per 1,000 requests | one shared S3 key with admin rights | per-service keys with read-only access; scale to 1 replica when idle |
