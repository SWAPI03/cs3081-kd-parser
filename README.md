# Command parser: knowledge distillation on a local cloud (CS3081 mini project)

**Student:** Swapnil Yadav, roll number 230103015

A teacher model (phi3.5, 3.8B, served by Ollama) labels 3,000 voice-assistant commands with a
four-key JSON frame. A 70M-parameter student (EleutherAI/pythia-70m) is fine-tuned on those
replies (sequence-level knowledge distillation) and served by a FastAPI service on a local k3d
Kubernetes cluster, with SeaweedFS as S3-compatible object storage.

```
POST /parse {"text": "set an alarm for seven thirty am tomorrow"}
-> {"intent": "alarm_set", "date": "tomorrow", "time": "seven thirty am", "place": null}
```

## Links
| What | Where |
|---|---|
| GitHub repository | https://github.com/SWAPI03/cs3081-kd-parser |
| Assessed commit | tag `final`: https://github.com/SWAPI03/cs3081-kd-parser/tree/final |
| Model Release (models, tokenizer, version info, checksums) | https://github.com/SWAPI03/cs3081-kd-parser/releases/tag/models |
| CI run, all stages passing | https://github.com/SWAPI03/cs3081-kd-parser/actions/runs/42074609367 |
| CI run failing at the quality gate (untrained model) | https://github.com/SWAPI03/cs3081-kd-parser/actions/runs/42074783612 |
| Report | `report/report.pdf` |
| Handwritten reflection | `230103015.pdf` (in the submitted zip) |

## Prerequisites
Run everything from bash (Linux, macOS, or WSL2 on Windows). Ollama can run on the host OS.

| Tool | Version used | Purpose |
|---|---|---|
| Docker | Docker Desktop (WSL2 backend) | k3d nodes, image builds |
| k3d | v5.7.4 | local Kubernetes (k3s v1.31.4) |
| kubectl | v1.31.4 | cluster control |
| Python | 3.10 to 3.12 | scripts, training |
| make, git | any | entry points |
| Ollama + `phi3.5` | latest | teacher model (Task 1 and teacher evaluation only) |
| gh (GitHub CLI) | any | publishing the model Release (`make release`) |

If Ollama runs on Windows, set `OLLAMA_HOST=0.0.0.0` (PowerShell: `setx OLLAMA_HOST 0.0.0.0`,
then restart Ollama) so the cluster can reach it at `host.k3d.internal:11434`.

## From a fresh clone
```bash
make up        # venv, cluster, SeaweedFS, buckets, service image, model, deployment
make down      # delete the cluster
```

## Task by task
Run in this order. Every command writes its evidence to `results/`.

```bash
# Task 1: storage and teacher labelling
make up                    # cluster + SeaweedFS + buckets + commands_pool.jsonl uploaded
make pilot                 # teacher prompt on 20 validation commands, scored
make label                 # two worker Pods in namespace pipeline (SHARD_INDEX 0 and 1)
make clean-data            # datasets/v1/train.jsonl + train.sha256 + results/clean_counts.json

# Task 2: student training and evaluation
make train SUBSET=50       # quick check (about a minute)
make train                 # v1 -> models/v1 (local + s3://models/v1/), training/loss.csv
make train-v2              # v2 (seed 7) -> models/v2, training/loss_v2.csv
make eval-teacher          # teacher on validation.jsonl -> results/teacher_validation.json
make eval                  # untrained Pythia-70M, student v1, v2 -> results/ + score table
make release               # model-v1.tar.gz, model-v2.tar.gz as GitHub Release assets

# Task 3: the container
make image                 # build kd-parser:v1 (CPU-only torch, no weights)
make memtest               # 1 CPU / 1 GiB, endpoints, FAULT_INJECT, 50 requests, peak memory

# Task 4: Kubernetes
make deploy                # Deployment (2 replicas), Service, Ingress, HPA in namespace app
make coldstart             # 3 runs: delete all Pods, creation -> Ready, download logs, endpoints
make rollout               # v1 -> v2 under load, then rollout undo
make recovery              # delete one Pod under load
make hpa                   # 1 -> 2 replicas under load and back to 1
make balance               # the standard load test with exactly 2 replicas (also Task 7)

# Task 5
make network              # subnet table + nacl_sim.py check -> results/

# Tasks 6 and 7
make lint && make test     # also run in GitHub Actions (.github/workflows/ci.yml)
make cost                  # cost per 1,000 requests from results/loadtest_stats.csv
make load                  # the standard marking command on its own
```

Rolling update by hand:
```bash
kubectl -n app set env deployment/parser MODEL_VERSION=v2 MODEL_URI=s3://models/v2
kubectl -n app rollout undo deployment/parser
```

## Repository layout
| Path | What |
|---|---|
| `cluster/k3d.yaml` | cluster definition |
| `k8s/` | manifests: namespaces, SeaweedFS (`data`), workers (`pipeline`), service (`app`) |
| `prompts/teacher_prompt.txt` | the teacher prompt |
| `worker/` | labelling worker, `clean.py`, S3 helpers |
| `datasets/` | copy of the teacher shards and the cleaned training set (no weights) |
| `data/`, `tools/`, `network/packets_sample.jsonl` | the provided student kit, unchanged |
| `results/` | every measured result and log |
| `training/` | `config.yaml` (all hyper-parameters), `train.py`, `predict.py`, loss per epoch |
| `service/` | FastAPI app, shared inference code, Dockerfile |
| `network/` | `subnets.md` (Task 5 table and explanation), `nacl.json` |
| `.github/workflows/ci.yml` | lint, tests, evaluation from the Release, quality gate, gitleaks |
| `scripts/` | the scripts behind each `make` target |
