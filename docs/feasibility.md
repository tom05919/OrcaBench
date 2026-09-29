# Learned-policy feasibility plan

## Current status

Feasibility is **pending**. A temporary Prime Intellect GPU worker ran three
live development episodes on September 27 and was terminated after all records
were copied. The episodes do not satisfy the reference-prompt or full-task trial
counts, so no qualified success rate or model comparison can be claimed.

Source inspection and the first live runtime pass established:

| Item | Status | Evidence |
|---|---|---|
| RoboCasa task predicate and horizon | Source-verified | Pinned `CerealAndBowl` source and dataset registry: cereal/counter contact, bowl/counter contact, closed cabinet; horizon 4,350 |
| Checkpoint locations | Revision-pinned | `configs/sources.lock.json` pins the official checkpoint repository and GR00T/π0.5 subdirectories |
| Coordinator/worker compatibility | Live worker verified | Pinned RoboCasa requires MuJoCo 3.3.1, NumPy 2.2.5, and Tianshou 0.4.10; pinned GR00T requires Tianshou 0.5.1; isolated environments communicated successfully |
| Runner operation semantics | Unit-tested and live-exercised | Free-form prompt replacement, queue discard, continuation, and pause/step behavior ran with Opus 5.5 and the pinned GR00T worker |
| Learned-policy prompt execution | Live development evidence | GR00T completed two diagnostic episodes and one Opus-directed episode; all failed the physical goal, and none count as a model comparison |
| Qualification gates | Incomplete | No reference-prompt entry condition has ten valid trials; one diagnostic full task failed; missing trials are neither passes nor failures |

Static inspection and mock policies cannot qualify a learned policy.

## Runtime isolation

Use two separately locked environments connected by an HTTP policy interface:

1. The coordinator environment owns MuJoCo, robosuite, RoboCasa, episode state,
   observations, action stepping, recording, and the evaluator. It uses the
   RoboCasa-compatible dependency set, including Tianshou 0.4.10.
2. The GPU worker environment owns the selected learned policy and checkpoint.
   The GR00T candidate uses its pinned dependency set, including Tianshou 0.5.1.
3. The coordinator sends only policy observations and the active prompt chosen
   through `run_policy`. The worker returns learned action chunks in the pinned
   action schema. Evaluator truth never crosses this interface.

Do not resolve the Tianshou conflict by relaxing one environment into a single
untested dependency mix. Record the exact environment images or locks, health
checks, checkpoint digest, and worker identity in each manifest.

## Qualification sequence

Qualification starts with the pinned GR00T checkpoint. The π0.5 checkpoint is
attempted only if a complete GR00T qualification produces a gate failure or a
documented incompatibility that cannot be fixed without changing the evaluation
contract. A missing worker, missing asset, setup error, or incomplete trial set
is pending, not failure. Once a backend passes, lock it for every compared LLM.

### 1. Static and transport checks

- reproduce every digest in `configs/sources.lock.json`;
- build the isolated coordinator and policy environments;
- load the exact checkpoint and record its identity;
- validate worker health, observation serialization, action shape, finite values,
  reset behavior, and deterministic seed plumbing;
- reset `CerealAndBowl`, render all three model cameras, and step only actions
  returned by the learned worker.

These checks can expose infrastructure faults but do not count toward either
success gate.

### 2. Per-reference-prompt-entry gate

Run ten valid diagnostic trials for each declared reference-prompt-entry
condition. Every reference prompt has a nominal condition and a naturally
encountered intermediate condition, for eight required rows. Initial states must
come from ordinary task resets and natural prefixes executed by the learned
policy; do not teleport objects, inject control noise, alter contacts, or script
manipulation. The hand-authored diagnostic supervisor may read truth to identify
whether the required starting condition and tested outcome were achieved and to
choose when to stop. The qualification evidence schema retains the historical
`skill` and `skill_conditions` keys; each such identifier denotes one exact
reference prompt.

| Reference prompt | Entry condition | Condition checked after learned execution | Gate |
|---|---|---|---|
| `open_cabinet` | Nominal ordinary reset with the task cabinet closed | The task cabinet is open | at least 8 of 10 valid trials |
| `open_cabinet` | Naturally reached intermediate state with the cabinet closed after prior learned execution | The task cabinet is open | at least 8 of 10 valid trials |
| `transfer_cereal` | Nominal learned `open_cabinet` prefix; cereal remains off counter | The cereal contacts the task counter | at least 8 of 10 valid trials |
| `transfer_cereal` | Naturally stopped or failed learned state in which transfer remains possible | The cereal contacts the task counter | at least 8 of 10 valid trials |
| `transfer_bowl` | Nominal learned `open_cabinet` prefix; bowl remains off counter | The bowl contacts the task counter | at least 8 of 10 valid trials |
| `transfer_bowl` | Naturally stopped or failed learned state in which transfer remains possible | The bowl contacts the task counter | at least 8 of 10 valid trials |
| `close_cabinet` | Nominal learned prefix with the task cabinet open | The task cabinet is closed | at least 8 of 10 valid trials |
| `close_cabinet` | Naturally reached intermediate state with cabinet open after prior learned execution | The task cabinet is closed | at least 8 of 10 valid trials |

Every row must independently reach 8/10. An aggregate cannot hide a weak
reference prompt. A target-prompt trial begins only after its required start is
observed; a prefix failure is retained as evidence about the prefix prompt and
does not become a target-prompt attempt. A valid trial that runs its declared
budget without meeting its condition is a failure. An unrun trial or an attempt
cut short by infrastructure is incomplete and is recorded without entering the
numerator or denominator until the trial set is completed.

### 3. Full-task diagnostic gate

Run twenty valid `CerealAndBowl` episodes with the diagnostic supervisor and the
same four reference prompts. The first full-task attempts reproduce the ordinary
sequence—open cabinet, transfer cereal, transfer bowl, close cabinet—without
disturbance. Subsequent attempts may exercise only failures and handoffs that
arise naturally from learned execution, by continuing a queue, resending a
prompt to reset it, selecting another reference prompt, and varying observation
intervals. Do not inject failures or perturb the scene.

Passing requires physical task success in at least 16 of 20 valid episodes under
the source predicate. Preserve all attempts, including unsuccessful and
infrastructure-incomplete episodes. The diagnostic supervisor's privileged view
and results remain separate from model evaluation.

### 4. Supervisory relevance gate

From naturally encountered recorded states, identify matched continuation cases
where at least two allowed supervisory choices can be evaluated without altering
the scene: for example omit the prompt to continue the pending queue versus
resend the same prompt to reset it, or continue versus supply another reference
prompt. Preserve the common prefix and both continuation traces. Record the
state-selection rule before inspecting continuation outcomes. Qualification
remains `pending_relevance` unless the retained cases show that at least one
allowed supervisory decision changes the physical outcome or resource use in a
way the benchmark can score. Report every investigated case, including null
results. Do not manufacture a failure state. This gate qualifies orchestration
with the declared reference prompts; it does not establish the effectiveness of
arbitrary prompts composed by a model.

## Gate interpretation

| Outcome | Interpretation |
|---|---|
| All eight reference-prompt-entry rows reach 8/10, full task reaches 16/20, and matched continuations establish supervisory relevance | Policy backend is qualified and may be locked for model comparison |
| A completed valid gate falls below threshold | Policy backend fails feasibility; preserve evidence and proceed to the predefined fallback |
| Fewer than the required valid trials exist | Pending/incomplete; neither pass nor fail |
| Only source, mock, or CPU interface checks exist | Runtime unverified; neither pass nor fail |

If neither GR00T nor π0.5 passes by the reporting deadline, publish the
feasibility evidence and do not publish LLM orchestration scores as robot-policy
benchmark results.

## Evidence package

For each candidate, retain the environment locks/images, source and checkpoint
revisions, hardware identity, seed list, trial manifests, observations, learned
policy requests and returned chunks, action attempts, evaluator-only traces,
videos, and gate calculation. Report missing records as missing rather than
estimating outcomes.

## First live development pass: September 27, 2026

The development run (local artifacts: `runs/prime_20260927_1454/`, excluded
from this Git repository) used the pinned official
GR00T N1.5 checkpoint on an RTX 6000 Ada. The checkpoint digest matched the
manifest, the worker exposed its expected policy identity, and RoboCasa's live
simulator smoke test passed with three RGB cameras, proprioception, and the
physical task evaluator. GR00T model loading initially failed because the
pinned EAGLE2 vision module required `flash_attn`; installing the official
Dao-AILab 2.7.4.post1 wheel matched to Torch 2.5/CUDA 12/Python 3.11/ABI=false
repaired it. That exact wheel is now in `configs/requirements-groot.txt`, and
the resolved package snapshot is retained with the run.

| Development episode | Seed | Terminal outcome | Steps | Wall time | Evidence |
|---|---:|---|---:|---:|---|
| Ordinary whole-task GR00T | 0 | Step budget exhausted; no physical success | 4,350 | 382.2 s | Cereal and bowl both eventually contacted the counter; cabinet was not closed at the end. |
| Predicate-based diagnostic supervisor | 100 | Step budget exhausted; no physical success | 4,350 | 456.6 s | Only the `open_cabinet` prompt ran. The upstream `cabinet_open` predicate never became true, so the supervisor never attempted a transfer or close prompt. |
| Opus 5.5 through the public harness | 1 | False completion | 3,640 | 763.7 s | Both objects contacted the counter, but the cabinet was neither fully open nor closed when Opus declared completion. This is an unqualified development run. |

The Opus run made 47 model calls, of which eight were malformed and charged
without physics advancement. It submitted 23 policy prompts, changed prompt 17
times, restarted the same prompt five times, and discarded 200 queued actions.
All 47 API-visible requests and responses are retained, including 45 responses
with thinking-summary blocks. The API does not expose raw private reasoning.
Each episode has three 20 fps MP4s and complete per-control-step PNG and timing
records; the local `runs/prime_20260927_1454/verification.json`
checks frame counts, video metadata, trace counts, and hashes. The team compute
charge was $0.93, and the GPU pod was terminated after records were copied.

These three seeds are not paired, so outcome differences cannot establish that
orchestration improved performance. The diagnostic supervisor's dependency on
`cabinet_open` is not a reliable handoff rule in the observed states: two other
runs transferred objects without that predicate becoming true. Before another
counted trial, inspect the natural cabinet states and predeclare a supervisor
rule that can attempt transfer after a finite opening prefix, then test closing
from naturally reached both-on-counter states. No reference-prompt-entry gate,
20-episode supervisor gate, or matched-continuation gate is complete. GR00T is
still **unqualified**, and π0.5 has not been tested.

The live worker was started manually without first sourcing `scripts/project_env.sh`,
so Transformers placed a transient dynamic-module cache under the pod user's
home directory. The checkpoint and project outputs stayed under the remote
project root, and that temporary pod was deleted. A clean reproduction must
source the project environment before starting the worker, as the GPU runbook
specifies; that clean rebuild has not yet been verified.
