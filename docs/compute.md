# Prime Intellect GPU runbook

## Worker requirements

The authoritative feasibility run requires a persistent Linux CUDA worker. Use
Python 3.11 and an NVIDIA GPU with enough memory for the selected backend. Record
the provider instance type, GPU model and count, VRAM, CPU, RAM, disk size,
CUDA driver, region, rental start/end time, and cost in the feasibility report
before running counted trials. No machine has been selected yet.

Allocate at least 80 GiB of free persistent storage for the GR00T path. The
RoboCasa assets are about 10 GB, the verified GR00T inference checkpoint is
about 7.1 GiB, and package/source caches and environments need additional room.
The π0.5 fallback adds about 11.6 GiB of inference parameters and another
environment. Checkpoint training state is deliberately excluded.

All project sources, environments, caches, assets, checkpoints, and outputs are
kept under the copied project root. `scripts/project_env.sh` exports project-local
cache directories and headless MuJoCo rendering settings.

## Transfer and preflight

Copy `/Users/tomwang/robot_benchmark` to persistent storage on the worker. Do
not copy local virtual environments, caches, checkpoints, or runs. Install `git`,
Python 3.11, `uv`, an NVIDIA driver compatible with the pinned framework wheels,
and basic EGL system libraries. Then inspect the entire setup without changing
the worker:

```bash
cd /path/to/robot_benchmark
source scripts/project_env.sh
python3 scripts/bootstrap_gpu.py --dry-run
```

The real bootstrap checks Linux, `git`, `uv`, `nvidia-smi`, and free space. It
clones every source at the commit in `configs/sources.lock.json`, creates
separate core, simulator, and GR00T environments, writes resolved package
snapshots under `.cache/bootstrap/freezes`, and can download assets and the
checkpoint:

```bash
python3 scripts/bootstrap_gpu.py --download-assets --download-checkpoint
```

The checkpoint downloader uses an immutable Hugging Face revision, verifies
every expected byte size and SHA-256 digest, and writes
`checkpoints/groot/checkpoint-120000.manifest.json`. An existing mismatched file
causes a hard failure unless the operator explicitly uses `--force`.

## Start and verify GR00T

Run a single worker on loopback. It verifies the complete checkpoint manifest
before loading the policy and permits only one episode stream:

```bash
.venv-groot/bin/python -m robot_benchmark.policy_worker \
  --backend groot \
  --checkpoint checkpoints/groot/checkpoint-120000 \
  --port 8765
```

In another shell, run both preflight checks. `doctor` returns nonzero if the
RoboCasa imports or the learned-policy health check fail. `smoke-sim` creates a
real task instance, audits the horizon, renders the three public cameras, and
records an evaluator-only initial state without applying a scripted action.

```bash
source scripts/project_env.sh
.venv-sim/bin/robot-benchmark doctor \
  --policy-url http://127.0.0.1:8765 \
  --output runs/preflight.json
.venv-sim/bin/robot-benchmark smoke-sim \
  --seed 0 --output runs/smoke/seed-0
```

Do not count a trial until the worker identity, camera dimensions, action schema,
reset behavior, simulator step, and append-only records have passed inspection.

## Feasibility order

First reproduce ordinary whole-task execution with the official task instruction.
Then run the four fixed instructions under the privileged diagnostic supervisor.
The supervisor chooses skills from simulator truth but never emits controls;
every physical action must come from the learned checkpoint.

```bash
.venv-sim/bin/robot-benchmark feasibility \
  --mode ordinary \
  --seeds 0,1,2,3,4,5,6,7,8,9 \
  --output runs/feasibility/groot-ordinary

.venv-sim/bin/robot-benchmark feasibility \
  --mode supervisor \
  --supervisor-interval 50 \
  --seeds 100,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119 \
  --output runs/feasibility/groot-supervisor
```

The generic supervisor run establishes full-task feasibility. Per-skill
qualification and matched continuation evidence must be audited from naturally
reached entry states as specified in `docs/feasibility.md`; the CLI does not
infer trial validity from aggregate episode success. Populate a copy of
`configs/qualification.example.json` with relative trace paths and run
`robot-benchmark qualify`. Copy the qualification contract hash from the
diagnostic episode manifests into that evidence file. Preserve incomplete and
failed attempts.

After the gate passes, publish the audited skill statistics into a model-visible
task config. This step strips private trace paths while retaining per-condition
counts, success rates, Wilson intervals, durations, and observed limitations:

```bash
.venv-sim/bin/robot-benchmark publish-policy-card \
  --qualification runs/qualification/groot-report.json \
  --output runs/release/cereal-and-bowl-qualified.json
```

Pass that qualified task config to both `freeze-release` and every official
`run`. The release command verifies its qualification-report digest.

## π0.5 fallback

Prepare π0.5 only after a complete GR00T gate failure or a documented
incompatibility that cannot be corrected without changing the contract:

```bash
python3 scripts/bootstrap_gpu.py \
  --include-pi05 --download-pi05-checkpoint
.venv-pi05/bin/python -m robot_benchmark.policy_worker \
  --backend pi05 \
  --checkpoint checkpoints/pi05/75000 \
  --port 8765
```

Repeat all feasibility evidence for π0.5. Never combine backends within one
model comparison.

## Recovery and reproducibility

The source checkout and checkpoint downloads are restart-safe. Rerunning the
bootstrap accepts a source only when its current `HEAD` equals the locked commit.
The checkpoint downloader resumes `.part` files and rehashes completed files.
Move an unexpected source checkout aside instead of mutating it in place.

Before the official comparison, preserve the environment freezes, preflight
report, checkpoint manifest, qualification evidence/report, release manifest,
model configuration files without secrets, and every episode directory. Rebuild
on a clean worker from the same source locks and compare these identities before
calling the release reproducible.

Each episode stores zero-padded PNGs in `video_frames/` at the contract's fixed
two-step interval. Render representative success and failure sequences with a
local video tool at 10 fps and retain the command and output beside the episode;
the PNG sequence remains the canonical recorded artifact.
