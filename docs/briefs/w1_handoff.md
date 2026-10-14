# W1 handoff: context for the next W1 agent (written October 13, 2026)

You continue **W1 (scoring, analysis, final experiment, integration and write-up)** for Tom Wang. This file holds
everything from the session that built W1 that is not obvious from the code. Read it after `AGENTS.md`,
`handoff.md` section S, `docs/direction.md`, `docs/work_split.md` and `docs/briefs/w1_scoring.md`. Work on branch
**`w1-scoring`** (pushed to origin; last commit `fd3e49e`); it is not merged to `main`.

## 1. How to work with Tom

- **Think critically; do not just agree.** He called out blind agreement once. When he proposes something, check it
  against the evidence and say plainly what is weak. Earlier pushback that he accepted:
  - custom scenes were the wrong first step, since the policies would sit at zero and we cannot train;
  - "the policy fails unseen tasks" does not by itself make an orchestrator useful;
  - all-new tasks reward "always interrupt".
- **Decisions are his.** For each, list the options, give the advantages and trade-offs with numbers from our data,
  then ask with `AskUserQuestion`, recommendation first. He decided the score parameters, the baselines, the policies
  and the task rule this way.
- **Explain jargon.** He did not know what "fallback mode" or "re-count, drop zero cells" meant until it was spelled
  out. Define terms the first time, in plain words.
- **Act on authorized, reversible work without asking. Ask before new spending, before merging to `main`, and before
  pushing anything he has not asked to push.** In this session he asked to push `w1-scoring`; merging the workstream
  branches into `main` has **not** been approved yet.
- **Report** numbers with sample sizes, and say what a result does not show. Keep replies concise. Never print or
  commit keys; the repository is public.

## 2. The project and the direction (decided October 11-12)

- **What OrcaBench measures:** whether an LLM supervisor of frozen learned robot policies (VLAs) in RoboCasa365
  chooses **when to interrupt and how often to check in**, so that the pair finishes tasks **fast and reliably**.
- **Tom's framing:** a VLA is fast but unreliable; an LLM is smart but slow; is the supervisor smart enough to get
  both benefits? One supervisor, in one context, supervises several policies of different ability and should adapt.
- **Decided, in order:**
  - environment first, policies second;
  - real RoboCasa tasks, not the abstract simulator (now a development tool);
  - a mix of unseen composite tasks and trained tasks;
  - time pressure through **scoring, not physics**: a per-call time charge and deadlines, plus hidden "story" timers
    on five unseen tasks (ice melts, food cools), which are not artificial disturbances;
  - several policies from the official RoboCasa365 checkpoints, with no training.
- **Rejected:** custom scenes from scratch, visible physical melting, and one real policy plus invented profiles.
- **Deadline:** deliverable on **October 16**; freeze on **October 14**; final runs on **October 15**.

## 3. Evidence behind the design (all diagnostic, never scores)

- **Stage 3** (seen tasks, pairs where the plain policy succeeded): Opus 5.5 failed 14 of 34 against a 3% noise floor.
  Left alone, it failed only by declaring 12-48 steps early. Completion of hidden-state tasks (rinse, scrub,
  microwave) is never recognized from images. On its successes, Opus stopped about halfway through the budget.
- **Stage 4** (Ranveer; failure pairs): restarts rescued 4 of 21, one episode each; Opus rescued 1 of 19.
- **Simulator:** Opus learns *when* to restart from records; neither model learns *how often* to look. Its rescue
  assumption (0.85 per restart) was about ten times too optimistic.
- **Stage 5** (Tom's pod, $2.72): the multitask GR00T solved 5 of 62 unseen-task episodes (36% on seen tasks); the
  pretraining-only GR00T solved 0 of 62. Failures are mostly all or nothing.
- **Stage 6, W2** (branch `w2-policies`):
  - **Ladder:** `groot` 24/40 trained and 0/63 story; `groot_u30` 13/40 and 5/64; `groot_u10` 12/40 and 5/63,
    indistinguishable from `groot_u30`; `groot_pretrain` 25/40 trained, a near-copy of `groot`. These are two
    crossing profiles, not a three-level ladder.
  - **Ceiling test:** step-by-step prompting rescued nothing: 3 sequencer vs 4 plain successes over 76 pairs, largest
    margin 1.
  - **Machines differ:** `groot` solved 0/63 on W2's pod against 5/62 on Tom's, on overlapping tasks. Start states
    are machine-specific, so per-task rates do not transfer across pods.

## 4. What W1 has built (branch `w1-scoring`; all tested; 304 tests pass on Python 3.12)

- **`src/robot_benchmark/time_score.py`** (analysis only, outside the contract hash):
  - **value** = success × max(0, 1 − charged/deadline); charged = robot seconds + `call_seconds[model]` per LLM
    response; story limits; failures score 0, so declaring early never pays;
  - fixed rules (declare at step T × restart family), with hindsight, leave-one-out and oracle values, estimated from
    unselected reference runs when present;
  - the pooled rule;
  - `read_session` and `session_summary` (per-label regret, the pooled-rule value, learning).
- **Scripts:**
  - `scripts/score_time.py`: per-episode scores; unpaired, paired and paired held-out regret; sessions; and the
    **primary result** (per-model paired held-out regret with a 95% bootstrap clustered by (task, scene), plus model
    differences); `--call-seconds` sensitivity.
  - `scripts/set_story_limits.py`: rule fixed in advance: the largest per-policy median trigger-to-success time among
    policies with at least 2 successes, plus 3 × the slowest `call_seconds`, rounded up to 5 s.
  - `scripts/select_final.py`: rules fixed in advance, with `--policies` for Tom's explicit choice.
  - `scripts/make_session_plans.py`: one session per scene, task blocks, shuffled anonymous labels, seed 20261014.
- **Settings:**
  - `configs/time_pressure.json`: per-model `call_seconds` (provisional Opus 4.7, Sonnet 2.2), deadline = step budget
    for all 32 tasks, five story tasks with `limit_seconds: null`.
  - `configs/final/selection.json`: the provisional selection.
- **Docs:**
  - `docs/time_score.md`: definition and offline validation. On stage 3, the declaration time varies from 7 to 57 s by
    task. Opus's paired held-out regret is 0.06 [-0.03, 0.16] with no charge and 0.27 [0.20, 0.35] at 4.7 s, so the
    call charge decides the verdict. Short tasks are swamped by the charge.
  - `docs/final_experiment.md`: design, pods, freeze checklist, run procedure, analysis plan.
  - `docs/report.md`: a draft; section 5 is filled only from `runs/final/score.json`.
  - The scoring section of `docs/protocol.md`; decision-log rows dated October 13.

## 5. Decisions Tom made on October 13 (all logged in `docs/decisions.md`)

1. **Call charge per model:** the median seconds per call, measured once under prompt version 6 (W3's probe and
   pilot) and **frozen October 14**. An uncalibrated model cannot be scored.
2. **Deadline = the task's step budget.**
3. **The first response is charged.**
4. **Baselines:** always-defer on both final pods (paired with every LLM episode); `reissue_50`, `reissue` (100) and
   `reissue_200` on pod A only (unpaired). Restarts are the control for *when to interrupt*.
5. **Fallback (monitoring) mode applies:** by the pre-declared rule, because no unseen task was rescuable. The report
   must say the benchmark measures monitoring, declaring and restraint, not rescue.
6. **Final policies:** `groot`, `groot_u30` and **`pi05`**. Tom insists on running both GR00T and π0.5. π0.5 has never
   run here; W2 must set it up, smoke-test it and run the ladder grid. JAX needs `XLA_PYTHON_CLIENT_PREALLOCATE=false`
   next to GR00T workers.
7. **Unseen tasks by the original rule:** most plain successes pooled over **all** candidate policies, π0.5 included
   once measured. Provisional: ArrangeTea, MakeIceLemonade, PanTransfer, WaffleReheat. Leave-alone tasks provisional:
   OpenCabinet, PickPlaceCounterToStove, CloseFridge.

## 6. What is left for W1, in order

1. **When W2 pushes π0.5's ladder cells:**
   - rerun `scripts/select_final.py --ladder <analysis.json> --ceiling <ceiling.json> --policies groot groot_u30 pi05
     --output configs/final/selection.json`;
   - log the final selection in `docs/decisions.md`;
   - if π0.5 cannot run cleanly, bring Tom the choice: move the freeze, or two GR00T policies with π0.5 reported as
     untested.
2. **Story limits:** W2 runs `scripts/set_story_limits.py` on the raw runs with trigger logs (the ceiling plain arm
   and π0.5's ladder), which are on their machine. Write the printed limits into `configs/time_pressure.json` (you own
   it). Only MakeIceLemonade and PanTransfer are story tasks in the provisional set.
3. **Latency:** when W3 reports the medians under prompt version 6, set `call_seconds` and mark the config's `status`
   frozen.
4. **Plans:** `scripts/make_session_plans.py --policies groot groot_u30 pi05 --tasks <final 7> --scenes 1000 1001 1002
   1003 --output configs/final/plans`.
5. **Integration, October 14, with Tom's approval:**
   - merge `w1-scoring`, `w2-policies` and W3's branch into `main`;
   - `docs/decisions.md` is append-only, so conflicts are row order only;
   - run the full suite and tag `release-2026-10-14`.
6. **October 15:** W2 runs pod A (always-defer, the Opus sessions and the three restart schedules); W3 runs pod B
   (always-defer and the Sonnet sessions). Both use the same GPU type. Score with
   `scripts/score_time.py <pod roots> --output runs/final/score.json`.
7. **October 16:**
   - fill section 5 of `docs/report.md` from `runs/final/score.json` only;
   - state monitoring mode and every deviation;
   - update `handoff.md`, `README.md` and `docs/protocol.md`.
8. **Optional:** ask Ranveer for stage 4's restart runs (JSON only) to evaluate restart rules offline.

## 7. Environment and data gotchas

- **Python:** the shell's `python3` is the system 3.9, which cannot import the codebase (`dict | None`). Run tests with
  `PYTHONPATH=src ~/.local/share/uv/python/cpython-3.12.11-macos-aarch64-none/bin/python3.12 -m unittest discover -s
  tests`. The project requires Python 3.11-3.12.
- **Data (`runs/` is Git-ignored):**
  - **On Tom's Mac:** `runs/stage2_remote`, `runs/stage3_remote` (the reference runs estimate the stage 3 fixed
    rules), `runs/stage5`, `runs/time_score` and `runs/sim`.
  - **On branch `w2-policies` (force-added):** `runs/stage6_ladder/analysis.json` and `runs/stage6_ceiling/ceiling.json`.
    Read them with `git show origin/w2-policies:<path>`.
  - **Raw stage 4 and 6 episodes:** on Ranveer's machine and his private Hugging Face bucket.
- **Disk:** Tom's Mac has about 8 GB free. `runs/stage5/**/frames` can be pruned if needed.
- **Money:** the team Prime wallet holds $225.24. W2 used Ranveer's personal account. API spend from Tom's key across
  the project is about $11 of a $15 cap.
- **No pod is running.** Every pod needs `scripts/pod_guard.sh backstop` plus the Mac watchdog (`handoff.md` S.3).
