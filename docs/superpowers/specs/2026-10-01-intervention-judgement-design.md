# Intervention-judgement benchmark: design

Status: design approved in conversation on 2026-10-01; not yet implemented
except where noted. Deadline for the course deliverable: 2026-10-16.

## 1. Purpose

The benchmark measures one failure mode of an LLM supervising a frozen
language-conditioned robot policy: **intervening when the policy did not need
help, or failing to intervene when it did.** Every decision in supervision
reduces to this choice: let the policy continue, or give it a new instruction.
Planning, progress monitoring, recovery, and completion judgement all feed into
it, so the measurement covers the core of supervision, not a niche skill.

### Why existing benchmarks miss it

LLM-over-VLA orchestration evaluations (VoLo/RoboVoLo, What Matters in
Orchestrating Robot Policies) choose tasks where the plain VLA fails, so
intervention is always rewarded and unnecessary intervention cannot appear as a
cost. Evidence that it is a real failure mode:

- Embody (Anthropic, July 2026): every LLM supervising MolmoAct on familiar
  LIBERO tasks did worse than MolmoAct alone; the strongest model over-overrode.
  Its supervision is action-level, with one executor, and it is not a released
  benchmark.
- VoLo: completion-monitoring errors dominate and grow with model capability.
- SEES: LLM decomposition of seen RoboCasa365 composites underperformed the base
  policy.
- Digital-agent precedents: The Intervention Paradox (2602.03338) and
  Calibration Is Not Control (2606.21399).

The claim is bounded: no reviewed, released benchmark measures intervention
judgement for an LLM supervising a learned robot policy through language. It is
a search finding, not proof of uniqueness.

## 2. System under test and fixed components

- **System under test:** an LLM supervisor using the existing interface:
  `run_policy(prompt?, steps)` and `complete`. Intervention means supplying a
  prompt (including an identical one, which still discards queued actions and
  resets the policy). Omitting the prompt defers. `steps` is when to observe
  next. The LLM never writes code or controls the robot directly.
- **Executor:** official RoboCasa365 GR00T N1.5 multitask checkpoint pinned in
  `configs/sources.lock.json`. pi0.5 is an optional second track only if the
  primary track finishes early; tracks are never mixed.
- **Simulator:** pinned RoboCasa/robosuite/MuJoCo, as today.
- **Systems for the required results:** Opus 5.5 (`claude-opus-5-5`) and
  Sonnet 5.5 (`claude-sonnet-5-5`) through the existing Anthropic adapter, same
  settings. A cross-vendor model needs a new adapter and is optional.

### Observation (implemented 2026-10-01)

Model observation schema 3: goal, three current camera frames, proprioception,
up to four keyframes per camera sampled evenly from strictly inside the interval
just executed, public performance cards, active instruction, budgets, decision
history, last schema error. Maximum interval 400 control steps (20 s at 20 Hz);
100 model calls per episode. Never exposed: simulator state, object
coordinates, reward, success, predicates, subtask labels, seed group, or
reference outcomes.

## 3. Tasks

- **Count:** 10 tasks for the first release. Tasks are defined in per-task config
  files so more can be added later without code changes.
- **Source:** RoboCasa365 atomic and composite-seen tasks in the pinned source.
  Composite-unseen tasks are excluded: the plain VLA is near zero on them, so
  they have no leave-alone seeds.
- **Selection criteria, applied in order:**
  1. official `_check_success` exists and is read without modification;
  2. episode horizon short enough to screen cheaply (prefer at most about 1,500
     steps);
  3. for composites, subgoal predicates can be written for the diagnostic
     sequencer (section 4);
  4. screening yields both leave-alone and needs-help seeds (section 4).
- **Goal text:** the task's native RoboCasa language instruction, verbatim. If the
  native text names a relation the checker does not enforce, record it in
  `docs/decisions.md`; do not edit the checker.
- **Budget:** the upstream task horizon (`get_task_horizon`), as today.
- **Performance cards:** per-task, not per-seed: the plain VLA's success rate on
  the native instruction across all screened seeds, and, where measured, step
  prompt rates. Unknown rates are `null`/untested, never zero.

## 4. Seeds: scene versus policy noise

The policy worker currently seeds its sampling noise with the episode seed
(`policy_worker.py` `reset`), so repeated runs on one seed are near-identical.
The benchmark therefore separates:

- **scene seed:** layout, objects, and initial state (`env.reset`);
- **policy seed:** the VLA's sampling stream (`policy.reset_episode`).

An episode is identified by `(task, scene_seed, policy_seed)`. This changes the
evaluation contract and must be recorded.

### Screening and seed groups

Per task, screen 10 scene seeds from the evaluation range. For each, run the
plain VLA on the native instruction with 5 policy seeds (screening set A) using
the privileged-stop diagnostic (section 5).

- **Leave-alone:** at least 4 of 5 succeed.
- **Needs-help:** at most 1 of 5 succeed, and a privileged diagnostic supervisor
  succeeds in at least 2 of 5 runs on the same scene seed. That supervisor is:
  - *privileged retry* (generic, any task): re-issues the native instruction
    when the official checker has not become true within a fixed predeclared
    step count;
  - *privileged sequencer* (composites only): issues predeclared step prompts
    driven by per-task subgoal predicates.
  This is evidence that language-level intervention can rescue the seed. It is
  diagnostic only and never mixed with model scores.
- **Medium:** everything else. Retained and reported separately.

Keep a task only if it has at least 2 leave-alone and 2 needs-help scene seeds.
The evaluation set takes up to 4 of each per task (at most 80 scene seeds);
medium seeds are evaluated only if budget remains, and reported separately.
If fewer than 10 tasks qualify, screen more seeds or candidate tasks before
reducing the count. Report the final count.

### Avoiding selection bias

Seeds chosen because they scored 5/5 or 0/5 will look less extreme on a rerun.
Scoring therefore uses a fresh **reference set B**: 5 new policy seeds per
selected scene seed, disjoint from set A. Group labels come from A; reference
rates come from B. Evaluation episodes for every system reuse the policy seeds of
set B, so each system episode is paired with a reference episode sharing the
same scene and policy noise until the first divergence.

## 5. Conditions

| Condition | Role | Privileged? |
|---|---|---|
| Plain VLA, privileged stop | Reference: ideal deference with perfect completion detection. Native instruction, checker polled every 100 steps, stops on success. | Yes, diagnostic only |
| Always defer | Baseline: native instruction once, maximum intervals, `complete` when budget is nearly exhausted | No |
| Re-issue every 100 steps | Baseline: interruption without judgement; same prompt every 100 steps, `complete` at budget end | No |
| Opus 5.5 | System under test | No |
| Sonnet 5.5 | System under test | No |

Both baselines are public strategies and appear on the scorecard. An LLM that
cannot beat both is not showing judgement.

## 6. Scoring

Every episode is scored by the official `_check_success` at the agent's
`complete` declaration. A physically complete state without declaration is a
failure; a false declaration is a failure. This primary rule is unchanged.

Per system, per seed group, with Wilson 95% intervals:

- **success rate**;
- **harm** (leave-alone seeds): reference success rate (set B) minus system
  success rate, with a seed-clustered bootstrap interval;
- **rescue** (needs-help seeds): system success rate minus reference success rate,
  with a seed-clustered bootstrap interval;
- **false-completion rate** and **no-declaration rate**;
- **intervention profile**: prompts submitted, prompt changes, identical-prompt
  restarts, discarded actions, chosen intervals;
- **cost**: model calls, input/output tokens, physical steps, wall time.

Harm and rescue are reported as a pair and never combined with arbitrary weights.
Every attempted episode is retained, including infrastructure errors, which are
reported separately and not counted as agent failures.

**Offline failure attribution** (diagnostic, not part of the score): using private
predicate logs, label each failed system episode with the first decisive error:
unnecessary intervention while the VLA was progressing, missed intervention while
it was stalled, false or missing completion, or executor failure after a
reasonable instruction. Labelling rules are fixed before evaluation runs.

## 7. Implementation scope

Local, testable without a GPU:

1. Generic task scoring: `RoboCasaEnvironment.evaluate()` returns the official
   `_check_success` for any task; per-task subgoal predicates live in a separate
   diagnostic module used only by the sequencer and failure attribution.
2. Per-task config files (schema 3) with native goal, horizon, cards; replace
   the CerealAndBowl-only validation in `cli.task_parts` with a generic validator.
3. Scene/policy seed separation through `Runner.run`, the CLI, records, and the
   manifest.
4. The two public baselines, the privileged-retry diagnostic, and the per-task
   privileged sequencer.
5. Screening command: grid of tasks × scene seeds × policy seeds with the
   reference supervisor, then seed-group labelling.
6. Release freeze: tasks, scene seeds, groups, set-B policy seeds, reference
   outcomes, cards, model identifiers.
7. Scorecard: harm, rescue, rates, intervals, cost, from the run directory.
8. Unit tests for each; `python -m unittest discover -s tests -v` passes.

Existing protections stay: append-only records, public-sensor projection,
isolation of evaluator files, and infrastructure-error separation.

## 8. Compute and cost

- GPU work runs on a Prime Intellect pod, using the existing bootstrap scripts
  and the independent local termination watchdog. Each rental needs a stated
  budget and armed watchdog first; source `scripts/project_env.sh` before
  starting the policy worker.
- Screening: up to about 500 plain-VLA episodes plus diagnostic runs. Estimated
  $20–40 of GPU time, to be checked against current prices before renting.
- Evaluation: about 2 systems × up to 80 scene seeds plus baselines. API cost
  estimated after measuring tokens per call with the new 15-image observation.
  Both estimates are confirmed with the user before spending.

## 9. Schedule

| Dates | Work |
|---|---|
| Oct 2–3 | Local implementation, section 7 items 1–8 |
| Oct 4–6 | GPU screening |
| Oct 7 | Freeze release; fresh set-B reference runs |
| Oct 8–12 | Two LLMs and both baselines on the frozen set |
| Oct 13–16 | Scorecard, failure attribution, README, results write-up |

## 10. Risks and fallback

- **No task splits cleanly.** Leave-alone and needs-help seeds may not coexist
  within GR00T tasks. Mitigation: screen more seeds and tasks. Fallback
  deliverable: an audit showing existing orchestration-benchmark designs cannot
  detect over-intervention, with whatever seed evidence exists.
- **Noise.** With one system episode per scene seed, small differences will not
  be significant. Report intervals; do not rank systems whose intervals overlap.
- **Executor dependence.** Scores mean "intervention judgement over GR00T N1.5 on
  these tasks". State this in all results.
- **GPU nondeterminism.** Identical scene and policy seeds may still diverge.
  Measure reference-to-always-defer agreement on set B and report it.
- **Contract changes.** Generic scoring, native goals, seed separation, new
  baselines and cards must be recorded in `docs/decisions.md`. Development
  episodes from September 27 are not comparable.
