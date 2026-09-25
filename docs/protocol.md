# Evaluation protocol

## Study question and controlled variables

The benchmark compares multiple LLM orchestrators as supervisors of the same
fixed learned-policy library. A model may decide which learned skill runs, how
many control steps elapse before it observes again, whether to interrupt or
retry, and when to declare completion. It never emits robot controls directly.

Every reported model comparison must hold these items fixed:

- the source revisions and checkpoint revision in
  [`configs/sources.lock.json`](../configs/sources.lock.json);
- the selected learned-policy backend and checkpoint;
- the four skill instructions, policy preprocessing, cameras, proprioception,
  controller, task split, seeds, and initial states;
- the 4,350-control-step episode horizon, 100-model-call limit, and 1–100-step
  observation interval, with at most 1,024 output tokens per model call;
- the model-facing prompt and operation schema, except for provider-required
  serialization;
- the physical evaluator and result aggregation.

No training, fine-tuning, scripted manipulation, artificial disturbance, or
model-specific recovery aid is allowed. A policy backend is selected during
feasibility qualification and then remains identical across model runs. Results
from different policy backends must not share a comparison table.

## Environment and task

The environment is MuJoCo through robosuite and RoboCasa at the pinned revisions.
The task is `CerealAndBowl`. RoboCasa registers an upstream horizon of 4,350
control steps.

The evaluator's physical predicate is exactly:

```text
contact(cereal, counter)
AND contact(bowl, counter)
AND cabinet.is_closed
```

The model-facing goal must describe those predicates directly:

> Move the cereal box and the bowl from the cabinet onto the adjacent counter,
> and leave the cabinet closed. Declare completion when both objects are on the
> counter and the cabinet is closed.

RoboCasa's upstream language mentions placing the objects “next to the milk,”
but its `_check_success` implementation does not score that relation. The
benchmark therefore omits it from the goal. The evaluator also does not require
the gripper to release either object or require contact to remain stable for a
minimum time. These are limitations of the source task, not extra benchmark
conditions.

## Fixed learned skills

The library exposes only these four learned-policy instructions:

| Skill ID | Fixed instruction |
|---|---|
| `open_cabinet` | Open the cabinet. |
| `transfer_cereal` | Pick the cereal box from the cabinet and place it on the counter. |
| `transfer_bowl` | Pick the bowl from the cabinet and place it on the counter. |
| `close_cabinet` | Close the cabinet. |

The first policy candidate is the official
[`robocasa/robocasa365_checkpoints`](https://huggingface.co/robocasa/robocasa365_checkpoints)
revision `c484448aba1a9b60a04c9b0ca117241518ea69f3`, subdirectory
`gr00t_n1-5/multitask_learning/checkpoint-120000`. The π0.5 subdirectory
`pi05_pretrain_human300/multitask_learning/75000` is the predefined fallback.
The fallback may be selected only through the feasibility procedure; it is not
chosen per episode or per model.

Action chunks are produced by the learned policy independently of the LLM's
requested observation interval. The runner consumes enough queued policy
actions to advance the requested number of control steps and requests another
chunk only when needed. It does not stretch, shorten, interpolate, or replace
learned actions.

## Model-visible information

The only environment sensing available to a model is RGB plus proprioception.
The model receives the current goal, public skill catalog, active and last skill,
step and call budgets, accepted-decision history, and the last schema error.
Each public skill includes the predeployment screening card published from the
qualified policy: tested entry conditions, counts, success rates, Wilson
intervals, step-duration summaries, and observed limitations. Private trace
paths and evaluator state are removed before publication.
The sensor portion contains RGB PNGs from:

- `video.robot0_agentview_left`;
- `video.robot0_agentview_right`;
- `video.robot0_eye_in_hand`.

Proprioception contains relative end-effector position and rotation, gripper
joint position, and base position and rotation. Reward, task-success flags,
object coordinates, simulator predicates, subtask annotations, evaluator
artifacts, and corrective advice must never enter a model request.

## Decision semantics

Each model call returns exactly one operation:

| Operation | Valid state and effect |
|---|---|
| `start(skill, steps)` | Requires no active skill. Starts a named skill and advances 1–100 control steps. |
| `continue(steps)` | Requires an active skill. Keeps its pending policy queue and advances 1–100 steps. |
| `interrupt` | Requires an active skill. Discards its pending queue, resets policy skill state, and advances no physics. |
| `switch(skill, steps)` | Requires an active skill and a different target. Discards the queue, resets policy skill state, and advances 1–100 steps with the target. |
| `retry(steps)` | Requires a previously selected skill. Discards the queue, resets policy skill state, and advances 1–100 steps using that skill again. |
| `complete` | Advances no physics, evaluates the current state, and terminates the episode. |

A new `start` also begins with clean policy skill state. Physics is synchronous
and pauses for the entire LLM inference. Thus model latency changes wall time,
not simulated dynamics. A malformed or state-invalid response consumes one of
the 100 model calls, produces a visible schema error on the next call, and does
not advance physics. Requests that exceed the remaining control-step budget are
invalid in the same way.

## Termination and primary score

The primary per-episode score is binary success. Success requires the model to
issue `complete` while the physical predicate is true, before either the
4,350-step or 100-call budget is exhausted. Physical success at an earlier time
does not count if it has regressed before declaration. Issuing `complete` while
the predicate is false produces terminal `false_completion`; the model cannot
correct it afterward. Reaching either budget without a correct declaration is a
failure.

Report, at minimum, the following alongside success rate: final and ever-seen
physical success, false-completion count, budget-exhaustion counts, model and
policy call counts, chosen intervals, switches, retries, interrupts, model and
policy time, and infrastructure errors. Preserve every attempted episode.
Infrastructure-incomplete attempts remain visible but are not silently converted
into model failures or replaced without provenance.

## Diagnostic oracle

A hand-authored supervisor may read simulator truth only for feasibility and
system diagnosis. It may choose among the same four learned skills and the same
operations, but may not apply scripted robot actions or alter objects. Its
requests and results are stored separately and never included in model score
tables. Oracle access does not change what a model adapter can observe.

## Reproduction record

Each run must identify source and checkpoint revisions, environment and worker
images or lockfiles, policy backend, model/provider version, adapter settings,
prompt digest, seed list, budgets, and code revision. Append-only records must
retain model replies, accepted and rejected decisions, sensor frames, attempted
and completed actions, policy calls, evaluator-only states/events, final result,
and infrastructure errors. A left-camera replay frame is retained every two
control steps, including step zero, so representative episodes can be rendered
and inspected. Evaluator directories and replay frames are not model inputs.

Primary source anchors:

- [RoboCasa `CerealAndBowl` at the pinned revision](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/snack_preparation/cereal_and_bowl.py)
- [RoboCasa dependency manifest at the pinned revision](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/setup.py)
- [GR00T dependency manifest at the pinned revision](https://github.com/robocasa-benchmark/Isaac-GR00T/blob/9d7d7a9eb7ad30bd8ce30448d9ab53a918b45b10/pyproject.toml)
- [GR00T evaluation entry point at the pinned revision](https://github.com/robocasa-benchmark/Isaac-GR00T/blob/9d7d7a9eb7ad30bd8ce30448d9ab53a918b45b10/scripts/run_eval.py)
