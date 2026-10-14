# Stage 6: the policy ladder (W2, October 13, 2026)

A **diagnostic development run** (`diagnostic_reference`): plain policies only, no model calls, nothing here is a
benchmark score. It answers W2 in `docs/work_split.md`: which three policies differ clearly in ability on the chosen
tasks, and do they still solve the trained tasks where leaving them alone is right. The plan below was fixed before
any episode ran.

## Policies

All GR00T N1.5, pinned at revision `c484448a` of `robocasa/robocasa365_checkpoints` (`configs/sources.lock.json`,
`scripts/download_checkpoint.py`, `policy_worker.py`; config and shard index are byte-identical to the multitask pin).

| Backend | Checkpoint | Training | Published average on these 16 tasks (`test` split, 30 rollouts each) |
|---|---|---|---|
| `groot_u10` | `target_fraction/composite_unseen_10p` | pretraining (80k steps), then 60k steps on the 16 `composite_unseen` tasks with 50 of 500 demos each | 22.7% |
| `groot_u30` | `target_fraction/composite_unseen_30p` | the same with 150 demos each | 30.8% |
| `groot` | `multitask_learning/checkpoint-120000` | multitask (existing pin) | not published; 5 of 62 in stage 5 on our `pretrain` split |

The published numbers come from each checkpoint's `eval_results.json` and use RoboCasa's held-out `test` kitchens.
Ours use the `pretrain` split (`task_parts` requires it), so they are not comparable. `groot_pretrain` is dropped: 0
of 62 in stage 5.

## Grid (`scripts/run_stage6_ladder.sh`)

- **Story tasks** (the eight with a time story, `docs/task_catalog.md`): MakeIceLemonade, SeparateFreezerRack,
  PanTransfer, PortionHotDogs, GarnishPancake, HeatKebabSandwich, WaffleReheat, ArrangeTea.
- **Leave-alone tasks:** the five seen tasks the multitask checkpoint solved most often in stage 4 (OpenCabinet 8/8,
  PickPlaceCounterToCabinet 6/8, PickPlaceCounterToStove 6/8, CloseFridge 4/8, OpenDrawer 4/8). Sink and scrub tasks
  are left out because their scenes do not rebuild reliably.
- **Episodes:** scenes 1000-1003 x policy seeds 0, 1 on both sets, for each of the three checkpoints (104 each, 312
  in all), on one pod so start states are comparable.
- A build check of all 13 tasks at the four scenes runs first. A scene whose checker is true at step 0 is reported
  and never counted (rule from stage 5).

## Reading (fixed before the results)

`scripts/analyze_stage5.py --root runs/stage6_ladder --backends groot groot_u10 groot_u30`: successes per task and
backend, subgoal progress from the evaluator predicates, and stage 5's per-task reading (leave-alone candidate,
re-prompting candidate, unlikely to be helped, mixed).

- **Ladder:** recommend three policies whose story-task success counts are clearly separated, with partial progress
  on some failures (so supervision has something to rescue). Report counts per task, never pooled rates to quote.
- **Leave-alone:** a policy that solves fewer than half of a leave-alone task's episodes is reported as having
  forgotten it; that task is then leave-alone only for the policies that still solve it.

## Compute and guards

One Prime pod on Ranveer's personal account: RunPod A100 80 GB, 32 vCPUs, $1.81/hr (the 36-vCPU L40 and L40S
offers were out of stock). Six policy workers, two per checkpoint (four took about 35 GB in stage 4). Caps: **$10 GPU,
pod deadline 5.5 hours after creation** (about $11 if the backstop has to fire), `BUDGET_MINUTES=240` per driver.
`scripts/pod_guard.sh` syncs `runs/stage6_ladder` to the private Hugging Face bucket every 30 minutes and after the
run, then terminates the pod; the backstop and the Mac watchdog remain. The pod gets only the Hugging Face and Prime
keys, not the Anthropic key.

## Results (October 13, 2026)

319 episodes, all kept (`runs/stage6_ladder/`, private bucket `stage6_ladder`). Analysis:
`runs/stage6_ladder/analysis.json`. No scene was solved at step 0. The run used the backend names `groot_10p` and
`groot_30p`, renamed afterwards to the agreed `groot_u10` and `groot_u30` (`docs/work_split.md`): the episode
manifests keep the old names, with the same `checkpoint_manifest_sha256` as the renamed pins, and the local run
folders were renamed to match. Counts are valid episodes; infrastructure errors
are listed separately below.

| Task | `groot` | `groot_u30` | `groot_u10` |
|---|---|---|---|
| ArrangeTea | 0/8 | 2/8 | 1/8 |
| GarnishPancake | 0/7 | 0/8 | 1/7 |
| HeatKebabSandwich | 0/8 | 0/8 | 0/8 |
| MakeIceLemonade | 0/8 | 0/8 | 2/8 |
| PanTransfer | 0/8 | 2/8 | 0/8 |
| PortionHotDogs | 0/8 | 0/8 | 0/8 |
| SeparateFreezerRack | 0/8 | 0/8 | 0/8 |
| WaffleReheat | 0/8 | 1/8 | 1/8 |
| **Story tasks** | **0/63** | **5/64** | **5/63** |
| OpenCabinet | 6/8 | 4/8 | 4/8 |
| PickPlaceCounterToCabinet | 6/8 | 2/8 | 0/8 |
| PickPlaceCounterToStove | 6/8 | 4/8 | 8/8 |
| CloseFridge | 3/8 | 2/8 | 0/8 |
| OpenDrawer | 3/8 | 1/8 | 0/8 |
| **Leave-alone tasks** | **24/40** | **13/40** | **12/40** |

Story-task successes come late (first success between steps 399 and 3623, against 154-733 on the
leave-alone tasks), and many failures make partial progress:
PortionHotDogs puts an item on a plate in 5-7 of 8 episodes per policy, GarnishPancake reaches the strawberry in 4-5,
PanTransfer moves vegetables in 2-4. HeatKebabSandwich, ArrangeTea and WaffleReheat report no subgoal predicates.

### Reading

- **No three-step ladder on the story tasks.** The rule fixed above asks for three clearly separated counts. They
  are 0, 5 and 5: `groot_u10` and `groot_u30` cannot be told apart (Fisher exact p = 1.0, and 17 vs 18 successes
  overall), and `groot` against either is borderline (p = 0.058). The published 22.7% vs 30.8% gap on the `test`
  split does not show at 8 episodes per task on our `pretrain` split.
- **The two kinds of policy cross over.** The multitask checkpoint solves the leave-alone tasks about twice as often
  (24/40 vs 13/40, p = 0.024, and 12/40, p = 0.013) and no story task; post-training on the unseen tasks buys a few
  story successes at the cost of the seen tasks.
- **Leave-alone per policy** (fewer than half solved means forgotten):
  - `groot`: OpenCabinet, PickPlaceCounterToCabinet, PickPlaceCounterToStove. CloseFridge and OpenDrawer (3/8 each,
    4/8 in stage 4) fall just below the line.
  - `groot_u30`: OpenCabinet and PickPlaceCounterToStove (4/8 each, on the line).
  - `groot_u10`: PickPlaceCounterToStove (8/8) and OpenCabinet (4/8).
  - Only OpenCabinet and PickPlaceCounterToStove remain leave-alone tasks for all three.
- **No stronger rung to add.** At the pinned revision the repository has `eval_results.json` for
  `composite_unseen_10p` and `_30p` only (plus `atomic_seen_30p` and `composite_seen_10p`/`_30p`); there is no
  higher-fraction `composite_unseen` checkpoint.

### Recommendation (for W1)

Supervise **`groot`** and **`groot_u30`**, as two policies of genuinely different ability profiles rather than three
rungs. Prefer `_30p` over `_10p`: they tie here, `_30p` is the published-stronger checkpoint, and it fails no
leave-alone task outright (`_10p` is 0/8 on three). The third-policy run below measured `groot_pretrain` on the
leave-alone tasks: it matches `groot` there (25/40 vs 24/40), so it adds no third ability level; see its reading.

### Infrastructure errors

Nine episodes (seven in the first pass, two on rerun) ended on the static-noise frame guard (`docs/decisions.md`,
2026-10-05) and are kept as `infrastructure_error`; the driver's second pass reran them. Every PortionHotDogs error
(scene 1002 p1 for all three policies, 1003 p0 for `groot` and `groot_u10`) reran cleanly.
GarnishPancake scene 1001, policy seed 0 failed twice at step 1328-1331 for both `groot` and `groot_u10` (it ran
cleanly for `groot_u30`), so those two cells hold 7 valid episodes. The repeat at the same step
across checkpoints suggests a scene-specific render failure rather than random static; the failing frame falls
between video samples (every 10 steps), so it was not inspected.

### Cost

Drivers ran 05:27-09:18 UTC; the pod guard made a final sync and terminated the pod at 09:18. Billed $7.60 (cap
$10). The backstop and the Mac watchdog did not fire.

## Third policy: `groot_pretrain` on the leave-alone tasks (plan, fixed before the run)

The recommendation above leaves `groot_pretrain`'s leave-alone cells null. This run measures them, so W1 can choose a
third policy from counts rather than a gap.

- **Grid (`scripts/run_stage6_pretrain.sh`):** the plain `groot_pretrain` checkpoint
  (`checkpoints/groot_pretrain/checkpoint-80000`, pinned October 12) on the five leave-alone tasks, scenes 1000-1003 x
  policy seeds 0, 1: 40 episodes, the same settings as the ladder run (`run_stage4.sh workers plain`, video every 10
  steps), after a build check of the five tasks at the four scenes. Its story-task cells are stage 5's (0 of 62).
- **Reading:** the leave-alone rule above (fewer than half of a task's episodes solved means forgotten), per task.
  The other policies' counts come from a different pod; scenes are rebuilt from the same seeds, but start states are
  not matched across pods, so counts are compared per task, not as pairs.
- **Compute:** one Prime pod on Ranveer's account, four policy workers (`WORKER_THREADS=2`, see
  `docs/stage6_ceiling.md`). Caps: **$4 GPU, pod deadline 2.5 hours after creation**, `BUDGET_MINUTES=120`.
  `scripts/pod_guard.sh` syncs `runs/stage6_pretrain` to the private bucket and terminates the pod; backstop and Mac
  watchdog as before.

## Third policy: results (October 13, 2026)

40 episodes, all kept (`runs/stage6_pretrain/`, private bucket `stage6_pretrain`); no infrastructure errors, no scene
solved at step 0, every task built at the four scenes. Analysis: `scripts/analyze_stage5.py --root
runs/stage6_pretrain`; `runs/stage6_ladder/analysis.json` also includes it (the folder is linked in as
`runs/stage6_ladder/groot_pretrain`), with only the five leave-alone tasks for that backend. The driver ran 23:14-23:24 UTC on a RunPod L40S 48 GB pod (31-CPU quota, four workers);
the pod guard synced and terminated the pod at 23:25. Wallet change $1.55 (cap $4); backstop and Mac watchdog did
not fire.

| Task | `groot_pretrain` | `groot` (ladder) | `groot_u30` (ladder) | `groot_u10` (ladder) |
|---|---|---|---|---|
| OpenCabinet | 3/8 | 6/8 | 4/8 | 4/8 |
| PickPlaceCounterToCabinet | 6/8 | 6/8 | 2/8 | 0/8 |
| PickPlaceCounterToStove | 7/8 | 6/8 | 4/8 | 8/8 |
| CloseFridge | 6/8 | 3/8 | 2/8 | 0/8 |
| OpenDrawer | 3/8 | 3/8 | 1/8 | 0/8 |
| **Leave-alone tasks** | **25/40** | **24/40** | **13/40** | **12/40** |

The ladder columns come from a different pod, so start states are not matched; counts are compared per task.

### Reading

- **Leave-alone per the rule:** `groot_pretrain` keeps PickPlaceCounterToCabinet, PickPlaceCounterToStove and
  CloseFridge, and falls below half on OpenCabinet and OpenDrawer (3/8 each).
- **Not a third ability level.** On the leave-alone tasks it equals `groot` (25/40 vs 24/40, Fisher p = 1.0) and
  beats both post-trained checkpoints (p = 0.013 against `groot_u30`, 0.007 against `groot_u10`). On the unseen
  tasks it solved 0 of 62 in stage 5 against `groot`'s 5 of 62 (p = 0.057), and `groot` solved none of the eight
  story tasks in the ladder (0/63). So `groot` and `groot_pretrain` share one profile: the seen tasks, not the
  unseen ones.

### Recommendation, revised (for W1)

Still **`groot`** and **`groot_u30`**: two measured profiles (seen-task strong vs. a few unseen successes with the
seen tasks partly forgotten). There is no third policy of clearly different ability among the pinned checkpoints;
`groot_pretrain` is measured now and is a near-copy of `groot` on both task sets. If the design needs three policies
anyway, `groot_pretrain` is the one to add as a weaker-on-unseen variant of `groot`, with the borderline unseen gap
(p = 0.057) stated. The only leave-alone task for all four policies is PickPlaceCounterToStove (`groot_u30` on the
line at 4/8); OpenCabinet drops out with `groot_pretrain` at 3/8.

## π0.5 (plan, fixed before the run, October 14)

Tom chose π0.5 as the third benchmark policy, a second architecture (`docs/final_experiment.md`, freeze step 0). It
has never run in this project, so it is untested (null) until this run.

- **Checkpoint:** `pi05_pretrain_human300/multitask_learning/75000` at revision `c484448a`, already pinned
  (`policy_worker.py`, `scripts/download_checkpoint.py --backend pi05`), installed with
  `bootstrap_gpu.py --include-pi05 --download-pi05-checkpoint` into `.venv-pi05`.
- **Grid (`scripts/run_stage6_pi05.sh`):** the ladder's 8 story and 5 leave-alone tasks x scenes 1000-1003 x policy
  seeds 0, 1 (104 episodes), plain, video every 10 steps, after a build check of the 13 tasks at the four scenes.
  Four pi05 workers; `run_stage4.sh` turns off JAX's 75% GPU memory preallocation for pi05 and stops if a worker is
  not healthy within 30 minutes.
- **Smoke first:** one plain OpenCabinet episode at scene 1000, policy seed 0 (kept in `smoke/`, not counted). An
  infrastructure error stops the run; then Tom decides between moving the freeze and proceeding with the two GR00T
  policies, and π0.5 is reported as untested.
- **Reading:** the ladder's rules above, per task; the counts go into `runs/stage6_ladder/analysis.json` (folder
  linked in as `runs/stage6_ladder/pi05`) for `scripts/select_final.py`. The story tasks' episodes log the clock
  triggers, for `scripts/set_story_limits.py`.
- **Compute:** one Prime pod on Ranveer's account (80 GB GPU), caps **$8 GPU, pod deadline 4 hours after creation**
  with a 30-minute backstop, `BUDGET_MINUTES=200`; pod guard, backstop and Mac watchdog as before.
