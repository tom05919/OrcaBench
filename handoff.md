# OrcaBench handoff

Updated October 1, 2026. This document consolidates the important project context, user preferences, discussion history, implemented contracts, experiment evidence, and unapproved proposals from the conversation. Read it before continuing work. Repository files are the source of truth for implementation; research suggestions below are not user-approved changes unless explicitly labeled.

## 1. Immediate orientation

- **User:** Tom Wang. GitHub: [tom05919/OrcaBench](https://github.com/tom05919/OrcaBench).
- **Authoritative project root:** `/Users/tomwang/robot_benchmark`. Keep source, documents, environments, caches, assets, checkpoints, and outputs under this dedicated root. The Codex task may start in `/Users/tomwang/Documents/ChatGPT/Robot_Benchmark`; set tool working directories explicitly. Do not accidentally continue implementation in the older workspace or inherit its environment pins.
- **Project:** evaluate LLMs as execution-time supervisors of fixed learned robot policies, initially in MuJoCo + robosuite + RoboCasa.
- **Course deadline:** October 16, 2026. Deliverable: runnable automatic evaluation plus results on at least two real systems or two configurations of one system.
- **Actual status:** work-in-progress harness, one unqualified task, three live development episodes, no qualified policy library, no controlled model comparison, no validated benchmark release.
- **Most recent discussion:** the user rejected an overly narrow benchmark proposal and requested extensive research with subagents to find a defensible contribution. That review is complete. It recommends a controlled supervision-value suite as a candidate, but the user has **not accepted that pivot**. Their latest request was to write this handoff.
- **Last known compute state:** the September 27 Prime Intellect pod was terminated after copying artifacts. No new GPU run occurred during the October 1 research or this handoff. This document does not verify current provider state; check the account read-only before assuming there are no active pods.

Read first: [AGENTS.md](AGENTS.md), [README.md](README.md), [protocol](docs/protocol.md), [feasibility evidence](docs/feasibility.md), and [latest direction review](docs/benchmark_direction_research.md).

## 2. What the user is trying to accomplish

The course assignment is **evaluating and benchmarking AI agents**, not inventing a new robotics method. It permits either:

1. identifying a capability/failure mode poorly measured by existing benchmarks, designing isolating tasks, and automatically scoring them; or
2. inspecting/modifying an existing benchmark, identifying vulnerabilities, and evaluating fixes.

The evaluation must work for another person and contain results for two real systems or configurations. A benchmark-validity audit can satisfy the assignment; an orchestration framework by itself cannot. The October deliverable can be a pilot, but its claims must match its scale and qualification evidence.

The original interest is medium-to-long-horizon household manipulation involving dependent skills. The LLM interprets the goal and plans, but the main interest is what it decides **during execution**: monitor progress, continue, redirect, retry, recover, choose observation timing, and declare completion. Low-level learned policies stay fixed across model comparisons. Supply policy descriptions and honest predeployment performance evidence.

The user later became interested in robots asking a simulated human for directions/preferences/instructions, inspired by tau2-bench. The human does **not** physically help perform the chore. That was a direction under exploration, not a replacement of all established contracts.

## 3. Working preferences and instructions

- Be critical. The user explicitly objected to repeated agreement and wants shortcomings, overlap, and feasibility risks addressed candidly.
- Research recent primary sources. The user challenged comparisons relying only on old papers and asked what actually powered each agent: LLM/VLM, VLA, hierarchical VLA, oracle/scripted skill, planner, etc.
- Do not claim novelty simply because a robot is added to a digital-agent benchmark, because tasks are longer, or because a framework combines components.
- When explaining settled harness choices, answer concisely and describe decisions already made. The user specifically asked not to substitute a list of remaining decisions for that answer.
- Prefer action and persistence on authorized work. Do not repeatedly stop for confirmation on routine implementation, read-only research, or reversible local work. Ask only when material information or authorization is actually missing.
- Use subagents when useful and authorized. The user explicitly requested them for research and prefers **GPT-5.6 Sol with extra-high (`xhigh`) reasoning** when possible. The October 1 review used three such agents: landscape survey, candidate design, and red team. Do not rely on their ephemeral context; their synthesis is in the research memo.
- Keep changes surgical and simple; follow the user's global coding instructions and repository AGENTS.md. Read relevant files before coding, identify verifiable outcomes, and do not refactor unrelated work.
- The user has limited local storage: do not download VLA checkpoints/assets to the Mac as part of a casual experiment. GPU models and authoritative policy evaluation belong on a remote Linux GPU worker.
- Do not expose API keys, SSH private keys, or credential headers in documents, logs, Git, or chat. This handoff intentionally contains no secrets.

## 4. Conversation trajectory and what was actually accepted

| Stage | User concern or request | Result/status |
|---|---|---|
| Initial foundation | Build an automatically scored benchmark of LLM robot-policy orchestration; use a dedicated folder. | The detailed implementation plan was explicitly approved. Root is `/Users/tomwang/robot_benchmark`; initial stack and CerealAndBowl feasibility candidate were implemented. |
| Action-interface discussion | Start/continue/interrupt/switch/retry categories might restrict useful orchestration. The robot should expose a policy API the LLM can prompt freely. | **Accepted and implemented:** two operations, `run_policy(prompt?, steps)` and `complete`. The old six-operation interface is superseded. |
| Compute setup | Investigate Prime Intellect APIs, GPU cost/performance, and credentials; initially do not purchase. | CLI/API integration and remote bootstrap tooling were prepared. The user reported $250 credit; this is not a currently verified balance or an unlimited spending authorization. |
| VLA selection | Find best-performing open models by actual benchmark performance and pretraining scale, rather than popularity. | Preserve this selection criterion. The implemented official GR00T N1.5 candidate is the original compatibility/feasibility choice, not a proven globally best VLA. Reassess rankings with current evidence before changing it. |
| Task difficulty | If raw VLAs already solve these tasks, are we really testing long-horizon orchestration? | Longer duration alone is insufficient. Need evidence that supervisory choices affect outcomes, rather than assuming a composite task establishes an orchestration test. |
| First live experiment | First reproduce ordinary execution and the hand-authored supervisor; if these finish within two hours, run the full LLM through the harness. | **Authorized and performed** September 27. All three runs were unqualified development episodes. |
| Recordings/traces | Save every camera video, robot and external views, per-step/total timings, and all LLM traces; use Opus 5.5. | Three camera streams, timing records, and all API-visible Opus traces were retained. User accepted API-visible thinking summaries/signatures/outputs; raw hidden reasoning is unavailable. |
| Usage-limit concern | Ensure GPUs terminate even if this agent hits its session limit; asked about resuming at 2:57 AM. | An independent local launchd termination guard was implemented and verified for the first run. No reliable current restart/resume automation is established by this handoff. Do not depend on an LLM turn to clean up paid compute. |
| GitHub | Upload current work with a README; emphasize work in progress. | Initial repository publication completed. Latest local research/task-outline files are untracked and were not part of that publication. |
| Harness/scoring | Spend more time on the harness; consider step-by-step success and a final score combining steps, full success, and time. | Automatic terminal scoring exists; intermediate predicate events are recorded. A new stepwise scoring scheme or weighted final formula was **not adopted**. Keep progress, terminal success, and cost separate until a defensible contract is chosen. |
| Task catalog | List longer multi-step RoboCasa tasks, sorted by published steps. | Survey saved in `docs/long_horizon_tasks.md` and CSV. Published subtasks are not guaranteed distinct policy skills or an orchestration-difficulty measure. |
| Environment design | Existing RoboCasa versus custom environments/tasks using its objects? | Existing simulator/checkers provide a foundation. Custom tasks remain possible but require asset, physics, checker, and policy qualification; no custom task is implemented. |
| Broader chores | Link multiple household tasks with ongoing human preferences. | Explored, then challenged by the user as potentially just context/memory management plus a robot layer. Do not treat this brainstorm as accepted scope. |
| Human clarification | Clarify that the robot asks the human for preferences/directions, rather than receiving physical help. | Accepted clarification of the proposed human role. A user simulator should supply information only. |
| First human-interaction task | Work together on one task and the LLM-as-human structure. | User selected **breakfast setup as an easier first task**, with eventual tasks varying in difficulty. The detailed outline remains a draft. |
| Latest novelty challenge | Earlier suggestions were too narrow; perform extensive research and brainstorming with subagents. | Review found direct precedents for many proposed capabilities. Assistant recommended a controlled supervision-value suite plus two alternatives. **No pivot has been approved or implemented.** |

The earlier proposal PDF was explicitly background, not a binding specification. Do not assume its contents are available or that it governs current choices.

## 5. Current harness contract: implemented

### Policy API and timing

The agent emits exactly one JSON operation per model call:

```json
{"op":"run_policy","prompt":"Pick the bowl and place it on the counter.","steps":50}
```

```json
{"op":"run_policy","steps":50}
```

```json
{"op":"complete"}
```

- The first advancing call needs a prompt. A supplied prompt is nonblank, at most 512 characters, and forwarded verbatim.
- Supplying **any** prompt, even unchanged text, replaces the active instruction, clears queued actions, and invokes the policy reset hook before advancing.
- Omitting the prompt preserves the active instruction and unexecuted actions.
- The reset hook does not reset the physical episode or the episode RNG stream. The pinned backends have no recurrent instruction state, but implementation caches still matter for reproduction.
- The LLM chooses 1–100 control steps before its next observation, subject to remaining budget.
- Physics pauses during model inference. This is a synchronous capability evaluation, not a real-time reaction benchmark.
- The VLA's internal chunk horizon is separate from the LLM observation interval. The runner requests a chunk when the action queue becomes empty and executes learned actions without interpolation or scripted replacements.
- There is no standalone interrupt operation: physics is paused at decision boundaries. A new prompt cancels queued actions there.
- No agent reset/restore, raw joint-control tool, code sandbox, or filesystem access is exposed by the implemented model adapter.

### Prompt and model adapter

The actual shared system prompt is `SYSTEM_PROMPT` in [agents.py](src/robot_benchmark/adapters/agents.py), prompt version 2. It tells the model to supervise a language-conditioned learned policy, derive progress from observations, treat reference prompts as examples rather than an allowlist, and return only one operation JSON. It explains pause behavior, prompt-versus-continuation semantics, budgets, and completion.

This file is authoritative; do not silently replace it with a new scaffold for one model. The user-facing task goal is:

> Move the cereal box and the bowl from the cabinet onto the adjacent counter, and leave the cabinet closed. Declare completion when both objects are on the counter and the cabinet is closed.

Adapters currently support `anthropic` and `json_http`. The generic HTTP adapter expects an endpoint implementing the documented request/decision shape; it is not a ready-made adapter for every model provider. Anthropic sends one user message containing current images and serialized public observation/history, with the common system prompt. Current Anthropic settings are adaptive summarized thinking and medium output effort, with 4,096 maximum output tokens and a 120-second request timeout. The development config's exact model identifier is `claude-opus-5-5`; that is a recorded experimental choice, not a recommendation that availability/pricing remains unchanged.

### Observation and image formatting

Public observation schema version 2 contains goal, RGB images, proprioception, reference-prompt performance cards, active instruction, steps/decisions remaining, maximum interval, decision history including rejected outputs, and the latest schema error.

- Current frames only; previous visual frames are not automatically included. Public decision history is retained.
- Each RGB view is 256 x 256 in the development task config.
- Images are PNG data URLs internally: `data:image/png;base64,...`.
- Anthropic serialization sends each camera's name followed by its base64 PNG image block, then a text JSON block containing non-image observation fields. They are separate camera images, not an unlabeled montage or video input.
- Cameras: `video.robot0_agentview_left`, `video.robot0_agentview_right`, `video.robot0_eye_in_hand`.
- Proprio fields: relative end-effector position (3), relative rotation quaternion (4), gripper qpos (2), base position (3), base rotation (4).
- Object coordinates, reward, success flags, simulator predicates, subtask annotations, evaluator artifacts, and corrective advice are excluded by the public sensor projection.

The recorded camera set includes two external robot agent views and the wrist view. Do not imply a separate fourth spectator camera was recorded. The user wants robot-camera and third-person visibility; verify representative views meet that practical requirement.

### Budgets, completion, malformed output

Development defaults: 4,350 physical control steps, 100 model calls/decisions, 1–100 steps per advancing decision, 4,096 output tokens per model call. Reserve budget for a completion decision.

A malformed or state-invalid response consumes a model call, advances no physics, and makes a schema error visible on the next call. Requests exceeding remaining steps are invalid. No free repair call is made.

Primary success is binary: the agent declares `complete` before budget exhaustion and the physical goal holds at that declaration. False completion ends the episode unsuccessfully. A physically complete state without declaration is unsuccessful for the primary score; ever-seen and final physical success are diagnostic metrics. Infrastructure errors are retained separately from agent failures.

## 6. Task, policies, feasibility gates, and dependency state

### CerealAndBowl scorer

The pinned RoboCasa `_check_success` is:

```text
contact(cereal, designated counter)
AND contact(bowl, designated counter)
AND cabinet.is_closed
```

The upstream language says next to the milk, but the checker does not enforce that. The benchmark instruction omits it. It also does not require gripper release or sustained stable placement. Do not silently add these conditions or score an unsupported milk relation.

`RoboCasaEnvironment.evaluate()` is currently specific to this task. The generic runner does **not** imply generic multi-task scoring is implemented. Opening the cabinet is a diagnostic entry predicate, not a separate terminal-goal conjunct. The cabinet begins closed, so a future stepwise score must not award meaningful completion credit for initial closure.

### Frozen learned-policy candidates

Official Hugging Face checkpoint repository: `robocasa/robocasa365_checkpoints`, revision `c484448aba1a9b60a04c9b0ca117241518ea69f3`.

- First candidate: GR00T N1.5, `gr00t_n1-5/multitask_learning/checkpoint-120000`.
- Predefined fallback: pi0.5, `pi05_pretrain_human300/multitask_learning/75000`; prepared in tooling but **not tested**.
- Four exact qualification prompts: open cabinet; transfer cereal; transfer bowl; close cabinet. They are probes with performance cards, not allowed-command restrictions. Arbitrary dynamic prompts remain permitted but unqualified.
- Do not switch models per episode, train policies, or substitute hand-coded manipulation when a prompt fails.

Source locks in [sources.lock.json](configs/sources.lock.json):

| Source | Revision |
|---|---|
| RoboCasa | `456174f62b89b8fca99eaaf33949c29fec9cfc2a` |
| robosuite | `5ce6643f3092639d08f7b0f90ed1c6a84f50552c` |
| Isaac-GR00T fork | `9d7d7a9eb7ad30bd8ce30448d9ab53a918b45b10` |
| openpi fork | `5a6beda9ff99da30b4e1b59320f6a32971d7c397` |

### Dependency environments

Simulator coordinator and learned policy run in separate environments connected by a loopback HTTP worker. RoboCasa requires Tianshou 0.4.10; GR00T requires 0.5.1. Keep this isolation.

Simulator direct pins include MuJoCo 3.3.1, NumPy 2.2.5, and Numba 0.61.2. GR00T includes Torch 2.5.1, Transformers 4.51.3, NumPy 1.26.4, and the official flash-attention 2.7.4.post1 wheel for Linux x86_64 / Python 3.11 / Torch 2.5 / CUDA 12 / ABI=false. That wheel repaired an actual EAGLE2 model-load failure.

Some upstream requirements remain unpinned until installation; bootstrap records concrete resolution snapshots. Do not claim every transitive dependency is fully locked merely because source revisions and direct requirements exist. A clean rebuild has not yet been verified.

### Qualification: all pending

- Each of four exact prompts must pass nominal and naturally encountered intermediate entry conditions: eight rows, each at least 8/10 valid trials.
- Diagnostic hand-authored supervisor: at least 16/20 valid full-task successes.
- Matched natural continuations must establish that supervision can affect physical outcome or resource use.
- These are provisional engineering screening rules, not statistical proof of robust skills. Report Wilson intervals and limitations.
- Missing/unrun or infrastructure-incomplete trials are pending, not successes or failures. A target trial starts only after its required entry condition exists; prefix failure is not a failed target attempt.
- Diagnostic supervisor can read simulator truth; LLM benchmark agents cannot. Their scores must never be mixed.
- pi0.5 fallback begins after a **completed** GR00T gate failure or a documented incompatibility that cannot be fixed without changing the contract. Three incomplete development experiments do not constitute that gate.
- Official release freezing and runs are guarded by qualification/checkpoint/contract/evidence validation.

Candidate splits: development 0–19, qualification 100–119, evaluation 1000–1019. They are disjoint seeds within the pretrain scene/object split, not unseen-task/scene generalization. Config status is `candidate_not_frozen`.

## 7. Actual live experiments: September 27, 2026

The temporary Prime worker used one RTX 6000 Ada 48 GB, 12 vCPUs, 72 GB RAM, 350 GB disk, region `us-central-3`. It was terminated after approximately 76 minutes. Recorded compute charge: $0.93. Last verified artifact root: `runs/prime_20260927_1454/` (Git-ignored).

| Episode | Seed | Result | Steps | Wall time | Interpretation |
|---|---:|---|---:|---:|---|
| Ordinary whole-task GR00T | 0 | Step budget exhausted | 4,350 | 382.2 s | Cereal and bowl eventually contacted counter; cabinet was not closed. |
| Privileged diagnostic supervisor | 100 | Step budget exhausted | 4,350 | 456.6 s | Only open-cabinet prompt ran because cabinet_open never became true. |
| Opus 5.5 through public harness | 1 | False completion | 3,640 | 763.7 s | Objects contacted counter; cabinet remained neither fully open nor closed when completion was declared. |

These seeds are unpaired. Do not interpret differences as model effects, publish 0/3 as a qualified success rate, or conclude GR00T cannot perform every possible task.

Opus made 47 calls, eight malformed. It submitted 23 prompts, changed prompt 17 times, restarted the same prompt five times, and discarded 200 queued actions. There are 47 full API-visible request/response traces, 45 with thinking-summary blocks. This is evidence that the real LLM/harness integration ran, not that the task is qualified.

Each episode has three 20 fps MP4s and per-control-step PNGs including step zero, plus action, policy, model, evaluator, and timing records. `verification.json` checks counts, metadata, hashes, and implementation agreement. Video duration reflects simulation playback; it is not total wall time. Ordinary/supervisor videos have 4,351 frames per camera; Opus has 3,641. Nine videos total.

The first supervisor rule is problematic: it waits for cabinet_open before attempting a transfer, yet other runs transferred objects without that predicate becoming true. Before counted trials, inspect natural cabinet states and predeclare a finite opening-prefix/transfer rule. Then test closing from naturally reached both-on-counter states. Do not teleport objects to manufacture these conditions.

A reproduction issue remains: the worker was started without first sourcing `scripts/project_env.sh`, so a transient Transformers dynamic-module cache went under the pod user's home. The temporary pod was deleted. Future runs must source the project cache environment before worker startup; clean reproduction is not yet verified.

Useful artifact locations:

- `runs/prime_20260927_1454/verification.json`
- `runs/prime_20260927_1454/remote_runs/feasibility/groot-ordinary-1/seed-0-20260927T153606.916983Z/`
- `runs/prime_20260927_1454/remote_runs/feasibility/groot-supervisor-1/seed-100-20260927T154307.001674Z/`
- `runs/prime_20260927_1454/remote_runs/models/opus-5-5-development-1/seed-1-20260927T155517.159450Z/`

## 8. Compute authorization, safeguards, and credentials

The user first prohibited purchases while asking to verify configuration, then explicitly authorized the limited first experiment. That authorization has already been used. Do not interpret historical approval or reported credit as open-ended permission for repeated rentals.

User's timing clarification was: **start the LLM test if the earlier tests finish within two hours**. They also requested that rented GPUs not remain running if the Codex session reaches its usage limit. The first run used an independently verified two-hour guard and finished earlier. For a new paid experiment, establish its budget and cleanup before launch; do not assume a previous deadline or pod remains relevant.

Tooling:

- `scripts/arm_prime_watchdog.py`: arms a local macOS launchd guard before renting a pod; exact pod-name prefix `robot-cereal-`, team, deadline, and optionally bound pod ID.
- `scripts/prime_pod_watchdog.py`: lists/status-checks the intended pod and requests termination after deadline; validates identity/team.
- `scripts/prime_artifact_sync.py`: copies append-only remote run records back locally.
- The local guard survives a Codex turn/app interruption but still depends on the Mac being awake and online. Closing the lid/network loss can delay it. It is **not** a provider-enforced prepaid two-hour lease. Verify actual termination afterward.
- Prefer independent provider-side termination if the current API supports it, but verify documentation rather than claiming it exists. Never launch compute whose cleanup depends solely on this conversation continuing.

Prime CLI configuration and Anthropic credentials were configured for the earlier run. Never print the configured keys. Model config refers to environment variable `ANTHROPIC_API_KEY`; use a secure environment or ignored credential file, not a committed JSON value. Reverify availability without exposing credentials. Current credit balance, instance prices, GPU availability, and API behavior are time-sensitive and should be checked before another rental.

Remote storage: GR00T inference checkpoint about 7.1 GiB; RoboCasa assets about 10 GB; allocate at least 80 GiB free including environments/caches. pi0.5 adds roughly 11.6 GiB and its environment. Download inference parameters only, not optimizer/training state.

## 9. Human-interaction direction: selected task versus draft design

The user selected **personalized breakfast setup** as the first easier task in a future varied-difficulty suite. [first_interactive_task_outline.md](docs/first_interactive_task_outline.md) is a draft; no ask_human tool or custom breakfast environment exists.

Proposed pilot:

- Two distinguishable breakfast-food boxes and two distinguishable bowls, with an initially underspecified request to set out breakfast.
- Private, fixed profile chooses one food and one bowl; four matched preference profiles share physical states and counterbalanced object locations.
- Agent may ask broad/compound questions and may guess. Do not impose an exact conversation or artificially require multiple narrow questions.
- Transfer selected items, leave unselected items in storage, close cabinet, then declare completion. Either transfer order can be valid.
- Stock CerealAndBowl has only one box and one bowl. Extra objects, asset descriptors, clutter, reachability, scorer, and policy feasibility require real implementation and qualification.

Proposed human simulator:

- Information-only household user, not a co-manipulator.
- Receives public request, finite private preference/fact profile, known object-description catalog, unknown-information list, and dialogue history.
- No simulator predicates, reward, object coordinates, policy queues, execution diagnostics, or live camera feed in the first draft.
- Responds briefly and cooperatively, answers broad questions fully, corrects preference misunderstandings, and says unknown when appropriate.
- Does not certify completion, invent physical procedures, reveal internal profile IDs, or change preferences retrospectively.
- The profile is truth; an LLM renders the reply. LLM user behavior needs audited probes; its mistakes are simulator/infrastructure faults, not silently blamed on the evaluated agent.
- A draft system prompt is in the outline. User-model identifier, temperature/settings, answer limits, and dialogue auditing are not frozen.

Proposed third operation: `ask_human(question)`, zero physical steps, preserves queue, consumes an ordinary decision. An eight-exchange cap is a suggestion, not an adopted requirement. Proposed controls: fully specified initial request, interactive underspecified request, no-dialogue guessing. Success need not require asking. No weighted score is fixed.

This is an information-only adaptation inspired by tau2-bench; do not claim it reproduces tau2's dual-control setup. The latest research substantially weakens the novelty of clarification itself.

## 10. Latest research and proposed direction: not adopted

[benchmark_direction_research.md](docs/benchmark_direction_research.md) contains a recent primary-source comparison, three candidate designs, rejected headlines, feasibility gates, and causal-validity review. It supersedes the initial four-paper comparison as a guide to current novelty assessment, but does not supersede the implemented protocol.

Key conclusions from the review:

- Embody already compares LLM supervisors over MolmoAct.
- What Matters in Orchestrating Robot Policies compares hierarchical components, models, timing, observations, and memory.
- VoLo compares VLMs and measures monitoring/recovery using learned policies plus extra manipulation/perception tools.
- ReSteer, SwitchVLA, and CoRe/LangSwitch cover intermediate-state steering, multiple switching stages, rollback, and preserving progress. Frozen VLA plus task changes is not an uncovered capability.
- Ask-to-Act, Ask-to-Clarify, Hi Robot, and PARTNR/dialogue extensions cover important human-interaction neighbors; identify their actual motor abstraction before making comparisons.
- WorldLines, AppWorld-UL, AgentChangeBench, and ATRBench weaken novelty claims based on persistent chores, updated goals, preference memory, and asking for missing information.
- FailBench measures recorded success/failure but not the causal physical outcome of a chosen supervisory intervention.
- LIBERO-MAX and ConflictVLA-Bench already use matched process/continuation controls; paired testing is not itself new.
- PACE shows chunk execution horizon alone can alter outcomes. CheckVLA studies execution verification/replanning.
- ManiGuard and SafeVLA-Bench already score trajectory constraints/safety. Current SafeVLA includes threshold sensitivity and duration/exposure; do not call those missing.

Primary links and more exact architectures are in the memo. These are recorded research findings with a bounded scope, not a certificate of novelty or current leaderboard recommendations. Refresh sources before a public claim; inspect full protocols and artifacts. The older EAI, EmbodiedBench, RoboBench, and REFLECT comparison is in `docs/research.md`. Do not characterize EAI as offline-only: it includes interactive replanning. REFLECT is a method, and RoboBench's planning evaluator differs from fixed-policy physical execution.

### Recommended candidate from the assistant

**Controlled supervision-value suite:** measure when LLM execution-time decisions help or harm a frozen learned policy after separating instruction content, policy requery, queued-action treatment, and orchestrator context.

Possible breadth: at least three task families (retrieval/placement, articulated storage, multi-object arrangement/cleanup), several execution stages, productive motion, natural failures, no-progress states, dependent-task transitions, apparent completion, and harmful unnecessary continuation. Suggested 36-checkpoint pilot is provisional, not a power calculation. Keep free-form prompting; evaluator strata are not forced agent action classes.

Controls from identical snapshots could compare queued continuation, same-prompt requery, fixed old-goal paraphrase, revised prompt, and fixed revised-goal paraphrase. Compare live versus clean-context supervisors separately. Score paired physical success/progress, harmful interventions, recovery, false completion, and resource use. Complete-episode controls are also required for overall supervisor-value claims.

Critical review constraints:

1. Checkpoint selection must be frozen from independent development rollouts, never chosen because an evaluated system or its reference branch failed.
2. Restore simulator/controller state **and** policy RNG/caches, action queue, prompt, history, and counters. Replaying recorded actions only reproduces physics, not policy runtime. If worker restoration is unavailable, validated original-policy-call replay or identically reset clean-context branches are alternatives with narrower claims.
3. Identical-prompt twin branches must agree within declared tolerances before causal comparisons. Seed equality alone is insufficient.
4. At a fixed query boundary, keep reset/queue treatment, observations, horizon, and query schedule equal when comparing semantic content.
5. When requery itself is the treatment, realized query counts differ intentionally. Match resource allowances, report actual use, and do not pretend compute is identical. Effects can interact; do not add simple contrasts as a complete decomposition.
6. Frozen-boundary contrasts measure decision-level effects, not the total effect of a supervisor that chooses its own intervention timing. Use complete-policy comparisons for the latter.
7. Clean-context agents receive only public sensors, active goals/prompts, sensor-history window, and budgets. Physical/policy snapshots, queue contents, evaluator truth, and reachability labels stay private. An agent-generated summary may use public observations only.
8. Report unconditional outcomes, plus independently qualified feasibility strata. Do not discard evaluated failures after seeing a failed reference branch.
9. Comparisons against a finite set of tested alternatives are not regret against a globally optimal controller. Do not normalize by a zero/tiny estimated policy ceiling or invent final metric weights.

This is a **candidate evaluation-protocol contribution**, not a claim that monitoring/recovery/steering is new. Research has not established that the complete proposed controls are unique or consequential. If they add no distinction, describe a replication/extension. A rigorous demonstrated validity problem and evaluated fix can still satisfy the course audit route.

### Other candidates considered

- **Household obligation reconciliation:** selectively add/revoke/change one task while preserving unrelated completed work; versioned obligations, obsolete-effect restoration, collateral movement. Broader dialogue, but high overlap/novelty risk. Not accepted scope.
- **Phase-scoped safety applicability audit:** SafeVLA acknowledges a composite component can disable a clause throughout an episode even where it would otherwise apply. Reproduce masked violations, compare episode-wide versus phase-specific applicability, report coverage and safe task completion. Fits course audit option but shifts away from the user's main LLM interest; code/data availability was not verified.

## 11. Task catalog and the classmate comparison

The task survey covers 38 current RoboCasa catalog tasks with at least eight published subtasks, sorted by count then demonstration duration. All listed candidates require mobile manipulation. Counts include navigation and do not guarantee reusable skills; duration is a demonstration median, not an LLM rollout budget.

Examples for research, not qualified task selections: DivideBuffetTrays (16), PackFoodByTemp (15), PackIdenticalLunches (15), StoreDumplings (11), ClearFreezer (11), ClearSinkArea (11), BlendMarinade (9). StoreDumplings has container-content dependencies; BlendMarinade has insertion/lid/appliance stages, but its source success predicate does not independently enforce every language-mentioned stage. Inspect exact source checkers before selecting any.

Files: [long_horizon_tasks.md](docs/long_horizon_tasks.md), [CSV](docs/long_horizon_tasks.csv).

The classmate's project, supplied by the user, assembles procedurally generated 7–40-piece MuJoCo block structures. Solvability is certified by privileged disassembly/reassembly. The model gets target poses, a simulator, code sandbox, persistent memory across roughly 20 targets, and token/sim/wall budgets. Three levels: given pick/place tools and example; raw simulator API with self-written primitives; raw end-effector/joint actions. Score final stable poses and cost to success; compare memory variants, control abstraction, multiple models, and planner reference.

This is context for distinguishing contributions, not a specification for OrcaBench. Fixed learned manipulation execution, visual supervision, private scoring, and no agent sandbox currently differ. Simply emphasizing long horizon or memory would make the projects more similar. Avoid assuming the classmate's final implementation matches the proposal.

## 12. Repository map and useful commands

| Path | Purpose |
|---|---|
| `src/robot_benchmark/contracts.py` | Public sensing/operation/action schemas and validation. |
| `src/robot_benchmark/runner.py` | Physics ownership, queue semantics, budgets, logs, completion. |
| `src/robot_benchmark/adapters/agents.py` | Actual shared system prompt, HTTP/Anthropic serialization, API-visible traces. |
| `src/robot_benchmark/adapters/robocasa.py` | Real simulator, three cameras, task-specific private evaluator, initial state and hashes. |
| `src/robot_benchmark/adapters/policy.py` | Loopback HTTP learned-policy client, health/reset/infer. No worker snapshot endpoint. |
| `src/robot_benchmark/policy_worker.py` | Isolated GR00T/pi0.5 inference, checkpoint verification, RNG/reset behavior. |
| `src/robot_benchmark/feasibility.py` | Ordinary and privileged diagnostic supervisors plus qualification support. |
| `src/robot_benchmark/evaluation.py` | Qualification/release and result aggregation; inspect before extending scoring. |
| `src/robot_benchmark/records.py`, `video.py` | Append-only artifacts, per-step frames, MP4 encoding. |
| `src/robot_benchmark/cli.py` | doctor, smoke-sim, feasibility, run, qualify, publish-policy-card, freeze-release, summarize. |
| `configs/` | Task/model examples, candidate splits, qualification example, source/dependency pins. |
| `scripts/` | Project cache env, remote bootstrap/download, artifact sync, termination guard. |
| `tests/` | Contract, isolation, step counting, queue cancellation, completion, qualification, records, adapters, infrastructure. |

Dependency-free local checks from the authoritative root:

```bash
cd /Users/tomwang/robot_benchmark
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 scripts/bootstrap_gpu.py --dry-run --skip-gpu-check
```

The last reported foundation suite had 59 passing tests. This handoff-only change did not rerun tests. Mock/unit success does not qualify the simulator-policy combination. Run appropriate tests after code changes as AGENTS.md requires.

For real GPU setup, read the full [compute runbook](docs/compute.md) and arm/verify cleanup first. Essentials on the Linux worker:

```bash
cd /path/to/OrcaBench
source scripts/project_env.sh
python3 scripts/bootstrap_gpu.py --download-assets --download-checkpoint
.venv-groot/bin/python -m robot_benchmark.policy_worker --backend groot --checkpoint checkpoints/groot/checkpoint-120000 --port 8765
```

Then use the simulator environment in another shell for doctor/smoke/feasibility. Do not run these commands locally expecting Mac CUDA support. Do not replace remote commands with the older harness's environment.

### Git state at handoff creation

- `main`; latest commit `323bd52` — Publish OrcaBench work-in-progress harness and development results.
- Origin fetch/push: `https://github.com/tom05919/OrcaBench.git`.
- Initial publication was completed; no new commit/push was made for this handoff.
- Preexisting untracked files: `docs/benchmark_direction_research.md`, `docs/first_interactive_task_outline.md`, `docs/long_horizon_tasks.md`, `docs/long_horizon_tasks.csv`.
- This new `handoff.md` is also untracked until a future commit. Do not overwrite or delete the other work.
- Git excludes environments, caches, vendor sources, assets, checkpoints, raw runs, and `.env`. Those local run artifacts will not appear in a fresh clone; distribute a deliberate artifact package if needed.

## 13. Next-agent priorities and pitfalls

1. Read this handoff and current docs; inspect Git before editing. Preserve distinction between original implemented protocol, user-selected breakfast pilot, and unapproved research proposals.
2. Continue the discussion from the latest novelty review. Do not announce that the user has chosen the supervision-value direction or silently rewrite the benchmark contract around it.
3. If continuing the established feasibility work, fix and predeclare the diagnostic handoff rule based on natural states, then qualify exact prompts and closing behavior. New rentals need current authorization/budget and independent cleanup.
4. If the proposed controlled suite is selected, implement task-specific scorers and exact runtime reproduction before claiming paired continuation results. Current snapshots store initial state/XML and later hashes; they do not provide restorable per-step checkpoints. Existing MP4s cannot support arbitrary branched physics replay.
5. Do local contract/scoring work first where useful. Keep physical validation, representative-video inspection, and real model results distinct from fixtures and mocks. A scoring replay consumes recorded private state/events, not pixels magically revealing exact simulator truth.
6. Progress scoring should preserve dependencies, distinguish first achievement from maintained terminal conditions, accept multiple valid orders, and not reward initial goal conjuncts or repeated transient contact. Keep cost/time diagnostics separate unless a justified formula is explicitly adopted.
7. Before comparing models, freeze disjoint evaluation instances, exact model identifiers/settings, prompts, policy checkpoint, observations, execution machinery, budgets, and automatic checker. Use paired seeds, retain every outcome, and report uncertainty and infrastructure errors.
8. If no executor/task qualifies, deliver honest feasibility/audit evidence rather than inventing benchmark scores, replacing learned controls with scripts, or claiming task novelty solves low-level incapability.

Do not lose the user's central motivation: a useful, substantive evaluation of an agent's physical supervisory judgment. Equally, do not manufacture a uniqueness claim to satisfy that motivation. The contribution must be precise, runnable, automatically scored, and supported by experiments.
