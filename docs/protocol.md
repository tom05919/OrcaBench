# Evaluation protocol

## Study question and controlled variables

The benchmark compares multiple LLM orchestrators as supervisors of the same
fixed learned policy. A model may write any natural-language instruction for the
policy, decide how many control steps elapse before it observes again, redirect
or restart the policy, and declare completion. It never emits robot controls
directly.

Every reported model comparison must hold these items fixed:

- the source revisions and checkpoint revision in
  [`configs/sources.lock.json`](../configs/sources.lock.json);
- the selected learned-policy backend and checkpoint;
- the reference qualification prompts and their evidence, policy preprocessing,
  cameras, proprioception, controller, task split, seeds, and initial states;
- the 4,350-control-step episode horizon, 100-model-call limit, and 1–100-step
  observation interval, with at most 4,096 output tokens per model call;
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

## Reference qualification prompts

The benchmark publishes performance cards for four exact learned-policy prompts:

| Reference ID | Prompt |
|---|---|
| `open_cabinet` | Open the cabinet. |
| `transfer_cereal` | Pick the cereal box from the cabinet and place it on the counter. |
| `transfer_bowl` | Pick the bowl from the cabinet and place it on the counter. |
| `close_cabinet` | Close the cabinet. |

These prompts are diagnostic probes, not the model's action vocabulary or an
allowlist. During model evaluation, the orchestrator may send any nonblank
natural-language prompt of at most 512 characters to the same checkpoint.
Accepted text is forwarded verbatim, without trimming or other normalization;
validation only rejects blank or overlength strings. A card supports only its
exact prompt under its tested entry conditions; it does not establish that
paraphrases, composed instructions, or prompts changed during execution work.
Those uses are allowed by the interface but remain unproven until retained GPU
rollouts provide evidence.

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
Model observation schema version 2 includes the current goal, public
reference-prompt catalog, active policy instruction, step and call budgets,
decision history (including rejected outputs), and the last schema error. Each reference prompt
includes the predeployment screening card published from the qualified policy:
tested entry conditions, counts, success rates, Wilson intervals, step-duration
summaries, and observed limitations. Private trace paths and evaluator state are
removed before publication.
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
| `{"op":"run_policy","steps":N,"prompt":"..."}` | Requires a nonblank prompt of at most 512 characters and `N` from 1–100 when no instruction is active. At any later boundary, the supplied prompt is preserved verbatim, replaces the active instruction, discards every pending action, invokes the policy reset hook, and advances `N` control steps. These effects apply even when the supplied text equals the active prompt. |
| `{"op":"run_policy","steps":N}` | Requires an active instruction. Preserves that instruction and its pending action queue, and advances `N` control steps. |
| `{"op":"complete"}` | Advances no physics, evaluates the current state, and terminates the episode. |

There is no separate interrupt operation. Physics is synchronous and already
paused for the entire LLM inference at every decision boundary, so the model can
inspect the observation and either continue the queue or replace the prompt in
its next advancing call. Model latency changes wall time, not simulated dynamics.
The pinned policy backends have no recurrent instruction state; their reset hook
does not reset the physical world or the policy's episode random stream.
A malformed or state-invalid response consumes one of the 100 model calls,
produces a visible schema error on the next call, and does not advance physics.
Requests that exceed the remaining control-step budget are invalid in the same
way.

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
policy call counts, chosen intervals, prompt submissions, prompt changes,
same-prompt restarts, discarded queued actions, model
and policy time, and infrastructure errors. Preserve every attempted episode.
Infrastructure-incomplete attempts remain visible but are not silently converted
into model failures or replaced without provenance.

## Diagnostic oracle

A hand-authored supervisor may read simulator truth only for feasibility and
system diagnosis. Qualification uses the four declared reference prompts through
the same `run_policy` semantics, but the supervisor may not apply scripted robot
actions or alter objects. Existing qualification records call these probes
`skill` and their conditions `skill_conditions`; those evidence-schema names do
not restrict the model API. Supervisor requests and results are stored separately
and never included in model score tables. Oracle access does not change what a
model adapter can observe.

## Reproduction record

Each run must identify source and checkpoint revisions, environment and worker
images or lockfiles, policy backend, model/provider version, adapter settings,
prompt digest, seed list, budgets, and code revision. Append-only records must
retain model replies, accepted and rejected decisions, sensor frames, attempted
and completed actions, policy calls, evaluator-only states/events, final result,
and infrastructure errors. All three camera views are retained as PNG frames
at every control step, including step zero, and encoded as MP4 replays at 20 fps.
Step timing records include wall time, simulation time, policy wait, recording,
and evaluation time. For Anthropic model calls, the complete API-visible request,
response, usage, thinking summaries, and errors are retained without credential
headers. Raw hidden model reasoning is unavailable. Evaluator directories and
replay frames are not model inputs.

Primary source anchors:

- [RoboCasa `CerealAndBowl` at the pinned revision](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/snack_preparation/cereal_and_bowl.py)
- [RoboCasa dependency manifest at the pinned revision](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/setup.py)
- [GR00T dependency manifest at the pinned revision](https://github.com/robocasa-benchmark/Isaac-GR00T/blob/9d7d7a9eb7ad30bd8ce30448d9ab53a918b45b10/pyproject.toml)
- [GR00T evaluation entry point at the pinned revision](https://github.com/robocasa-benchmark/Isaac-GR00T/blob/9d7d7a9eb7ad30bd8ce30448d9ab53a918b45b10/scripts/run_eval.py)
