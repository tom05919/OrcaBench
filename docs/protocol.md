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
- the 4,350-control-step episode horizon, 100-model-call limit, and 1–400-step
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
Model observation schema version 4 includes the current goal, current camera
frames, current proprioception, up to four keyframes per camera sampled evenly
from strictly inside the interval just executed (each labeled by step and carrying
the proprioception recorded at that step; empty on the first call and after a
rejected decision), public reference-prompt catalog, active policy instruction, step and call budgets,
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
| `{"op":"run_policy","steps":N,"prompt":"..."}` | Requires a nonblank prompt of at most 512 characters and `N` from 1–400 when no instruction is active. At any later boundary, the supplied prompt is preserved verbatim, replaces the active instruction, discards every pending action, invokes the policy reset hook, and advances `N` control steps. These effects apply even when the supplied text equals the active prompt. |
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

### Reply format

The model's reply must be one JSON object in the schema above. Anthropic
requests enforce the shape with `output_config.format` (`op` of `run_policy` or
`complete`, optional `prompt`, optional integer `steps`, no other keys); the schema
cannot express per-operation fields or ranges, so the runner still validates
those. Tolerance is deliberately narrow. Text that is not itself a JSON value is
accepted only when the model finished normally (`end_turn`) and the text contains
exactly one distinct object whose `op` is a string; the same decision repeated is
still one decision. Two different candidate objects, a truncated (`max_tokens`)
or refused reply, or no candidate leaves the reply rejected, charged, and
reported on the next call as an ordinary schema error. The retained record keeps
the raw text and a `parse` label (`strict`, `extracted`, or `unparsed`) for every
reply, so recovered replies can be audited or excluded. The same rule applies to
every Anthropic-provider model; a `json_http` server must return the parsed
decision itself.

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

## Intervention-judgement benchmark

Status: implemented and unit-tested locally with mocks only. Nothing in this
section has been run on a GPU or against the real simulator yet. The design is in
[`docs/superpowers/specs/2026-10-01-intervention-judgement-design.md`](superpowers/specs/2026-10-01-intervention-judgement-design.md).

The benchmark measures one supervision error: an LLM intervening when the policy
did not need help, or failing to intervene when it did. The interface,
observation, declaration rule and budgets above are unchanged. The differences
from the CerealAndBowl pilot are listed here.

**Tasks.** The candidate pool is 16 RoboCasa365 tasks in `configs/tasks/` (see
[`task_catalog.md`](task_catalog.md)). The goal is the task's native instruction,
read verbatim from the environment. Success is the official `_check_success` at
the agent's `complete` declaration. Each config publishes one card,
`native_instruction`, whose prompt is the template `"{goal}"`; each observation
shows the episode's goal text in its place. After screening, `publish-cards` writes
the plain policy's set-A success rate on the native instruction, pooled over all
screened scene seeds (trials, successes, Wilson 95% interval), and sets the config
`status` to `screened`. This is a per-task rate, not a per-seed estimate. Unscreened
tasks stay untested/null. Subtask step prompts stay privileged.

**Seeds.** An episode is `(task, scene_seed, policy_seed)`. The scene seed fixes
the layout and initial state, and the policy seed fixes the policy's sampling
noise. Screening uses policy seeds 0–4 (set A) and reference scoring uses 5–9
(set B). The two sets are disjoint and are set in `configs/splits.json`.

**Seed groups.** For each task and scene seed, the plain policy runs with the
native instruction on the five set-A policy seeds (`diagnostic_reference`):

| Group | Rule |
|---|---|
| `leave_alone` | at least 4 of 5 reference runs succeed |
| `needs_help` | at most 1 of 5 succeed, and `diagnostic_retry` or `diagnostic_sequencer` succeeds in at least 2 of 5 on the same scene; a retry success counts only if it re-prompted (`prompt_submissions >= 2`) |
| `medium` | anything else; reported separately |
| `pending` | fewer than 5 usable reference runs |

A task qualifies with at least 2 seeds in each of the first two groups, and the
release keeps up to 4 of each. If more than 10 tasks qualify, the release keeps the
top 10, ranked by `min(selected leave_alone, selected needs_help)` descending, then
total selected seeds descending, then task name (predeclared). Rescue diagnostics may
run only on low-success scenes (`screen --scenes-from groups.json`): those with a full
set-A reference and at most 1 success. Infrastructure errors are kept on disk but never
counted. Two usable runs for the same (task, scene seed, policy seed, kind) are
rejected.

**Conditions.** All conditions run on the release's selected scene seeds with the
set-B policy seeds, so each system episode pairs with a reference episode that
has the same scene and policy noise.

| Kind | Role | Privileged |
|---|---|---|
| `diagnostic_reference` | plain policy, native instruction, checker polled every 100 steps, stops on success | yes; reference only |
| `diagnostic_retry`, `diagnostic_sequencer` | rescue evidence for `needs_help` labels; retry checks success every 100 steps and re-issues the instruction after 300 steps without success | yes; never scored |
| `baseline_always_defer` | native instruction once, maximum intervals, `complete` at the end of the budget | no |
| `baseline_reissue` | same instruction every 100 steps, `complete` at the end of the budget | no |
| `llm` | model under test with a frozen benchmark release | no |

LLM and baseline runs use one policy seed per scene by default, the first
`reference_policy_seed`, which matches the planned cost. More set-B seeds are allowed.
`llm_development` runs are never scored; the scorecard counts them as
`excluded_development`.

**Scoring.** The scorecard (`robot-benchmark scorecard`) keeps only episodes whose
contract hash equals the release's. It scores each baseline and model
separately and reports, per group:

- success rate with a Wilson 95% interval;
- **harm** on `leave_alone`: reference success rate minus system success rate;
- **rescue** on `needs_help`: system success rate minus reference success rate;
- false-completion and no-declaration counts and rates, the intervention profile
  (including an interval histogram), and cost;
- for `baseline_always_defer`, `reference_agreement`: how often its success equals
  the paired reference episode's, as a GPU-nondeterminism check.

Harm and rescue use only paired (task, scene seed) clusters, which need at least one
usable system episode and one usable set-B reference episode. Unpaired clusters are
counted as `unpaired_clusters`. Both carry seed-clustered percentile bootstrap
intervals and are never combined into one number. Failed system episodes get an offline attribution label
from private logs: false completion, missed completion, unnecessary intervention,
missed intervention, or executor/other. This label is diagnostic and not part of
the score. Results are conditional on GR00T N1.5 and the selected tasks.

**Contract.** Every command computes one contract payload covering the whole task
pool, splits, policy identity (including the GPU name), source revisions, system
prompt and implementation hashes. Any task subset therefore yields the same hash.
Screening runs under the pre-publication hash: `publish-cards` writes screened
performance into the task configs and so changes the hash on purpose. From the
set-B reference runs onward, freeze, baselines and model runs share one hash. The analysis-only modules `scorecard.py` and
`screening.py` are not in the hash; `freeze-benchmark` records their SHA-256 under
`analysis_sha256`. Supervisor and baseline parameters are module defaults in hashed
modules. Set-B reference, baseline and LLM runs must use the same GPU type, code,
configs and splits as the freeze. Each command writes its payload to
`contract-<hash>.json`. The video recording interval is not part of the hash but is
recorded in every manifest.

**Release.** `freeze-benchmark --reference-root` refuses to freeze unless every
selected (task, scene seed) has a usable `diagnostic_reference` episode under the
frozen hash for each reference policy seed. `run --release` and
`baseline --release` accept only the release's tasks, selected scene seeds and
reference policy seeds.

## Reproduction record

Each run must identify source and checkpoint revisions, environment and worker
images or lockfiles, policy backend, model/provider version, adapter settings,
prompt digest, seed list, budgets, and code revision. Append-only records must
retain model replies, accepted and rejected decisions, sensor frames, attempted
and completed actions, policy calls, evaluator-only states/events, final result,
and infrastructure errors. All three camera views are retained as PNG frames
every `video_record_interval` control steps (default 1; benchmark GPU runs use 10),
including step zero, and encoded as real-time MP4 replays at 20/interval fps.
Step timing records include wall time, simulation time, policy wait, recording,
and evaluation time. Every `result.json` reports both clocks: `simulated_seconds`
is the physics clock (control steps / 20 Hz) and `wall_seconds` is real elapsed
time from reset to the end of the episode, including model API latency
(`model_seconds`, the time spent waiting for the agent), policy inference
(`policy_seconds`), rendering and video recording, and evaluation. Only
`model_seconds` and `simulated_seconds` are attributable to the agent and the
episode; `wall_seconds` also depends on the GPU, the recording interval and API
latency, so compare it only across runs on the same setup. The scorecard reports
total, mean, and success-only mean for each clock per system and group; a field
missing from a result stays unknown rather than counting as zero. For Anthropic model calls, the complete API-visible request,
response, usage, thinking summaries, and errors are retained without credential
headers. Raw hidden model reasoning is unavailable. Evaluator directories and
replay frames are not model inputs.

Primary source anchors:

- [RoboCasa `CerealAndBowl` at the pinned revision](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/snack_preparation/cereal_and_bowl.py)
- [RoboCasa dependency manifest at the pinned revision](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/setup.py)
- [GR00T dependency manifest at the pinned revision](https://github.com/robocasa-benchmark/Isaac-GR00T/blob/9d7d7a9eb7ad30bd8ce30448d9ab53a918b45b10/pyproject.toml)
- [GR00T evaluation entry point at the pinned revision](https://github.com/robocasa-benchmark/Isaac-GR00T/blob/9d7d7a9eb7ad30bd8ce30448d9ab53a918b45b10/scripts/run_eval.py)
