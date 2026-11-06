# AI use

This file was drafted with Claude at my request, from the conversation in which we built the
project. I read it and confirm it describes what happened.

## Tools used
- **Claude (Anthropic)**, in one claude.ai conversation from 4 to 6 November 2026. Claude could
  run code in its own sandbox and, from 5 November, push commits to this repository (those
  commits carry a `Co-Authored-By: Claude` line).

## What I used it for
- Reading the brief with me and planning the order of work around my deadline.
- Writing almost all code and configuration: `cluster/k3d.yaml`, the Kubernetes manifests, the
  labelling worker, `clean.py`, training and evaluation scripts, the FastAPI service, both
  Dockerfiles, the Makefile and scripts, the unit tests, the CI workflow, and the network files.
- The teacher prompt: Claude wrote the first version, and after my first `make pilot` it drafted
  rules 4 to 7 from the mistakes the teacher made on those 20 commands. I decided to stop after
  two rounds and start labelling.
- Debugging my Windows setup: port 8080 was held by MiniTool ShadowMaker's `MTAgentService`;
  two Windows Firewall Block rules for `ollama.exe` stopped WSL from reaching Ollama; restarting
  the Windows NAT service cut WSL's internet until I restarted Windows.
- Drafting `report/report.pdf` from the files in `results/`.
- Claude triggered the deliberately failing CI run (untrained model) through the GitHub API.

## How I checked the output
- I ran every step myself on my laptop with the `make` targets. Every measurement in
  `results/` comes from my machine, not from Claude's sandbox.
- Prompt: `make pilot` full frame went from 30% to 40%; then the teacher scored 58% full frame
  on all 100 validation commands (`results/teacher_validation.json`).
- Data: `clean.py` reported 0 missing and 0 repeated ids, and the counts add up to 3,000.
- Before I ran it, Claude tested the storage, worker and container code in its sandbox against a
  real SeaweedFS (two workers, one killed and resumed, identical checksum on re-runs).
- The Task 4 scripts could not be tested there (no working Kubernetes), so my laptop was the
  first real run; I checked each output and re-ran the rollout test after a fix.
- Lint and 16 unit tests run in CI; I have one passing run and one run that stops at the
  quality gate.
- `nacl_sim.py` gives 6 / 6; the subnet table is computed by `scripts/subnets.py` and checked by
  a unit test.
- Report: Claude cross-checked every number in the report against `results/` with a script
  (24 checks); I read the report and confirmed the hardware details and how the prompt tuning is
  described.

## Mistakes caught and fixed
- `train.py` first uploaded the 282 MB weights in a single request; SeaweedFS dropped the
  connection. Fixed with multipart upload (8 MB parts), a `make upload-model` target so I did not
  have to retrain, and a 1 GiB memory limit for SeaweedFS.
- The first rolling-update test sent its "after rollback" request while the last v2 Pod was
  still in its 10 s shutdown pause, so v2 answered. The script now waits until the old Pods are
  gone; the re-run shows v1 on all 4 requests.
- Claude's early advice to use `repetition_penalty` or `no_repeat_ngram_size` was wrong for JSON
  output (JSON repeats `": "` and `null` by design); it corrected this before training.
- The labelling progress output kept printing errors from Pods that had already been replaced;
  this was only cosmetic.
