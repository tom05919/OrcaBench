# OrcaBench handoff

Read section A first. Sections 0-15 are the older October 2 handoff: still right about the interface, scoring, seeds, compute commands and tooling gotchas, but their status, branch and "next steps" statements are superseded (A.2).

## A0. Update October 11, 2026 (stage 4, run from Ranveer's Mac)

Read this first, then A below; A.1 items 7, 8 and 10 and A.5 item 1 are updated here.

**Done.**

- **Stage 4 ran: A.5 item 1, the real rescue/harm measurement.** Plan in `docs/stage4_plan.md`, results in
  `docs/stage4_results.md`.
  - Scope: 22 pairs (task, scene) where GR00T failed twice, across 16 tasks, giving 21 reproducible failures.
    Arms per pair: continue, restart every 50/100/200 steps with the native wording, Opus 5.5, and three replays of
    each Opus episode.
  - Restarts: 4 of 21 failures rescued by some restart schedule (TurnOffStove 1000 and 1001, TurnOnMicrowave 1001,
    CloseFridge 1003).
  - Opus: rescued 1 of 19 (OpenDrawer 1001), attributed to wording by replay.
  - Every rescue is a single episode with no repeat.
  - Reply format: 0 rejected replies in 148 Opus calls.
  - Spend: $1.85 GPU and about $3.03 API.
- **Item 7 of A.1 is partly answered.** Restarts do sometimes rescue GR00T, but at about 1 in 20 failed episodes per
  schedule. The simulator's brittle profile assumes a rescue probability of 0.85 per restart (`sim/process.py`), so
  it is far too optimistic.
- **The pod no longer depends on the Mac.**
  - `scripts/pod_guard.sh`, on the pod: uploads results to a private Hugging Face bucket (`scripts/pod_sync.sh`)
    after every phase and every 30 minutes. It terminates the pod after the final upload, or at a deadline, and a
    second backstop process terminates it 45 minutes later.
  - Both processes check the pod's ID and name before terminating. This worked: the pod terminated itself at
    07:21 UTC.
  - The Mac watchdog accepts `--team-id personal`.
  - Driver: `scripts/run_stage4.sh`. Analysis: `scripts/analyze_stage4.py`.
- **Contract change:** `ReplayAgent` replays logs that ended at a budget (`docs/decisions.md`, 2026-10-11). Contract
  hashes changed.

**Accounts and data (this run).**

- Compute was billed to Ranveer's personal Prime account, not team COS597.
- Raw episodes are Git-ignored:
  - on Ranveer's Mac in `runs/stage4_remote/` (3.8 GB, 310 episodes);
  - in a private Hugging Face bucket of Ranveer's (ask Ranveer for access; the path is not published here).
- `runs/stage4_remote/analysis.json` is the per-pair table.

**What is left** (replaces A.5; ask the user before any new spending):

1. **Repeat the five rescues** (four restart, one Opus): three more episodes each on the same pod type. Phases are
   `defer reissue opus`, run with `TASK_LIST` and a hand-made `failures.tsv`, or a small selection change. About
   30 minutes of GPU. This settles whether the rescues are reliable.
2. **Recalibrate and re-run the simulator** (A.5 item 2, about $3 of API):
   - set the brittle profile's rescue probability from stage 4, not the assumed 0.85;
   - vary the call price (`CALL_COST` and `SECOND_COST` in `sim/harness.py`, and the `$0.02` in `SYSTEM_PROMPT` in
     `sim/agent.py`);
   - vary whether the prompt says readings are noisy.
3. **Fix `scripts/compare_to_reference.py`.** It crashes on scene-mismatch episodes, which have no `decisions.jsonl`.
4. Then choose the real task suite and run model comparisons (A.5 item 3), with Sonnet 5.5 as the second system.
   Before then, do not claim which model supervises better.
5. Deadline October 16: write the course deliverable around stages 3-4 plus the simulator. Every result so far is
   `llm_development` or diagnostic, never a score.

## A. Current state (October 10, 2026)

### A.1 In ten lines

1. **Code:** everything is on `main`. The feature branch was merged and deleted. `main` is ahead of `origin/main` and **has not been pushed**; the user has asked only for commits, so push only when asked.
2. **Tests:** 282 pass on the Mac (`PYTHONPATH=src python3 -m unittest discover -s tests`). Run them after any runner change.
3. **Direction changed after Oct 2.** The Oct 2 plan (screen ~800 episodes, label seeds, freeze a release, scorecard) was **not run**; that code is intact and unit-tested only. On Oct 4 the user redirected to a diagnosis: which task qualities make an LLM's interruptions do worse than the plain VLA, rebuilt as a simplified environment. On Oct 9 the user added: test whether an agent knows (1) when to interrupt and (2) how much to observe, from a VLA's observed performance, with one agent and one context window supervising VLAs of different ability, with as little noise as possible.
4. **Real robot, Opus 5.5 vs plain GR00T N1.5** (stage 3, 37 same-machine confirmed pairs, 13 tasks, `docs/stage3_results.md`): Opus failed 14 of 34 usable episodes (41%); a second no-intervention run failed 1 of 36 (3%). Left alone: 5 of 19 failed, all by declaring 12-48 steps before the checker turned true. Rewrote the instruction: 9 of 14 failed. Wording vs restart is **not separated** (those arms were lost).
5. **Completion is hard to read:** visible-state tasks are recognized; rinse, scrub and microwave never are; the checker lags visual completion by about 20 steps (`docs/stage3_results.md`, offline probes).
6. **Abstract environment** (`src/robot_benchmark/sim/`, spec `docs/env_design.md`, one page `docs/env_building_blocks.md`, results `docs/sim_results.md`): the best supervision rule differs by VLA profile (steady, hesitant, brittle); adapting is worth 0.05-0.13 per episode. Opus learns **when** to restart a stalled brittle VLA from records (restart rate 0.00 / 1.00 / 0.75 with 0 / 3 / 8 past episodes), Sonnet does not; **neither** learns to look more often at the unreliable VLA, and in closed loop both are far from the best fixed rule on the brittle VLA (regret 0.34-0.55 vs 0.13). Rough reading: Opus there is about as good as no intervention, Sonnet worse.
7. **Biggest gap:** the brittle profile's stall rate and rescue probability are **assumptions**. No real data shows a restart ever rescuing GR00T; the real rewrite data points the other way. The sensitivity sweep covered only the restart dials. Do not state the brittle result as a property of GR00T.
8. **Money and compute:** no pod, no launchd watchdog. Prime team wallet $227.96 (it was $241.95 after the Oct 2 session). GPU overspent its cap (about $7.5 vs $5, 13.75 pod-hours) after the Mac slept; API about $11 of the $15 cap, of which the simulation study was $2.22 (`runs/sim/spend.jsonl`).
9. **Data (Git-ignored, only on this Mac):** `runs/stage2_remote` 2.0 GB, `runs/stage3_remote` 1.3 GB, `runs/probes`, `runs/sim` (calibration, probes, sessions, sensitivity, spend ledger). Disk is **99% full (7.8 GiB free)**: copy back selectively; the `frames/` folders of the stage 2 plain, defer and reissue arms (about 1.3 GB) are redundant if space is needed. Lost with the terminated pod: the stage 3 Sonnet, reissue, Opus-repeat, decision-replay, interruption-sweep and rescue arms.
10. **Next:** measure on the real robot whether a restart rescues or harms (A.5, item 1), then re-run the simulation with the call price varied. No GPU or API run is in flight.

### A.2 Superseded statements in the older text

- Sections 0 (items 4, 8-10) and 1 ("Branch"): the work is on `main`, not on `intervention-judgement-benchmark`.
- Sections 10-11 (open decisions, next steps): the full screening was not started; A.5 replaces it. Section 10 item 5 (branch handling) is settled.
- **Contract hash:** `adapters/robocasa.py` and `baselines.py` are hashed and changed on Oct 5 (frame-noise guard, start-state guard, `reissue_50/200/400`). Stage 1 episodes, and anything from before, are under a different hash: any future release needs fresh references.
- Section 9 lists only the Oct 2 pods. Stage 2 used a Lambda A10 and stage 3 a RunPod RTX A6000 (about $0.54/hr); see `docs/compute.md`, including the Oct 5-6 incident section.
- Section 12 doc drift is still true, and the README benchmark section ("Not yet GPU-verified") is stale.

### A.3 What was added since Oct 2

| Dates | What | Where |
|---|---|---|
| Oct 4-5 | Stage 2 harm run (Opus, always-defer, reissue); a validity audit found invalid pairs (different scenes, corrupted frames, end-of-budget declarations) and **withdrew the first conclusion** | `docs/stage2_results.md` (corrected) |
| Oct 5-6 | Guards: static-noise frame check, `--expect-state` start-state hash check; `replay` command, `ReplayAgent`, `reissue_*` baselines; stage 3 selection rules fixed before results | `docs/stage3_plan.md`, `docs/decisions.md` (Oct 5 rows), `scripts/select_stage3.py` |
| Oct 5-9 | Stage 3 on RunPod; probes of whether the model can tell the task is done | `docs/stage3_results.md`, `runs/probes/` |
| Oct 5-6 | Watchdog incident (Mac slept, pod ran 13.75 h, arms lost) | `docs/compute.md` |
| Oct 9 | Environment design by an Opus agent, then the abstract simulator, probes, sessions, sensitivity sweep | `docs/env_design_brief.md`, `docs/env_design.md`, `docs/sim_results.md`, `docs/decisions.md` (Oct 9 row) |

### A.4 What the evidence says to reproduce

| Quality | Evidence | Role |
|---|---|---|
| Hard-to-read completion plus a checker that lags about 20 steps | Real, strong | Early declarations are the largest measured failure with no intervention |
| VLA heterogeneity (plain success 0.17-1.00 by task, wide timing spread) | Real, strong | No single supervision rule fits every VLA |
| Any prompt restarts the policy | Real mechanism, harm size unseparated | Rewrites failed 9 of 14 |
| Stalls that a restart rescues | **Assumed** | The only profile where supervision adds much value (+0.38 over always-defer vs +0.09 steady and +0.005 hesitant) |

Recommended form: keep the abstract environment as the cheap testbed for agent design; for real tasks, cross completion legibility (visible vs hidden) with plain success (high vs low) rather than choosing by task family; score by regret against the best fixed rule for each VLA, not raw success. Conclusions are for these two models, one prompt and one cost ratio; two Opus sessions and one Sonnet session are too few to rank models.

### A.5 Next steps (none started; costs are estimates)

1. **Real rescue/harm measurement, about $2-4 of A6000 time.** Replay plain failures to a stall point on the same machine, then compare continuing, restarting with the same prompt, and restarting with new wording. The code exists and is tested (`replay` with ablations exact / native_text / no_interruption; `reissue_50/200/400`); only the data was lost. Plain reruns must be on the same pod, because start states are host-specific. Run short phases, copy results back after each, `caffeinate -dimsu`, arm the watchdog, verify termination yourself. If restarts never rescue GR00T, the brittle profile should go and the interrupt question reduces to when to declare and how to read completion.
2. **Simulation re-run, about $3 of API:** vary the call price (the cost constants are `CALL_COST` and `SECOND_COST` in `sim/harness.py`, and the `$0.02` text is hard-coded in `SYSTEM_PROMPT` in `sim/agent.py`, so change both) and whether the prompt says readings are noisy; 3-5 sessions per model. This tests whether "does not observe more often" is a pricing artifact.
3. Only after 1 and 2: choose the real task suite and run model comparisons. Before then, do not claim which model supervises better.

### A.6 Rules and lessons since Oct 2

- Never pair episodes without comparing the step-0 state hash. The scene seed does not always fix the scene (cause unknown), and start states differ between machines.
- Sim records are kind `sim_development`: never mix them with benchmark scores. Nothing from them is exposed to a real model adapter.
- Check model names and prices before spending. The design agent invented a "Haiku 5.5"; the study used Sonnet 5.5 (Opus 5.5 is $4/$20 per million tokens, Sonnet 5.5 $2/$10). The study API key is in the Git-ignored `.env` (mode 600); never print it.
- The user's Oct 9 instructions to work without asking questions and to use an Opus agent only for major design decisions applied to that run. Outside it, ask before new spending, per section 3.
- A paid pod must never depend on the Mac staying awake: the Oct 5-6 incident cost about $2.5 over cap and the data from six arms.
- Start with `docs/sim_results.md`, `docs/env_building_blocks.md`, `docs/stage3_results.md`, then `docs/decisions.md` from 2026-10-04 on.

---

## Oct 2 handoff (older; see A.2 for what is superseded)

Updated October 2, 2026, after the first GPU test of the new benchmark. The repository is the source of truth for code and contracts; this file records context, status, evidence, and what is still open. Statements are marked **verified** (observed on real hardware), **unit-tested only**, or **proposal**.

## 0. State in ten lines

1. **Project:** a benchmark of whether an LLM supervising a frozen robot policy (GR00T N1.5 in RoboCasa365) steps in only when needed. The LLM's only lever is re-prompting the policy; it never writes code or controls the arm.
2. **Direction (user-approved Oct 1-2):** "intervention judgement." Measure **harm** (LLM breaks a scene the plain policy solves alone) and **rescue** (LLM fixes a scene the plain policy fails), per scene, against a privileged plain-policy reference on the same scene and policy noise.
3. **Deadline:** October 16, 2026. Deliverable: a working eval someone else can run, plus results on at least two real systems (planned: Sonnet 5.5 and Opus 5.5) or two configurations of one system. It must be a **benchmark**, not a one-off study.
4. **Code:** all local implementation is done, reviewed and merged on branch `intervention-judgement-benchmark` (pushed, not merged to `main`, no PR). 199 unit tests pass.
5. **First GPU test (Oct 2) worked end to end:** all 16 candidate tasks build, the private predicates run cleanly, 32 plain-policy episodes and 9 Sonnet 5.5 episodes ran with zero infrastructure errors. See `docs/stage1_remote_results.md`.
6. **Result is a pipeline check, not a finding.** 8 Sonnet episodes, one policy seed: it solved 2 of the 4 scenes the plain policy solves and 0 of the 4 the plain policy fails. One unnecessary rewrite and one premature completion were observed.
7. **Not yet run on real data:** the retry and sequencer rescue diagnostics, the two baselines, `label-seeds`, `publish-cards`, `freeze-benchmark`, `run --release`, `scorecard`. Unit-tested only.
8. **Compute:** no pod is running. Team wallet was $241.95 after the session. Pods cost money while idle; see section 9.
9. **Next:** get the user's decisions in section 10, then the full screening (about 800 plain-policy episodes, roughly 16 hours and $9 on one A6000), then labels, cards, set B, freeze, baselines and models, scorecard, write-up.
10. **Nothing from this session's later changes is on `main`.** Do not merge or open a PR without the user asking.

## 1. Orientation

- **User:** Tom Wang. Repo: [tom05919/OrcaBench](https://github.com/tom05919/OrcaBench) (public). Project root: `/Users/tomwang/robot_benchmark`. Keep all work, caches, environments and outputs under it.
- **Branch:** `intervention-judgement-benchmark` (4 commits ahead of `main`, which is at `323bd52`). `git status` was clean when this was written apart from this file.
- **Verify the baseline first:**
  ```bash
  cd /Users/tomwang/robot_benchmark
  PYTHONPATH=src python3 -m unittest discover -s tests -v    # 199 tests, all pass
  ```
- **Read in this order:** [AGENTS.md](AGENTS.md) (binding project rules), this file, [docs/superpowers/specs/2026-10-01-intervention-judgement-design.md](docs/superpowers/specs/2026-10-01-intervention-judgement-design.md) (the design), [docs/decisions.md](docs/decisions.md) (every contract change and ruling, dated), [docs/protocol.md](docs/protocol.md) (benchmark section), [docs/stage1_remote_results.md](docs/stage1_remote_results.md), [docs/compute.md](docs/compute.md) (GPU runbook). Background: [docs/benchmark_direction_research.md](docs/benchmark_direction_research.md) (related-work review from before the direction was chosen), [docs/task_catalog.md](docs/task_catalog.md).

## 2. What the user wants

- The course assignment (evaluating and benchmarking AI agents): build an evaluation that targets a capability or failure mode current benchmarks measure poorly, with tasks that isolate it and automatic scoring; or audit an existing benchmark for vulnerabilities and fixes. **The user was explicit that it must be a benchmark** with a working eval someone else can run.
- Subject matter: an LLM orchestrating a VLA (learned manipulation policy) in physical tasks. The user knows many benchmarks already exist in this area, wants it **general and insightful, not niche**, and does not want a claim of novelty that the evidence does not support.
- Why this direction: published LLM-over-VLA evaluations mostly use tasks where the plain VLA already fails, so unnecessary intervention is never penalised. Embody (Anthropic) and the SEES/VoLo results suggest supervision can hurt. The gap is a released benchmark that scores both directions. This is a bounded finding from a literature search, not proof of uniqueness.
- The user chose the language-only intervention surface (re-prompting) deliberately: code-writing or direct control would measure a different skill and `AGENTS.md` forbids scripted manipulation.

## 3. How to work with this user

- Be critical and say so when something is weak, overlapping or infeasible. They rejected agreement-by-default and a narrow proposal.
- Prefer action on authorised, reversible work; ask only when information or authorisation is genuinely missing. But **ask before** spending money in a new way, downloading files they have not authorised, or committing/pushing/merging beyond what they asked. This session they explicitly asked twice to push; each push went to the feature branch.
- **Do not leave a paid pod idle waiting on a question.** On Oct 2 a question to the user sat for hours and a pod ran to its 5-hour watchdog deadline for nothing ($6.36). Ask first, or terminate and rebuild.
- They want to understand results: explain in plain language and use visuals when asked. Give numbers with their sample sizes and say plainly what a result does not show.
- Use parallel subagents when tasks touch disjoint files; keep quality over speed. This session used spec, then plan, then subagent-driven development with a reviewer per task and a final whole-branch review. The reviewers caught real bugs (diagnostic runs leaking into scores, policy seeds collapsing in `summarize`, a wasted-attempt rule); keep doing that for non-trivial work.
- Global rules in `~/.claude/CLAUDE.md` apply: surface assumptions, simplest solution, surgical changes, verify before claiming done.
- Never print or commit API keys, SSH keys or tokens. Store no secrets in docs, logs or chat.
- Limited local disk (about 19 GiB free on the Mac): do not download checkpoints locally; copy back JSON and replays selectively.

## 4. How the project got here

| When | What |
|---|---|
| Sep 25-26 | Foundation built: synchronous runner, two-operation interface (`run_policy`, `complete`), GR00T N1.5 via a loopback HTTP worker, RoboCasa `CerealAndBowl` as the first (unqualified) task. |
| Sep 27 | First GPU pass (RTX 6000 Ada). Three development episodes on `CerealAndBowl`, none successful (the plain policy and a privileged supervisor each ran out of steps; Opus 5.5 declared completion falsely). Old contract; not comparable with anything now. |
| Oct 1 | Research review of related work; the user rejected the first proposals as too narrow and asked for their own direction. Candidate directions were compared; "intervention judgement" was chosen. Other agent's "supervision-value suite" (snapshot branching) was judged too infrastructure-heavy for the deadline; it remains a possible later extension. |
| Oct 1 | Two harness fixes the user asked for: interval keyframes in observations, maximum interval 100 to 400 steps. Spec and implementation plan written; local implementation done by parallel agents with per-task review. |
| Oct 2 | Added field descriptions for proprioception in the prompt, proprioception on keyframes, both clocks reported. Pushed. First GPU test of the new benchmark (section 8). |

The legacy `CerealAndBowl` path (`feasibility`, `qualify`, `publish-policy-card`, `freeze-release`) still works but is CerealAndBowl-only and no longer the focus. The old contract is superseded; do not mix its episodes with new ones.

## 5. The benchmark as built

### 5.1 Interface (what the LLM can do)

One JSON object per model call:
- `{"op":"run_policy","prompt":"...","steps":N}`: **intervene.** The prompt replaces the active instruction, discards the policy's queued actions and resets the policy, even if the text is identical.
- `{"op":"run_policy","steps":N}`: **defer.** Continue the active instruction and queue.
- `{"op":"complete"}`: stop and be scored. The first advancing call must include a prompt.

`steps` is 1 to 400 control steps (20 Hz) and is also how often the LLM chooses to look. Physics is paused while the model thinks. Limits: 100 model calls, 4,096 output tokens per call, and a step budget equal to the task's RoboCasa365 registry horizon (asserted at start; 450 to 1,800 here). A reply that is not a valid decision still spends a call but advances no physics; the next observation carries the error. There is no retry. The step limit, not the call limit, ends failing runs (at most 14 of 100 calls were ever used).

### 5.2 What the LLM sees (observation schema 4, system prompt v5)

Goal = the task's native RoboCasa instruction, verbatim. Three current RGB views (256x256: two external, one wrist), five proprioception fields, up to four keyframes per camera sampled evenly from inside the interval just executed (each with the proprioception at its step), one public card (`{goal}` substituted at observation time, plus the plain policy's pooled success rate once published), the active instruction, budgets, the full decision history including rejected replies, and the last error. The system prompt (`SYSTEM_PROMPT` in `adapters/agents.py`) documents the operations and each proprioception field's frame, units, quaternion order (x, y, z, w), gripper range, and that a quaternion and its negation are the same orientation.

**Never exposed:** success, reward, simulator predicates, object coordinates, subtask labels or step prompts (`tasks.predicates.SEQUENCES`), seed group, reference outcomes. Do not change this.

### 5.3 Scoring

Success only if the agent declares `complete` and the official RoboCasa `_check_success` is true at that moment. A false declaration is a failure (`false_completion`); running out of budget is a failure even if the goal held at some point (`physical_success_any` is diagnostic). Infrastructure errors are retained and reported separately, never as agent failures. Every `result.json` records `simulated_seconds` (robot clock), `wall_seconds`, `model_seconds` (waiting for the agent) and `policy_seconds`; the scorecard reports total, mean and success-only mean for each.

### 5.4 Seeds and groups

- **Scene seed** = layout (`env.reset`). **Policy seed** = GR00T's sampling noise. An episode is `(task, scene_seed, policy_seed)`. Before this work the policy noise was seeded by the scene seed, so repeated runs were near-identical; this is changed and recorded in `docs/decisions.md`.
- `configs/splits.json`: scene seeds 1000-1019 (evaluation range), **set A** policy seeds 0-4 (screening and labels), **set B** policy seeds 5-9 (reference rates used for scoring, so seeds chosen for extreme set-A results are not re-scored on the same noise).
- Labels per `(task, scene)` from five set-A plain-policy runs (`screening.THRESHOLDS`): **leave_alone** if at least 4 succeed; **needs_help** if at most 1 succeeds *and* a privileged rescue supervisor succeeds in at least 2 of 5 (retry or sequencer; a retry success counts only if it actually re-prompted, at least 2 prompt submissions); **medium** otherwise; **pending** with fewer than 5 usable trials. A task qualifies with at least 2 of each; up to 4 of each are selected (lowest-numbered); at most 10 tasks (rank: min of the two selected counts, then total, then name). These thresholds are provisional engineering choices, not statistics.
- Systems run one policy seed per scene by default (seed 5); more set-B seeds pair the same way.

### 5.5 Conditions and scorecard

Reference (privileged plain policy, native instruction, stops on checker success; never a scored row), always-defer baseline, re-issue-every-100-steps baseline, and the LLMs. Scored systems: `llm`, `baseline_always_defer`, `baseline_reissue`. Excluded and counted: `llm_development`, all other `diagnostic_*`. Per system and group: success rate with Wilson interval; **harm** (reference minus system rate on leave_alone) and **rescue** (system minus reference on needs_help) with a seed-clustered bootstrap over paired `(task, scene)` clusters (unpaired clusters reported); false-completion and no-declaration rates; intervention profile (prompts, restarts, discarded actions, interval histogram); tokens; timing; offline failure attribution (false completion, missed completion, unnecessary intervention, missed intervention, executor/other); `reference_agreement` for always-defer as a GPU-nondeterminism check. No combined score by design.

### 5.6 Contract hash

One hash per run covers every config in `configs/tasks/`, the splits, the policy identity (**including the GPU name**), source revisions, the system prompt and hashed implementation files (`CONTRACT_FILES` in `cli.py`). The scorecard counts only episodes under the release's hash. Editing any pool config, the splits, a hashed module or the prompt after the set-B reference runs silently drops those episodes. `scorecard.py` and `screening.py` are not hashed; the release records their SHA under `analysis_sha256`. `--video-record-interval` is not hashed. Consequences: set-B reference, baselines and model runs must use the **same GPU type**, code, configs and splits; `publish-cards` changes the hash on purpose, so run it before set B.

## 6. Code and docs map

| Path | Purpose |
|---|---|
| `src/robot_benchmark/runner.py` | Synchronous physics, queue semantics, budgets, keyframes, timing, per-step private evaluation |
| `contracts.py` | Public sensor projection, decision validation, protocols |
| `adapters/robocasa.py` | Simulator adapter; generic official-checker scoring; calls the privileged predicates (failures isolated as `predicate_error`) |
| `adapters/agents.py` | System prompt v5; Anthropic and generic-HTTP adapters; API-visible traces |
| `adapters/policy.py`, `policy_worker.py` | Loopback HTTP client; isolated GR00T/pi0.5 worker (separate virtualenv) |
| `tasks/predicates.py` | `CANDIDATE_TASKS` (16), `SEQUENCES` (privileged step prompts, 6 composites), `task_predicates` |
| `diagnostics.py` | Privileged retry and sequencer supervisors (diagnostic only; every action still comes from the policy) |
| `baselines.py` | Public always-defer and re-issue agents |
| `feasibility.py` | Plain-policy reference supervisor (`OrdinaryPolicySupervisor`) and legacy CerealAndBowl diagnostics |
| `screening.py` | `label_seeds`, `native_card_performance`, `freeze_release` |
| `scorecard.py` | Harm and rescue, bootstrap, timing, failure attribution |
| `evaluation.py` | Legacy `summarize` (episode groups, paired comparisons keyed by scene and policy seed) |
| `records.py`, `video.py` | Append-only artifacts; MP4 encoding (supports sparse recording) |
| `cli.py` (about 820 lines, large) | Commands: `doctor`, `smoke-sim`, `screen`, `baseline`, `label-seeds`, `publish-cards`, `freeze-benchmark`, `run`, `scorecard`, `summarize`, plus legacy `feasibility`, `qualify`, `publish-policy-card`, `freeze-release` |
| `configs/tasks/*.json` | 16 pool tasks: native goal, horizon, one `native_instruction` card (step prompts are deliberately not here) |
| `scripts/` | `bootstrap_gpu.py`, `check_task_pool.py` (builds all pool tasks), `compare_to_reference.py` (joins model episodes to same-seed plain episodes), `setup_remote_worker.sh`, `setup_nvidia_gl.sh` (**untested**), `arm_prime_watchdog.py`, `prime_pod_watchdog.py`, `project_env.sh` |
| `docs/superpowers/` | Design spec and implementation plan; plan's scratch workspace (`.superpowers/`) was deleted |

Intended command sequence (screen, label, publish cards, set B, freeze, baselines and models, scorecard): README section "Intervention-judgement benchmark."

## 7. Verification status

| Component | Status |
|---|---|
| Bootstrap on a fresh worker, GR00T worker, `doctor`, build and horizon check of all 16 tasks, native instruction text, official checker, all six composite subgoal predicates (0 errors across 12 episodes) | **verified** (Oct 2, A6000) |
| `screen --mode reference` (32 episodes), `run --development` with Sonnet 5.5 (9 episodes), sparse and every-step video, keyframe proprioception reaching the model, both clocks | **verified** |
| Proprioception wording in the prompt (units, frames, quaternion order, gripper range) | **verified** against real readings (gripper about +/-0.0206 m at step 0; unit quaternions, x,y,z,w) |
| `screen --mode retry` and `--mode sequencer` | unit-tested only; never run on the simulator |
| `baseline` (both agents), `run --release`, `label-seeds`, `publish-cards`, `freeze-benchmark`, `scorecard` command, abandon-task/skip-existing logic under real failures | unit-tested only |
| Opus 5.5 under schema 4 / prompt v5 | never run (the Sep 27 Opus episode used the old contract) |
| `scripts/setup_nvidia_gl.sh` | written and syntax-checked; never executed on a pod that needed it |

## 8. Stage 1 results (Oct 2)

Full tables are in [docs/stage1_remote_results.md](docs/stage1_remote_results.md); raw data is in the Git-ignored `runs/stage1_remote/` on the user's Mac (41 episodes, 123 MP4s, 2.3 GB; `sonnet_vs_reference.json` and `summary_data.json` hold the joined data).

- **Plain policy (16 tasks x scenes 1000, 1001 x policy seed 0):** 14 of 32 solved. Solved on both scenes: CloseFridge, OpenCabinet, PickPlaceCounterToStove, TurnOnSinkFaucet. One scene only: CloseToasterOvenDoor, CoffeeSetupMug, KettleBoiling, PickPlaceCounterToCabinet, ScrubCuttingBoard, TurnOnMicrowave. Neither: LoadDishwasher, OpenDrawer, PrepareCoffee, RinseSinkBasin, TurnOffStove, WashLettuce. Single policy seed, so not labels.
- **Sonnet 5.5 (8 episodes at policy seed 0, paired with the plain episode on the same scene and noise):** plain solved and Sonnet solved 2 (CloseFridge, PickPlaceCounterToStove); plain solved and Sonnet failed 2 (KettleBoiling 1000, ScrubCuttingBoard 1000); plain failed and Sonnet solved 0; neither 4.
- **KettleBoiling 1000 (unnecessary intervention):** Sonnet left the original instruction running 400 steps, then replaced it with its own "turn the burner on" and kept rewriting; the policy never followed. The plain policy finished on the original wording at step 794. **ScrubCuttingBoard 1000 (premature completion):** rewrote the instruction at the start and declared done at step 300; the plain policy needed 680.
- On plain-failed scenes Sonnet re-sent or rewrote the instruction in 31 of 44 calls (70%), versus 8 of 28 (29%) where the plain policy succeeded. Its rewrites were long and procedural (about 18-32 words against 4-18 for the originals). Hypothesis, untested: GR00T was trained on short imperatives, so long rewrites are out of distribution.
- 12 replies were rejected (11 of 72 calls in the batch). All were the same error ("decision must be an object with an op"): 10 had prose before the JSON, 2 had a stray markdown fence after it; every one contained a valid decision.
- Real time was roughly 2.5-5x robot time (robot 10-75 s, real 52-210 s per episode); waiting on Sonnet was 10-34 s; about 35k input tokens per episode.
- Policy noise matters: the first Sonnet episode (OpenDrawer 1000, policy seed 5, prompt v4, sparse video) solved a scene the plain policy failed at seed 0, and Sonnet then failed it at seed 0.
- Stage-1 episodes are **development data**: different contract hashes in the same folders, no release frozen. Do not reuse them for labels or scoring; screen into a fresh output root (`label-seeds` raises on duplicates).

## 9. Compute

- **Rented so far:** Sep 27 RTX 6000 Ada ($0.93); Oct 2 Lambda A10 ($6.36, abandoned: image has no NVIDIA EGL and the question to the user outlived the 5-hour watchdog); Oct 2 RTX A6000 48 GB, Massed Compute, `ubuntu_22_cuda_12`, 6 vCPU, 48 GB RAM, 256 GB disk, $0.54/hr ($0.76). Team balance afterwards: $241.95. Anthropic usage for stage 1: about 300k input and 5k output tokens.
- **Instance choice logic:** the run is CPU-bound (Sep 27 breakdown of 382 s: simulation 181, video 139, policy 45), so pick the cheapest card with enough memory and a graphics-capable driver. Offers change; re-list before renting.
- **Prime CLI** (always `--plain`, set `PRIME_DISABLE_VERSION_CHECK=1`): the default context is the user's **personal account with $0**. The credit is in the team wallet (team "COS597"; get its ID from `prime teams list`). Use `PRIME_TEAM_ID=<id>` in the environment or `--team-id` per command; do not change the persistent CLI config. Useful: `prime availability list --no-group-similar --output json`; `prime pods create --id <short id> --name robot-cereal-<stamp> --image ubuntu_22_cuda_12 --team-id <id> --yes` (do not pass `--disk-size`; 200 was rejected for the A6000 offer); `prime pods status <pod> --output json`; `prime pods terminate <pod> --yes`; `prime pods history`; `prime wallet`.
- **Always arm the watchdog first:** `python3 scripts/arm_prime_watchdog.py --pod-name robot-cereal-<stamp> --team-id <id> --minutes <N>`, then add the pod ID to `runs/prime_watchdog/<name>/config.json`. After terminating, remove the launchd job (`launchctl bootout gui/$(id -u)/ai.codex.robot-benchmark.<name>`). Pod names must start with `robot-cereal-`. The guard needs the Mac awake and online; verify termination yourself.
- **Setup of a fresh worker (about 25-30 minutes):** package the working tree, copy it, run `scripts/setup_remote_worker.sh`, then `bootstrap_gpu.py --download-assets --download-checkpoint` (46 GB), then start the worker detached and run `doctor` and `check_task_pool.py`. Exact commands: [docs/compute.md](docs/compute.md), section "Intervention-judgement benchmark: worker setup." Source `scripts/project_env.sh` before starting the worker (it pins caches and EGL).
- **Throughput:** one episode stream at a time (the worker allows one); plain episodes about 72 s on average at video interval 10; LLM episodes 54-210 s at every-step video. Rough planning numbers, not measurements of the full plan: full set-A screening about 800 episodes (about 16 h, about $9); set-B reference up to 400 episodes (about 8 h); baselines and two LLMs on up to 80 scenes each (about 8 h); API cost depends on current pricing, check the Anthropic console.
- **API key:** the user's key is exported in their interactive zsh profile, not in the Bash tool's shell. Read it with `zsh -ic 'printf ... "$ANTHROPIC_API_KEY"'`, pipe it over SSH into a mode-600 `.env` in the pod's project root, and `set -a; source .env; set +a` before model runs. Never print it.
- **Parallelism:** you can rent several pods to cut calendar time, but they must be the **same GPU type** for anything that counts toward the release (the GPU name is in the hash), and each needs the full setup.

## 10. Open decisions (need the user)

1. **Approve the full screening and its budget** (about 16 h and $9 on one pod, or split across pods). Decide whether to trim the task pool first (for example drop tasks the mini-screen showed as clearly uninformative) to save time.
2. **Reply format:** keep strict parsing (current; 15% of Sonnet replies wasted a call but never changed physics) or accept a JSON object surrounded by prose/fences (changes the contract and the hash).
3. **Record a rejected-reply count in every `result.json`** (currently derivable only from `decisions.jsonl`). Small change; recommended.
4. **Second system:** confirm Opus 5.5 (config exists, `configs/model-opus-5-5.dev.json`) or another model, and the model identifiers to freeze.
5. **Branch handling:** the work is on a feature branch; the user has not asked for a PR or merge.
6. Whether to re-run the very first Sonnet episode at every-step video (it is sparse; a different-seed run at full rate exists).

## 11. Suggested next steps

1. Get the section 10 answers. Optionally make the README's benchmark section accurate first (it still says no command has produced a result; see section 12).
2. Run **one real episode each** of the unverified paths before scaling: `screen --mode retry` and `--mode sequencer` on a low-success scene (for example OpenDrawer 1000 and KettleBoiling 1001), and both baselines on one scene. Confirm they behave and are labelled correctly.
3. Full screening into a fresh output root: reference on all scenes with five set-A seeds, `label-seeds`, then retry and sequencer only on low-success scenes (`--scenes-from`), `label-seeds` again. Copy results back as you go (section 14).
4. `publish-cards`, then set-B reference for each qualified task's selected scenes, then `freeze-benchmark --reference-root` (needs a live worker). From then on **do not edit** hashed files, configs, splits or the prompt, and keep the GPU type.
5. Baselines, Sonnet 5.5, Opus 5.5 on the frozen scenes, then `scorecard`. Report harm and rescue with intervals, the unpaired counts, and the executor caveat.
6. Write-up and README. Rough calendar from the design: screening Oct 4-6, freeze Oct 7, runs Oct 8-12, write-up Oct 13-16.
7. If no task yields both leave-alone and needs-help scenes, fall back to the audit deliverable described in the spec (section 10 there) instead of inventing scores.

## 12. Known issues and risks

- **Sample sizes are small.** At most 4+4 scenes per task and at most 10 tasks, one policy seed per scene per system. Intervals will be wide; do not rank systems whose intervals overlap.
- **Labels depend on noise.** One plain run per scene says little; the five-seed set-A rule exists for this reason. The OpenDrawer example shows seed sensitivity.
- **Results are conditional on GR00T N1.5 and these tasks.** Say so in every claim. The user asked earlier whether this executor is the best; it is the official RoboCasa365 multitask checkpoint, chosen for compatibility, not proven globally best.
- **Doc drift:** the README benchmark section still says "Not yet GPU-verified ... none of these commands has produced a result"; `docs/feasibility.md` and `docs/policy_card.md` describe the old CerealAndBowl pass. `docs/protocol.md` and `docs/decisions.md` are current.
- **`cli.py` is about 820 lines** and holds evaluation-relevant wiring (`SCREEN_MODES`, `BASELINES`, grid logic) that is not in `CONTRACT_FILES`. Consider moving it if it grows; changing it does not change the hash.
- **Smaller deferred items** (from reviews): `label-seeds` does not filter or record contract hashes; `freeze-benchmark` checks the set-B hash but warns nothing earlier; truncated JSONL lines in some readers still raise; unknown non-diagnostic episode kinds are dropped without a counter in the scorecard; `run --development` shares the release hash (its episodes are never scored but sit beside real ones if put in the same root); the grid builds each agent without an environment to read its model name; `summarize` is legacy.
- **Predicates read private upstream attributes** (for example washed-time and burner state). They ran clean on 12 composite episodes, but their sequencer use (rescue evidence) has never been exercised.
- **Three composite checkers enforce less than their instructions say** (RinseSinkBasin, LoadDishwasher, PrepareCoffee; see `docs/task_catalog.md`). ScrubCuttingBoard's sequence is two steps, not the source's three, because the checker has no grasp conjunct.

## 13. Tooling gotchas (all hit this session)

- macOS `tar` adds `._*` files that break the task-config glob on the pod (`UnicodeDecodeError`). Package with `COPYFILE_DISABLE=1 tar ... -T -` from `git ls-files -co --exclude-standard`, or use `git archive`.
- `ssh host 'cmd &'` hangs the session. Start detached work with `setsid -f cmd > log 2>&1 < /dev/null`, or run the whole ssh in a background task and poll.
- The Mac `rsync` (openrsync) rejects `--info`; use plain `-a`. `timeout` does not exist on macOS. In zsh an unquoted `$VAR` holding a command line is not word-split; use a wrapper script.
- Quote carefully when running Python over SSH heredocs; write the script to a file and copy it instead.
- Images differ by provider: Massed Compute's `ubuntu_22_cuda_12` ships NVIDIA EGL; Lambda's does not (headless MuJoCo fails with `EGL_BAD_DISPLAY`, and packaged graphics libraries did not match the running driver).
- The Bash tool's shell lacks the API key and the `zsh` interactive profile; the `Monitor` tool caps at 30 minutes and must be re-armed.

## 14. Data and git

- In git: code, configs, docs, tests, the spec and plan, `docs/stage1_remote_results.md`. Git-ignored and **not** in the repo: `runs/` (including `runs/stage1_remote/`, `runs/prime_*` from Sep 27), `vendor/`, `assets/`, `checkpoints/`, environments, caches, `.env`.
- Pods and their disks are destroyed on termination. Before terminating, copy results back (JSON/JSONL always; frames and replays as disk allows) and compare file counts and byte sizes with the pod. On Oct 2 all 32,512 files matched before termination.
- Commits: only when the user asks. End commit messages with the attribution line the harness provides.

## 15. Non-negotiable project rules (from AGENTS.md)

All work under the project root. No artificial disturbances, scripted manipulation replacing the policy, or training. A diagnostic hand-authored supervisor may read simulator predicates, but its results are never mixed with model scores. Never expose reward, task success, object coordinates, subtask annotations, evaluator artifacts or corrective advice to a model adapter. Unknown skill performance is null or "untested", never zero. Source inspection and mock tests do not qualify an actual robot policy. Preserve every attempted episode, including failures and infrastructure errors. Run `python -m unittest discover -s tests -v` after runner changes. Keep compatibility fixes surgical and record changes to the evaluation contract in `docs/decisions.md`.
