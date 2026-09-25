# Robot Policy Orchestration Benchmark

This pilot compares different LLM orchestrators while holding one fixed library
of learned robot skills constant. The LLM sees RGB, proprioception, the task,
and public execution history. It chooses which skill runs and when to observe,
interrupt, switch, retry, or declare completion; the learned policy alone emits
low-level controls.

The task is RoboCasa `CerealAndBowl` in MuJoCo/robosuite. The four fixed skills
are `open_cabinet`, `transfer_cereal`, `transfer_bowl`, and `close_cabinet`.
There are no artificial disturbances, scripted manipulation substitutes, or
training. The model may make at most 100 calls, choose 1–100 control steps per
advancing decision, and use at most the upstream 4,350-step horizon. Physics
pauses while the LLM reasons.

## Status

The local foundation is implemented: source and checkpoint identities are
pinned, the coordinator and isolated learned-policy worker have runnable entry
points, and contract tests cover observation isolation, step accounting, policy
state, queue cancellation, budget handling, scoring, qualification, and result
aggregation. The Prime Intellect GPU worker is not provisioned, so this project
does **not** claim any learned-policy rollout, skill success rate, full-task
success rate, or LLM benchmark result.

The first policy candidate is the official GR00T checkpoint at
`gr00t_n1-5/multitask_learning/checkpoint-120000`; the official π0.5 checkpoint
is the predefined fallback. RoboCasa and GR00T pin incompatible Tianshou
versions, so policy inference runs in a separate HTTP worker environment rather
than a combined dependency environment.

## Evaluation contract

Primary success requires both of the following before either budget is exhausted:

1. the cereal contacts the counter, the bowl contacts the counter, and the
   cabinet is closed; and
2. the LLM issues `complete` while that physical predicate is true.

A false completion ends the episode. The upstream task text mentions “next to
the milk,” but the upstream evaluator does not score that relation, so the
model-facing goal follows the physical predicate. Reward, success flags, object
coordinates, simulator predicates, and evaluator feedback are never exposed to
model adapters.

Read the complete [protocol](docs/protocol.md), [feasibility plan](docs/feasibility.md),
[research comparison](docs/research.md), [decision log](docs/decisions.md),
[policy card](docs/policy_card.md), [GPU runbook](docs/compute.md), and
[roadmap](docs/roadmap.md).

## Local foundation checks

The dependency-free contract suite runs on Python 3.11 or 3.12:

```bash
cd /Users/tomwang/robot_benchmark
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 scripts/bootstrap_gpu.py --dry-run --skip-gpu-check
```

These checks validate local contracts and mocks only. They do not qualify a
learned policy.

## Prime Intellect worker

Copy this project to a persistent directory on the Linux GPU worker, install
`uv`, and run the pinned setup. The first command prepares RoboCasa, robosuite,
GR00T, the benchmark, assets, and the verified GR00T checkpoint in separate
project-local environments:

```bash
cd /path/to/robot_benchmark
source scripts/project_env.sh
python3 scripts/bootstrap_gpu.py --download-assets --download-checkpoint
.venv-groot/bin/python -m robot_benchmark.policy_worker \
  --backend groot \
  --checkpoint checkpoints/groot/checkpoint-120000 \
  --port 8765
```

In a second shell on the same worker:

```bash
cd /path/to/robot_benchmark
source scripts/project_env.sh
.venv-sim/bin/robot-benchmark doctor --policy-url http://127.0.0.1:8765
.venv-sim/bin/robot-benchmark smoke-sim --seed 0 --output runs/smoke/seed-0
.venv-sim/bin/robot-benchmark feasibility \
  --mode ordinary --seeds 0,1,2 --output runs/feasibility/groot-ordinary
.venv-sim/bin/robot-benchmark feasibility \
  --mode supervisor --seeds 100,101,102 \
  --output runs/feasibility/groot-supervisor
```

These are development runs. Build the complete audited evidence file from the
recorded qualification traces, then evaluate the gate:

```bash
.venv-sim/bin/robot-benchmark qualify \
  --evidence runs/qualification/groot-evidence.json \
  --output runs/qualification/groot-report.json
.venv-sim/bin/robot-benchmark publish-policy-card \
  --qualification runs/qualification/groot-report.json \
  --output runs/release/cereal-and-bowl-qualified.json
.venv-sim/bin/robot-benchmark freeze-release \
  --qualification runs/qualification/groot-report.json \
  --task-config runs/release/cereal-and-bowl-qualified.json \
  --output runs/release.json
```

`freeze-release` refuses a failed or incomplete report, a different connected
checkpoint, a mismatched qualification contract, missing trace evidence, or
trace paths outside the project. If GR00T
completes qualification and fails, prepare the predefined π0.5 fallback with
`--include-pi05 --download-pi05-checkpoint`; do not start it merely because the
GR00T setup is incomplete.

## Model runs

Copy `configs/model-http.example.json` or `configs/model.example.json`, replace
the placeholder with an exact model identifier, and keep model credentials in
the named environment variable. Development runs are labeled and cannot be
mistaken for official results:

```bash
.venv-sim/bin/robot-benchmark run \
  --development \
  --agent-config configs/my-model.json \
  --seeds 0,1,2 \
  --output runs/models/my-model-development
```

After qualification, run every model against the same release manifest and
paired evaluation seeds:

```bash
.venv-sim/bin/robot-benchmark run \
  --release runs/release.json \
  --task-config runs/release/cereal-and-bowl-qualified.json \
  --agent-config configs/my-model.json \
  --seeds 1000,1001,1002,1003,1004,1005,1006,1007,1008,1009,1010,1011,1012,1013,1014,1015,1016,1017,1018,1019 \
  --output runs/models/my-model
.venv-sim/bin/robot-benchmark summarize runs/models \
  --output runs/results.json
```

Pinned external source metadata is in
[`configs/sources.lock.json`](configs/sources.lock.json). The planned October 16,
2026 pilot requires a backend to pass 8/10 valid trials for every declared
skill-entry condition, 16/20 valid diagnostic full tasks, and the matched
continuation relevance check before any LLM result is reported.
