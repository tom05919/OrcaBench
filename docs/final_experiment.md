# Final experiment (W1; protocol fixed October 13, 2026, selections applied October 14)

The scored run for the October 16 deliverable. Everything that can be decided without W2's and W3's results is fixed
here. The rest is computed by scripts from their outputs, under rules written before those outputs exist. Score:
`docs/time_score.md`. Owners: `docs/work_split.md`.

## Design

| Element | Value | Source |
|---|---|---|
| Policies | 3 backends | `scripts/select_final.py` on W2's ladder: the widest spread of plain success on the chosen unseen tasks; `groot_pretrain` excluded |
| Unseen tasks | up to 4 | Helpable in W2's ceiling test (sequencer beats plain by ≥ 2 paired successes for some policy), story tasks first. **Fallback** if fewer than 2 are helpable: the unseen tasks with the most plain success; the benchmark then measures monitoring and declaring rather than rescue, and the report says so. |
| Leave-alone tasks | 3 | From OpenCabinet, PickPlaceCounterToCabinet, PickPlaceCounterToStove, OpenDrawer, CloseFridge: highest minimum plain success across the chosen policies |
| Scenes, seed | 1000-1003, policy seed 0 | Stage 5 found most unseen-task successes in one scene, so four scenes |
| Cells | 3 policies × about 7 tasks × 4 scenes ≈ 84 | |
| Supervisors | Opus 5.5 and Sonnet 5.5, effort `medium`, prompt version 6 (W3) | `configs/model-*.json` |
| Sessions | One per scene per model: every (policy, task) cell once, in task blocks (the task with each policy, shuffled), with anonymous labels shuffled per session. The same plans for both models. | `scripts/make_session_plans.py --seed 20261014` |
| Baselines | always-defer on both pods (paired with every LLM episode); `reissue_50`, `reissue` (100) and `reissue_200` on pod A only (unpaired) | Decided October 13 |
| Score | value = success × max(0, 1 − charged / deadline). Deadline = step budget; per-model call charge, frozen; first response charged; story limits from `scripts/set_story_limits.py` | `configs/time_pressure.json` |

**Pods.** Both pods use **the same GPU type** (the contract hash includes the GPU name) and the tagged commit.

| Pod | Credits | Runs | Episodes |
|---|---|---|---|
| A | W2 | always-defer, Opus sessions, `reissue_50`, `reissue`, `reissue_200` | about 420 |
| B | W3 | always-defer, Sonnet sessions | about 168 |

- **Pod time:** stage 5 ran about 37 long episodes per hour on 7.65 cores. Pod A therefore needs about 11 hours on a
  similar pod, or about 5-6 on one with 16 or more cores and 6-8 streams. **Use a 16-core or larger pod for A.** Moving
  `reissue_200` to pod B would balance the pods with no effect on the analysis, because restart comparisons are
  unpaired either way; it needs a `docs/decisions.md` row first.
- **API, estimated:** Opus about $0.10 per episode, about $9 for 84; Sonnet about $4. Earlier episodes are cache reads.
  Each person's own key; stop at the cap they set.

## Freeze checklist (October 14, in order)

1. **W2** pushes the ladder table (`runs/stage6_ladder/analysis.json` via `scripts/analyze_stage5.py`), the ceiling
   summary (`runs/stage6_ceiling/summary.json`) and the trigger predicates. **W3** pushes session mode, prompt version 6
   and the latency calibration (median seconds per call per model).
2. **Select:** `python3 scripts/select_final.py --output configs/final/selection.json`. Log the selection, including
   whether the fallback applies, in `docs/decisions.md`.
3. **Story limits:** `python3 scripts/set_story_limits.py runs/stage6_ladder --policies <the three> --write`. Write
   W3's calibrated `call_seconds` into `configs/time_pressure.json` and set `status` to frozen.
4. **Plans:** `python3 scripts/make_session_plans.py --policies <the three> --tasks <chosen> --scenes 1000 1001 1002
   1003 --output configs/final/plans`.
5. **Merge and tag:** merge the three workstream branches to `main`, run the full test suite (Python 3.11-3.12), and tag
   `release-2026-10-14`. From then on nobody changes hashed files, configs, prompts, budgets or plans.

## Run procedure (October 15, each pod)

1. **Setup** as in `docs/compute.md` and `handoff.md` S.3. Download the chosen checkpoints, and start one policy worker
   per backend on separate ports. Arm `scripts/pod_guard.sh backstop` and the Mac watchdog before anything runs.
2. **always-defer** on every cell: `baseline --agent always_defer`, one backend at a time with its worker URL, scenes
   1000-1003, policy seed 0. W3's tooling reads each episode's step-0 state hash into the plan entries as
   `expect_state`, so every session episode starts from the same state as its twin on this pod.
3. **Sessions** for this pod's model, with W3's `session` command, all four plans, and the label-to-worker mapping.
   A `scene mismatch` ends an episode before any model call; that pair is reported invalid and is not retried with a
   different scene.
4. **Pod A only:** `baseline --agent reissue_50`, `reissue` and `reissue_200` on every cell.
5. **Copy back** JSON, JSONL and MP4 after every phase, no PNG frames. Terminate the pod when done and verify it is
   gone.

**Stops:** two infrastructure errors in a row, a policy worker dying, or a dollar cap reached. Every attempted
episode is kept.

## Analysis plan (declared before any final result)

`python3 scripts/score_time.py runs/final/podA runs/final/podB --output runs/final/score.json`

- **Primary, per model:** mean **paired held-out regret**. This is the always-defer twin's declare-at-T value on the
  same pod, scene and seed (T chosen without that scene), minus the model's value. Report a 95% bootstrap interval
  with resampling clustered by (task, scene).
  - **Claim** "beats" or "loses to" the best fixed rule only if the interval excludes 0.
  - **Model comparison:** the Opus − Sonnet difference in paired regret, with its interval. Each model's twins are on
    its own pod, so paired regret is what makes the two pods comparable.
- **Secondary, descriptive:**
  - regret against the best of all fixed-rule families, including the restart schedules (unpaired);
  - **adaptation:** per policy, the model's mean value against the pooled rule's value (one declaration time for all
    policies) and against the policy's own rule;
  - **learning:** second-half minus first-half regret per policy within a session;
  - success, false-completion rate, declaration lag, calls, median interval, restarts and rewrites per policy;
  - story outcomes per story task.
- **Not claimed:** per-task or per-policy rates (4 scenes each), and any comparison across pods except through paired
  regret.
