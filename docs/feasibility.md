# Learned-policy feasibility plan

## Current status

Feasibility is **pending**. The Prime Intellect GPU worker has not been
provisioned, so no actual learned-policy rollout, skill success rate, or full-task
success rate can be claimed.

Source inspection has established the following facts only:

| Item | Status | Evidence |
|---|---|---|
| RoboCasa task predicate and horizon | Source-verified | Pinned `CerealAndBowl` source and dataset registry: cereal/counter contact, bowl/counter contact, closed cabinet; horizon 4,350 |
| Checkpoint locations | Revision-pinned | `configs/sources.lock.json` pins the official checkpoint repository and GR00T/π0.5 subdirectories |
| Coordinator/worker compatibility | Conflict identified, design selected | Pinned RoboCasa requires MuJoCo 3.3.1, NumPy 2.2.5, and Tianshou 0.4.10; pinned GR00T requires Tianshou 0.5.1 |
| Runner operation semantics | Locally source-inspected | Queue discard and pause/step behavior are implemented in `src/robot_benchmark/runner.py` |
| Learned skill execution | Untested | Requires the GPU worker and complete runtime assets |
| Qualification gates | Not run | Missing or incomplete trials are neither passes nor failures |

Static inspection and mock policies cannot qualify a learned policy.

## Runtime isolation

Use two separately locked environments connected by an HTTP policy interface:

1. The coordinator environment owns MuJoCo, robosuite, RoboCasa, episode state,
   observations, action stepping, recording, and the evaluator. It uses the
   RoboCasa-compatible dependency set, including Tianshou 0.4.10.
2. The GPU worker environment owns the selected learned policy and checkpoint.
   The GR00T candidate uses its pinned dependency set, including Tianshou 0.5.1.
3. The coordinator sends only policy observations and one of the four fixed
   instruction strings. The worker returns learned action chunks in the pinned
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

### 2. Per-skill-entry gate

Run ten valid diagnostic trials for each declared skill-entry condition. Every
skill has a nominal condition and a naturally encountered intermediate condition,
for eight required rows. Initial states must come from ordinary task resets and
natural prefixes executed by the learned skills; do not teleport objects, inject
control noise, alter contacts, or script manipulation. The hand-authored
diagnostic supervisor may read truth to identify whether the required starting
condition and tested outcome were achieved and to choose when to stop.

| Skill | Entry condition | Condition checked after learned execution | Gate |
|---|---|---|---|
| `open_cabinet` | Nominal ordinary reset with the task cabinet closed | The task cabinet is open | at least 8 of 10 valid trials |
| `open_cabinet` | Naturally reached intermediate state with the cabinet closed after prior learned execution | The task cabinet is open | at least 8 of 10 valid trials |
| `transfer_cereal` | Nominal learned `open_cabinet` prefix; cereal remains off counter | The cereal contacts the task counter | at least 8 of 10 valid trials |
| `transfer_cereal` | Naturally interrupted or failed learned state in which transfer remains possible | The cereal contacts the task counter | at least 8 of 10 valid trials |
| `transfer_bowl` | Nominal learned `open_cabinet` prefix; bowl remains off counter | The bowl contacts the task counter | at least 8 of 10 valid trials |
| `transfer_bowl` | Naturally interrupted or failed learned state in which transfer remains possible | The bowl contacts the task counter | at least 8 of 10 valid trials |
| `close_cabinet` | Nominal learned prefix with the task cabinet open | The task cabinet is closed | at least 8 of 10 valid trials |
| `close_cabinet` | Naturally reached intermediate state with cabinet open after prior learned execution | The task cabinet is closed | at least 8 of 10 valid trials |

Every row must independently reach 8/10. An aggregate cannot hide a weak
skill. A target-skill trial begins only after its required start is observed; a
prefix failure is retained as evidence about the prefix skill and does not become
a target-skill attempt. A valid trial that runs its declared budget without
meeting its condition is a failure. An unrun trial or an attempt cut short by
infrastructure is incomplete and is recorded without entering the numerator or
denominator until the trial set is completed.

### 3. Full-task diagnostic gate

Run twenty valid `CerealAndBowl` episodes with the diagnostic supervisor and the
same four learned skills. The first full-task attempts reproduce the ordinary
sequence—open cabinet, transfer cereal, transfer bowl, close cabinet—without
disturbance. Subsequent attempts may exercise only failures and handoffs that
arise naturally from learned execution, using retry, switch, interrupt, and
variable observation intervals. Do not inject failures or perturb the scene.

Passing requires physical task success in at least 16 of 20 valid episodes under
the source predicate. Preserve all attempts, including unsuccessful and
infrastructure-incomplete episodes. The diagnostic supervisor's privileged view
and results remain separate from model evaluation.

### 4. Supervisory relevance gate

From naturally encountered recorded states, identify matched continuation cases
where at least two allowed supervisory choices can be evaluated without altering
the scene: for example continue versus interrupt-and-retry, or continue versus
switch. Preserve the common prefix and both continuation traces. Record the
state-selection rule before inspecting continuation outcomes. Qualification
remains `pending_relevance` unless the retained cases show that at least one
allowed supervisory decision changes the physical outcome or resource use in a
way the benchmark can score. Report every investigated case, including null
results. Do not manufacture a failure state.

## Gate interpretation

| Outcome | Interpretation |
|---|---|
| All eight skill-entry rows reach 8/10, full task reaches 16/20, and matched continuations establish supervisory relevance | Policy backend is qualified and may be locked for model comparison |
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
