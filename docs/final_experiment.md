# Final experiment (W1; protocol fixed October 13, 2026, selections applied October 14)

The scored run for the October 16 deliverable. Everything that can be decided without W2's and W3's results is fixed
here. The rest is computed by scripts from their outputs, under rules written before those outputs exist. Score:
`docs/time_score.md`. Owners: `docs/work_split.md`.

## Design

| Element | Value | Source |
|---|---|---|
| Policies | **`groot` (multitask), `groot_u30`, `pi05`** (Tom, October 13) | W2's ladder had no three distinct GR00T levels: `groot_u10` and `groot_u30` cannot be told apart, and `groot_pretrain` matches `groot` on trained tasks. Tom chose the two crossing GR00T profiles (`groot` strong on trained tasks and 0/63 on story tasks; `groot_u30` 5/64 on story tasks and 13/40 on trained) and **π0.5 as a second architecture**. `select_final.py --policies` replaces rule 2. π0.5 is untested (null) until W2 measures it. |
| Unseen tasks | **Fallback (monitoring) mode applies:** no task met the ceiling rule (largest margin 1; 3 sequencer vs 4 plain successes over 76 pairs, `docs/stage6_ceiling.md`). The unseen tasks are therefore those with the most plain successes **pooled over all candidate policies** (original rule, Tom, October 13). Provisional: ArrangeTea, MakeIceLemonade, PanTransfer, WaffleReheat, from `groot`, `groot_u10` and `groot_u30`. **Rerun `select_final.py` once π0.5's ladder cells exist**, since its successes count too. | The benchmark measures monitoring, declaring and restraint, not rescue; the report says so |
| Leave-alone tasks | 3, the highest minimum plain success across the chosen policies. Provisional, from `groot` and `groot_u30`: OpenCabinet, PickPlaceCounterToStove, CloseFridge (tie with PickPlaceCounterToCabinet broken by name). Recomputed with π0.5. | `configs/final/selection.json` |
| Scenes, seed | 1000-1003, policy seed 0 | Stage 5 found most unseen-task successes in one scene, so four scenes |
| Cells | 3 policies × 7 tasks × 4 scenes = 84 | |
| Supervisors | Opus 5.5 and Sonnet 5.5, effort `medium`, prompt version 6 (W3) | `configs/model-*.json` |
| Sessions | One per scene per model: every (policy, task) cell once, in task blocks (the task with each policy, shuffled), with anonymous labels shuffled per session. The same plans for both models. | `scripts/make_session_plans.py --seed 20261014` |
| Baselines | always-defer on both pods (paired with every LLM episode); `reissue_50` and `reissue` (100) on pod A, `reissue_200` on pod B (all unpaired) | Decided October 13; `reissue_200` moved to pod B on October 14 |
| Score | value = success × max(0, 1 − charged / deadline). Deadline = step budget; per-model call charge, frozen; first response charged; story limits from `scripts/set_story_limits.py` | `configs/time_pressure.json` |

**Pods.** Both pods use **the same GPU type, an A100 80 GB SXM4** (Tom, October 14; the contract hash includes the GPU
name), and the tagged commit.

| Pod | Credits | Runs | Episodes |
|---|---|---|---|
| A | W2 | always-defer, Opus sessions, `reissue_50`, `reissue` | about 336 |
| B | W3 | always-defer, Sonnet sessions, `reissue_200` | about 252 |

- **Pod time:** stage 5 ran about 37 long episodes per hour on 7.65 cores. Pod A therefore needs about 9 hours on a
  similar pod and pod B about 7, or about 4.5 and 3.5 on pods with 16 or more cores and 6-8 streams. **Use 16 or more
  cores on both pods.** `reissue_200` runs on pod B (Tom, October 14) to balance the pods; restart comparisons are
  unpaired either way, so the analysis is unchanged.
- **API, estimated:** Opus about $0.10 per episode, about $9 for 84; Sonnet about $4. Earlier episodes are cache reads.
  Each person's own key; stop at the cap they set.

## Freeze checklist (October 14, in order)

0. **π0.5 (W2, before anything else).**
   - **Install:** `bootstrap_gpu.py --include-pi05 --download-pi05-checkpoint`. The backend code exists but has never
     run in this project.
   - **GPU memory:** set `XLA_PYTHON_CLIENT_PREALLOCATE=false` (or `XLA_PYTHON_CLIENT_MEM_FRACTION`) whenever a π0.5
     worker shares a GPU with GR00T workers; JAX otherwise takes 75% of GPU memory.
   - **Smoke test:** one plain episode.
   - **Ladder:** the 8 story tasks and 5 leave-alone tasks × scenes 1000-1003 × policy seeds 0, 1, added to
     `runs/stage6_ladder/analysis.json`.
   - **If π0.5 cannot run cleanly by the freeze,** Tom decides between moving the freeze and proceeding with the two
     GR00T policies. π0.5 is then reported as untested, never as zero.
1. **W2** pushes the ladder table (`runs/stage6_ladder/analysis.json` via `scripts/analyze_stage5.py`), the ceiling
   table (`runs/stage6_ceiling/ceiling.json`, the name in `docs/work_split.md`) and the trigger predicates. **W3**
   pushes session mode, prompt version 6 and the latency calibration (median seconds per call per model).
2. **Select:** `python3 scripts/select_final.py --policies groot groot_u30 pi05 --output configs/final/selection.json`. Log the selection, including
   whether the fallback applies, in `docs/decisions.md`. Before the merge, W2's two tables are only on its branch:
   extract them with `git show origin/w2-policies:<path>` and pass `--ladder` and `--ceiling`.
3. **Call charge, then story limits.** First write W3's calibrated `call_seconds` into `configs/time_pressure.json`.
   Each model's charge is the median over one replayed call per recorded observation of W3's eight-episode pilot,
   with each observation's own preceding experience (Tom, October 14). The story limit adds 3 responses at the slowest
   calibrated latency, so it must be computed from the frozen values.
   Then `python3 scripts/set_story_limits.py <runs with trigger logs> --policies groot groot_u30 pi05 --config <that
   file>`. The trigger predicates are logged only in runs after W2's commit `938b7fd`: the ceiling plain arm and π0.5's
   ladder. Those episodes are on W2's machine, so W2 runs the script and W1 writes the printed limits into the config
   and sets `status` to frozen.
4. **Plans:** `python3 scripts/make_session_plans.py --policies <the three> --tasks <chosen> --scenes 1000 1001 1002
   1003 --output configs/final/plans`.
5. **Merge and tag:** merge the three workstream branches to `main`, run the full test suite (Python 3.11-3.12), and tag
   `release-2026-10-14`. From then on nobody changes hashed files, configs, prompts, budgets or plans.

## Run procedure (October 15, each pod)

1. **Setup** as in `docs/compute.md` and `handoff.md` S.3. Download the chosen checkpoints (including π0.5, with the JAX memory setting above), and start one policy worker
   per backend on separate ports. Arm `scripts/pod_guard.sh backstop` and the Mac watchdog before anything runs.
2. **always-defer** on every cell: `baseline --agent always_defer`, one backend at a time with its worker URL, scenes
   1000-1003, policy seed 0. W3's tooling reads each episode's step-0 state hash into the plan entries as
   `expect_state`, so every session episode starts from the same state as its twin on this pod.
3. **Sessions** for this pod's model, with W3's `session` command, all four plans, and the label-to-worker mapping.
   A `scene mismatch` ends an episode before any model call; that pair is reported invalid and is not retried with a
   different scene.
4. **Restart schedules:** pod A runs `baseline --agent reissue_50` and `reissue`, pod B runs `reissue_200`, each on
   every cell.
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
