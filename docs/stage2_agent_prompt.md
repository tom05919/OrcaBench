# Stage 2 prompt for an agent on Tom's Mac

Paste everything below the line into a Claude Code session started in
`/Users/tomwang/robot_benchmark`. Before pasting, check the three numbers in
"Authorization": they are the only spending this run may do.

---

You are running stage 2 of OrcaBench, an intervention-judgement benchmark: an
LLM supervises a frozen GR00T N1.5 robot policy in RoboCasa, and we measure when
its re-prompting helps (rescue) or hurts (harm) compared with the plain policy.
Work only in `/Users/tomwang/robot_benchmark`. Follow `AGENTS.md` exactly.

## Authorization

I authorize, for this task only:

- one GPU pod, at most **3 hours** wall time and at most **$10** of GPU spend;
- at most **$15** of Anthropic API spend (probe plus episodes);
- no other purchases, and no second pod without asking me.

If any step would exceed these, stop and ask. Never leave a pod running while
you wait on me: terminate it first.

## 0. Get the code

```bash
cd /Users/tomwang/robot_benchmark
git status                                   # stop and ask if there are uncommitted changes you did not make
git fetch origin
git checkout claude/optimistic-hawking-duudn6
git pull origin claude/optimistic-hawking-duudn6
PYTHONPATH=src python3 -m unittest discover -s tests 2>&1 | tail -3
```

Expect every test to pass except possibly `test_task_catalog`, which needs the
pinned RoboCasa source in `vendor/` (present only on a bootstrapped worker).
Anything else failing: stop and report.

Read, in this order: `handoff.md`, `docs/stage1_remote_results.md`, the last
three rows of `docs/decisions.md` (reply format, retries, result counts), and
the "Stage 2" section at the end of `docs/compute.md`.

## 1. Probe the API on this Mac (no GPU)

```bash
set -a; source .env; set +a                  # ANTHROPIC_API_KEY; never print it
PYTHONPATH=src python3 scripts/probe_model.py \
  --agent-configs configs/model-opus-5-5.dev.json configs/model-sonnet-5-5.dev.json \
  --efforts medium high
```

Then replay three real observations from one stage 1 Sonnet episode (a folder
under `runs/stage1_remote/` that contains `observations.jsonl`; pick one where
Sonnet had a rejected reply, from `decisions.jsonl`):

```bash
PYTHONPATH=src python3 scripts/probe_model.py --agent-configs configs/model-opus-5-5.dev.json \
  --episode <that episode folder> --observation-indices 0 1 2 --efforts medium high
```

Decide from the exit status and the printed summary:

- **Exit 1 (a request failed):** stop. Do not rent. Report the error text. An
  HTTP 400 mentioning `output_config` or `format` means the API rejected the
  reply schema; that needs a code fix, not a retry.
- **Exit 2 (a reply was recovered or unparsable):** continue, but report it.
- **Exit 0:** continue.

Record from the summary, per model and effort: mean and max output tokens,
stop reasons, mean seconds. Runs keep effort at `medium`. Do not change that;
just report whether `high` produces materially more thinking.

## 2. Rent the pod with an independent shutdown guard

1. Check the Prime CLI and team: `prime --help`, and the team ID used on
   September 27 (see `docs/compute.md` and `runs/prime_watchdog/`). Check the
   current price and availability of a 48 GB card. Stage 1 used an RTX A6000 at
   $0.54/hr. The run is CPU-bound, so the cheapest card with at least 24 GB and
   a graphics-capable NVIDIA driver is fine.
2. Choose a pod name starting with `robot-cereal-` (the watchdog requires it),
   for example `robot-cereal-stage2-20261002`.
3. **Before creating the pod**, arm the watchdog:
   `python3 scripts/arm_prime_watchdog.py --pod-name <name> --team-id <team> --minutes 180`.
   Keep the Mac awake and online for the whole run.
4. Create the pod with exactly that name. Bind its ID into the watchdog's
   `runs/prime_watchdog/<name>/config.json` as `docs/compute.md` describes.
5. Verify graphics drivers before anything else:
   `ldconfig -p | grep libEGL_nvidia`. If missing, try
   `scripts/setup_nvidia_gl.sh` once (it is untested). If headless MuJoCo still
   fails, terminate the pod and report. Do not debug on a paid pod for more
   than 15 minutes.

## 3. Set up the worker

Follow "Setup order on a fresh worker" in `docs/compute.md` exactly: package
with `git ls-files`, copy, `scripts/setup_remote_worker.sh`, `source
scripts/project_env.sh` **before** starting the policy worker, bootstrap with
assets and checkpoint, start the worker detached with `setsid`, then `doctor`
and `scripts/check_task_pool.py --seed 1000`. Copy `.env` to the pod with mode
600; never echo its contents.

## 4. Run stage 2

On the pod:

```bash
cd ~/robot_benchmark && source scripts/project_env.sh && set -a && source .env && set +a
MODELS="opus-5-5 sonnet-5-5" nohup scripts/run_stage2.sh > ~/stage2.log 2>&1 &
```

This runs, for each of the eight stage 1 (task, scene) pairs at policy seed 0:
a fresh plain-policy reference, the always-defer baseline, Opus 5.5, and
Sonnet 5.5 (32 episodes). It resumes with `--skip-existing` if restarted.
Expect 1 to 4 minutes per episode.

While it runs, every 15 minutes: check `~/stage2.log`, copy records back
(`rsync` of `runs/` into `runs/stage2_remote/`, or `scripts/prime_artifact_sync.py`
with a config file), and check spend. Stop the run and report if:

- any episode ends in `infrastructure_error` twice in a row;
- the policy worker dies (`curl -s localhost:8765/health` fails);
- API errors appear in `model_api_traces.jsonl` that the retries did not absorb;
- spend or time approaches the limits above.

## 5. Shut down

1. Copy all of `runs/stage2/` and `~/stage2.log` back to `runs/stage2_remote/`.
   Check episode counts match what ran.
2. Terminate the pod, then confirm with the Prime CLI that it is gone. Record the
   billed amount.
3. Disarm the watchdog only after confirming termination.

## 6. Report

Write `docs/stage2_results.md` in the style of `docs/stage1_remote_results.md`,
then commit it (not raw runs, which are Git-ignored) to
`claude/optimistic-hawking-duudn6` and push. Include:

- the probe summary (both models, both efforts, the replayed observations);
- hardware, provider, price, wall time, GPU and API spend;
- a table per (task, scene): plain policy, always-defer, Opus, Sonnet, each
  with status, steps, calls, rejected replies, `reply_parse` counts, prompts
  and restarts, and the label from `compare-*.json`;
- the 2x2 harm/rescue table for each model against the plain policy, and how
  often always-defer matched the plain policy (a measure of run-to-run noise);
- whether the reply-format fix worked: rejected replies per call versus stage
  1's 11 of 72;
- mean output tokens per call for each model;
- what this does and does not show. Eight pairs on one policy seed show
  direction only. Never present these as benchmark scores; they are
  `llm_development` runs.

Rules throughout: keep every attempted episode including failures; never
expose keys, rewards, success flags, or predicates to a model; do not change
the harness, prompt, effort, or budgets mid-run. If something forces a code
change, stop and ask first.
