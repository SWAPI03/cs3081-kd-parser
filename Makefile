# Knowledge distillation + deployment of a command parser on a local k3d cloud (CS3081).
# Run every target from the repository root, in bash (Linux, macOS or WSL).
#
# From a fresh clone:   make up      (cluster, storage, service, everything)
# Tear down:            make down
SHELL := /bin/bash
CLUSTER := kdcloud
PY := .venv/bin/python
SUBSET ?=
N ?= 20

.PHONY: help venv up down pilot label label-local clean-data train train-v2 eval eval-teacher \
        release image memtest deploy test lint load rollout recovery coldstart hpa balance cost network

help:
	@grep -E '^[a-z0-9-]+:.*?## ' Makefile | sed 's/:.*## /\t/'

venv: ## create .venv with the laptop-side tools
	@test -x $(PY) || (python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -r requirements-dev.txt)

up: ## Task 6: build and deploy everything from a fresh clone
	bash scripts/up.sh

down: ## Task 6: delete the cluster
	k3d cluster delete $(CLUSTER)

# ---------- Task 1 ----------
pilot: venv ## try the teacher prompt on the first N validation commands (default 20)
	$(PY) scripts/eval_teacher.py --limit $(N)

label: ## run the two labelling workers as Pods in namespace pipeline
	bash scripts/label.sh

label-local: venv ## FALLBACK: run the two workers on the laptop instead
	bash scripts/label_local.sh

clean-data: venv ## clean the shards -> datasets/v1/train.jsonl + train.sha256
	$(PY) worker/clean.py

# ---------- Task 2 ----------
train: ## fine-tune Pythia-70M (v1); `make train SUBSET=50` for a quick check
	bash scripts/train.sh v1 $(SUBSET)

train-v2: ## second model version for Task 4 (different seed)
	bash scripts/train.sh v2

eval: ## score untrained Pythia-70M, student v1 and v2 on validation.jsonl
	bash scripts/evaluate.sh

eval-teacher: venv ## score the teacher on validation.jsonl (needs Ollama)
	$(PY) scripts/eval_teacher.py

release: ## publish models/v1 and models/v2 as GitHub Release assets (needs gh)
	bash scripts/release.sh

# ---------- Task 3 ----------
image: ## build the inference service image (no weights inside)
	docker build -f service/Dockerfile -t kd-parser:v1 .

memtest: ## 50 sequential requests to the container at 1 CPU / 1 GiB, peak memory
	bash scripts/memtest.sh

# ---------- Task 4 ----------
deploy: ## (re)deploy the service: Deployment, Service, Ingress, HPA
	bash scripts/deploy_app.sh

rollout: venv ## rolling update v1 -> v2 under load, then rollback
	bash scripts/task4_rollout.sh

recovery: venv ## delete a Pod under load, replicas come back
	bash scripts/task4_recovery.sh

coldstart: ## delete all Pods three times, median creation -> Ready
	bash scripts/task4_coldstart.sh

hpa: venv ## autoscaling 1 -> 2 under load and back to 1
	bash scripts/task4_hpa.sh

balance: venv ## load test with exactly two Ready replicas
	bash scripts/task4_balance.sh

# ---------- Task 5 ----------
network: ## subnet table + NACL check against the sample packets
	mkdir -p results
	python3 scripts/subnets.py | tee results/task5_subnets.txt
	python3 tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check | tee results/task5_nacl_check.txt

# ---------- Tasks 6 and 7 ----------
test: venv ## unit tests
	bash scripts/train.sh deps
	$(PY) -m pytest -q tests

lint: venv ## static checks
	$(PY) -m pyflakes worker training service scripts tests

load: venv ## the standard marking load test
	mkdir -p results
	.venv/bin/locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m \
	    --host http://localhost:8080 --csv results/loadtest

cost: venv ## Task 7 cost per 1,000 requests from results/loadtest_stats.csv
	$(PY) scripts/cost.py
