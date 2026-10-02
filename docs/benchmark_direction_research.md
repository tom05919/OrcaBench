# OrcaBench direction review: measuring the value of supervision

Research cutoff: October 1, 2026. Status: research proposal, not an adopted protocol, implemented extension, or novelty certification.

## Recommendation

The strongest direction consistent with this project is a controlled evaluation of **when LLM supervision helps or harms a frozen learned robot policy** across manipulation tasks and execution stages. The proposed contribution is an evaluation protocol that attributes observed improvements to supervisory decisions, separates runtime effects, and establishes whether the executor can respond to those decisions. None of planning, monitoring, recovery, goal revision, or clarification is individually new.

Three independent subagents investigated recent related work, proposed candidates, and challenged novelty and feasibility. They converged on a validity problem more defensible than a new household-dialogue capability: an apparent orchestration gain can come from requerying the VLA, discarding its action queue, changing context, or selecting states where the target is already reachable. The agent's instruction may contribute little. This is a hypothesis to test, not a demonstrated flaw in another paper.

A benchmark can focus on one capability while spanning substantial physical diversity. Adding more chores or more dialogue does not establish a contribution. The proposed suite becomes substantive through many decision states, paired physical continuations, automatic outcome checks, and controls that can falsify an orchestration claim. If those controls reproduce existing findings without yielding a new diagnostic or useful correction, call the result a replication or extension.

## What recent work already covers

The table distinguishes capabilities studied from the proposed measurement gap. A method paper can still contain evaluation protocols that invalidate a novelty claim. These are primary-source observations; claims that something is absent are limited to the reviewed protocol, not the entire literature.

| Work and source | Agent or execution stack | Relevant coverage and implication |
|---|---|---|
| [Embody / Claude plays robotics, July 2026](https://www.anthropic.com/research/claude-plays-robotics) | LLM supervisors with a fixed MolmoAct VLA; also direct and programmatic control | Already compares models supervising a pretrained VLA, including harmful overrides and novel-task uplift. Merely comparing LLM orchestrators is insufficient. |
| [What Matters in Orchestrating Robot Policies, June 2026](https://arxiv.org/html/2606.10267v1) | Gemini 2.5 VLM family over GROD VLAs | Studies model choice, termination, observations, memory, and flat-VLA baselines. Some conditions use privileged simulator information. A generic orchestration-factor study has a direct precedent. |
| [VoLo, June 2026](https://arxiv.org/html/2606.07723v1) | VLM orchestrator, learned VLA, perception and grasp tools | Measures long-horizon execution, recovery, monitoring errors, and multiple VLM backends. Its extra manipulation tools differ from our frozen-VLA-only scope, but monitoring and recovery are already evaluated. |
| [RoboHarness, July 2026](https://arxiv.org/html/2607.18060v1) | LLM agent routing among learned policies and a planner | Covers heterogeneous routing, handoffs, capability memory, and runtime adaptation. Adding a policy-selection API alone is a harness contribution. |
| [ReSteer, March 2026](https://arxiv.org/html/2603.17300v1) | Multitask VLAs, including pi0.5 and OpenVLA-OFT | Tests target prompts from intermediate source-task states with repeated rollouts. State-dependent language steerability is already an explicit evaluation object. |
| [SwitchVLA, June 2025](https://arxiv.org/html/2506.03574v1) | Trained VLA with switching-aware trajectories | Evaluates early, middle, late, and repeated switches, including returning a held object before a new task. Simple switching or rollback is not a new capability. |
| [CoRe / LangSwitch, August 2026](https://arxiv.org/html/2608.14822v1) | Training-free recovery of frozen pi0, pi0.5, and GR00T N1.7 | LangSwitch evaluates re-grounding, re-skilling, and conflicts at multiple timings. Progress preservation is explicit. Its physical restoration method exceeds our permitted executor interface. |
| [One Word, Different Action, September 2026](https://arxiv.org/html/2609.05260v1) | Robot policies under minimally changed instructions | Same-state instruction invariance and sensitivity already have a dedicated evaluation. A prompt contrast alone is insufficient novelty. |
| [ConflictVLA-Bench, September 2026](https://arxiv.org/html/2609.31792v1) | Eight VLAs under valid and conflicting task premises | Uses paired, capability-qualified outcome and process evidence. Failure to complete does not establish appropriate disengagement. We should borrow this distinction, not claim it. |
| [LIBERO-MAX, September 29, 2026](https://arxiv.org/html/2609.36518v1) | Fourteen robot policies under dynamic physical events | Pairs continuations with identical initial state, policy seed, and executed prefix. Its event set differs from our no-disturbance scope; matched-prefix evaluation itself is established. |
| [FailBench, September 2026](https://arxiv.org/html/2609.03611v1) | General VLMs and specialized failure detectors | Scores success/failure from robot recordings. It explicitly does not measure what a supervisory decision causes next. This distinction motivates execution-based scoring, not another binary failure label. |
| [PACE, June 2026](https://arxiv.org/html/2606.00537v1) | Fixed chunked robot policies with adaptive execution horizons | Changing chunk execution alone changes outcomes. Query timing and discarded actions must be separated from semantic instruction effects. |
| [CheckVLA, July 2026](https://arxiv.org/html/2607.26789v1) | VLA with execution verification and an action-conditioned world model | Studies verification, replanning, and completed-subgoal regression. Execution verification alone is occupied. |
| [Hi Robot, February 2025](https://arxiv.org/html/2502.19417v1) | Trained high-level VLM over pi0 | Handles complex instructions and interactive corrections. A human-facing hierarchical stack is not itself a benchmark gap. |
| [Ask-to-Act, current v5](https://arxiv.org/html/2504.00907v5) | Multimodal agent, oracle skill library, LLM user | Interleaves actions and clarification for hidden preferences. The execution abstraction differs, but asking the human what they want is already evaluated. |
| [Ask-to-Clarify, September 2025](https://arxiv.org/html/2509.15061v1) | Qwen2-VL planner and ScaleDP motor policy on xArm7 | Real-robot clarification and absent-target handling undermine a blanket claim that dialogue plus learned manipulation is new. |
| [PARTNR](https://arxiv.org/html/2411.00081v1) and [dialogue extension](https://arxiv.org/html/2605.12920v1) | LLM household collaborators over embodied skills | Planning with household constraints and communicating world models are established. Original PARTNR and its dialogue extension should not be conflated. |
| [WorldLines, June 2026](https://arxiv.org/html/2606.18847v1) | Stateful household traces with memory and planning probes | Cross-day state and remembered constraints are already evaluated. Its trace-based probes differ from continuous learned-policy execution. Longer chores alone mainly add memory demands. |
| [AppWorld-UL, July 2026](https://arxiv.org/html/2607.20536v1) | Tool agent and constrained LLM user in digital apps | Covers missing information, acceptable alternatives, confirmations, and knowledge controls. Copying this structure into a robot scene needs an additional embodied measurement claim. |
| [AgentChangeBench](https://arxiv.org/html/2510.18170v1) and [ATRBench](https://arxiv.org/abs/2605.28108) | Digital tool agents | Dynamic goals and acquiring preferences for later use have non-robot precedents. Physical execution must make the measurement substantively different. |
| [AquaMend, September 2026](https://arxiv.org/html/2609.28973v1) | Embodied diagnosis and conditional rollback method | Compares information gathering, correction, and preserving valid work. Conditional rollback should not be our headline novelty. |
| [ManiGuard, August 2026](https://arxiv.org/html/2608.17386v1) | Robot policies with physics-grounded temporal monitors | Temporal constraints and engagement-aware safety reporting are covered. Safety can be inflated by inaction; task completion must remain visible. |
| [SafeVLA-Bench, September 30 revision](https://arxiv.org/html/2606.00773) | Post-hoc safety evaluation on LIBERO and RoboCasa-365 | Already includes threshold sensitivity and violation exposure. Its acknowledged episode-wide deactivation of clauses in composite tasks leaves a specific applicability audit candidate. |
| [Faster and Better? Benchmark Bugs, September 2026](https://arxiv.org/html/2609.37771v1) | Audit of multiple robotics benchmarks | Generic checker-bug hunting is also established. A project needs a specific reproducible validity issue and an evaluated fix. |

Additional overlap screens included ProGAL-VLA, InstructMove, COOPERA, CoIN, REIBench, RoboIRGBench, RoboAbstention, and SALT. They reinforced the risks around ambiguity, reference grounding, persistent preferences, abstention, and capability-aware alternatives. They are not needed to establish the central recommendation. We excluded a withdrawn HODAgent preprint from affirmative evidence.

## Candidate 1: a controlled supervision-value suite

### Research question and contribution claim

How much do an LLM's execution-time decisions improve physical outcomes over a frozen learned policy, after separating effects of language, policy requery, queued-action treatment, and orchestrator context?

The proposed novelty is a common measurement protocol and diagnostic decomposition for LLM-supervised robot execution. We did not verify another reviewed work using the entire proposed control set as one benchmark. That is a bounded search finding, not proof of uniqueness. Embody, What Matters, VoLo, ReSteer, and LIBERO-MAX are mandatory closest-work comparisons.

### Breadth and task construction

Build a suite over at least three physically distinct task families, provisionally object retrieval/placement, articulated storage, and multi-object arrangement or cleanup. Breakfast remains a calibration case. Select concrete RoboCasa tasks only after their predicates and fixed-policy performance are checked; no new scene or arbitrary prompt is assumed executable.

Freeze checkpoint selection using independent development rollouts, before evaluating any supervisor. Do not select recovery cases because an evaluated supervisor or its paired branch failed. Use several execution stages and naturally occurring outcomes: productive motion, ambiguous apparent completion, failed contact or dropped object, no progress, completed work vulnerable to unnecessary continuation, and the transition to a dependent goal. Include null cases where leaving the VLA alone is best. Recovery-only cases would reward indiscriminate intervention.

A prospective pilot is 3 task families x 3 execution stages x 4 independently selected states: 36 shared checkpoints, tested by two real LLMs and matched controls. This is a design scale, not a claim of sufficient statistical power. Branch duration, replicate count, and cost must be calibrated before freezing evaluation. Include some complete episodes to test compounding decisions rather than only isolated branches.

### Agent interface

Retain free-form policy prompting and agent-selected execution intervals. The agent receives the same RGB views, proprioception, active prompt, public history, and budgets across systems. It chooses language, continuation interval, and completion through the existing API. Benchmark strata are evaluator labels, not forced Start/Retry/Switch action classes.

Simulator truth is offline scoring and explicitly privileged feasibility diagnostics only. No evaluator progress labels, reachable-state verdicts, or verified predicates are sent to the model. A proposed context summary must be generated from public observations by the agent itself; it cannot import the checker's truth.

Human dialogue is optional for later event cases, not the main contribution. If added, a finite private profile supplies facts and preferences, an LLM renders replies, and a deterministic event ledger defines the active specification. The user simulator does not judge physical success or invent manipulation advice. All-information controls are already a standard design pattern, not our novelty claim.

### Matched continuation protocol

Select checkpoints from ordinary resets and learned-policy trajectories using predeclared rules. The evaluator restores a checkpoint into independent experimental branches; the agent has no reset or restore tool. This creates matched experiments without artificial disturbances or scripted manipulation.

Serialize simulator/controller state, policy RNG and implementation caches, action queue, active instruction, observation history, and counters. If direct restoration is unavailable, replay the original policy calls as well as the action prefix and validate returned chunks, worker runtime, and simulator equivalence. Replaying physical actions alone cannot restore policy RNG or caches. Alternatively initialize the worker identically in every branch and label the experiment a clean-context checkpoint evaluation, not a live-runtime continuation. Videos alone cannot restore a robot state. Identical seeds alone do not guarantee identical states or policy streams.

Use three separate contrasts:

1. **Instruction content:** at the same query boundary, compare the agent's revised prompt against an identical-old-prompt requery, a fixed old-goal paraphrase, and, if affordable, a fixed revised-goal paraphrase. Predeclare paraphrases before evaluation. Queue treatment, policy reset, observation, physical horizon, and query schedule are fixed for this contrast.
2. **Execution machinery:** compare queued continuation against a fresh query with the same instruction. Requery is intentionally the treatment; actual query counts can differ. Give equal resource allowances, log actual use, and do not describe unequal realized compute as matched compute. A separate sham query may be used only if its RNG/cache effects are isolated and verified.
3. **Orchestrator context:** compare a live supervisor against a clean supervisor receiving the same current target, public sensor-history window, active prompt, and budgets. The internal physical/policy runtime starts identically but is not exposed. Neither model receives queued actions, serialized simulator/controller state, evaluator predicates, reachability labels, or hidden policy state. Prior dialogue and plan memory are intentionally removed in the clean condition; the sensor window is held fixed. Do not confuse this with heterogeneous-policy handoff.

For each comparison, start from identical states and repeat policy seeds where needed. These contrasts are controlled effects under the specified settings; they do not automatically form an additive decomposition because context, prompts, and scheduling can interact. Use a small factorial experiment if estimating interactions. Frozen-boundary branches estimate a decision-level effect conditional on that state and boundary. They do not measure the total value of a live supervisor that chooses when to intervene. For the latter, compare complete supervisor policies against predeclared continuation and sham-supervision policies from identical initial checkpoints or episodes, with shared resource allowances.

### Automatic scoring

Predefine a goal utility J for each task: physical terminal success and, separately, the fraction of required predicates currently satisfied. Record first achievement and persistence so accidental contact or later regression is visible. A partial goal is not equivalent to complete success, and milestone ordering is enforced only when the task specification requires it.

At a fixed continuation horizon, report:

- Paired difference in terminal success and goal progress between the supervisor branch and each control.
- Harmful interventions: control succeeds or preserves progress while the supervisor regresses.
- Semantic benefit after controlling for identical-prompt requery.
- Recovery benefit over continuation on naturally encountered failures.
- False completion and unnecessary physical execution after the goal already holds.
- Execution steps, VLA calls, LLM calls, tokens, latency, and discarded actions.

A decision can also be compared against a predeclared finite set of tested alternatives. Call this comparison with tested alternatives, not regret against a globally optimal controller. Do not normalize by a tiny or zero estimated policy ceiling, or combine success, partial progress, and time with arbitrary weights. Release separate outcome and cost profiles, plus confidence intervals and every attempted outcome.

Use unconditional rates on the frozen set as the main report. Separately report feasibility strata qualified on independent development episodes. Never remove evaluation failures because a reference branch failed on that same trial. A clean-context target branch is diagnostic evidence, not proof of the executor's maximum possible ability.

### Hypotheses that can fail

- Semantic supervision improves goal outcomes over same-prompt requery at matched query boundaries.
- Some supervision is harmful, especially during successful approach or after completed subtasks.
- Model rankings or apparent improvements change when runtime controls are introduced.
- Recovery benefits persist on independently qualified states and cannot be explained entirely by fresh observations or chunk cancellation.

A null result remains useful if the experiment has adequate executor competence and uncertainty reporting. Positive results are not required for a benchmark; sensitivity and validity are. If the protocol has no consequential difference from existing evaluations, reduce the novelty claim to replication.

### Why this is more than a framework

The deliverable is a frozen checkpoint/task set, reproducible branch generator, private automatic scorer, control baselines, intervention provenance, and results for two real supervisors. A framework exposing policy calls without this test set and outcome protocol would not meet the intended contribution.

## Candidate 2: ongoing household obligation reconciliation

A broader capability candidate is handling multiple active physical jobs when a user adds, selectively changes, or cancels one job while other commitments remain valid. Example: prepare two servings; change only the second person's food; leave the first serving and shared utensils intact; cancel a later cleanup instruction; resolve a scoped preference conflict.

Automatic checks would track active obligations, preserved valid work, obsolete effects that must be undone, and collateral movement. A paired control receives the final active specification from the identical physical state, with irrelevant dialogue removed. This tests whether the physical situation adds difficulty beyond updating a text ledger.

However, task switching, rollback, household constraints, preference acquisition, and dialogue planning are individually covered. LangSwitch, SwitchVLA, WorldLines, AppWorld-UL, PARTNR, and AquaMend overlap strongly. The remaining candidate is selective scope and precedence across multiple physical commitments. We have not established that it is a sufficiently distinct benchmark capability. Treat this as a higher-risk research proposal, not the recommended October release headline.

## Candidate 3: phase-scoped safety applicability audit

SafeVLA-Bench acknowledges that a component tag can disable a safety clause for the whole composite episode even when the clause should apply during other phases. A concrete audit could reproduce affected tasks, show missed hazards in otherwise applicable phases, then compare episode-wide and phase-scoped scoring on identical traces.

Report clause/time coverage, safe task completion, and safety conditional on engagement. An agent that freezes should not appear better merely because nothing happens. Current SafeVLA already studies threshold sensitivity and violation durations, so those are not missing features. Its broad code/data release was not verified available; reproducing the instrumentation may be substantial work.

This fits the course's explicit inspect-and-fix-an-existing-evaluation route. It is less aligned with the user's interest in LLM policy orchestration, so it is a fallback rather than a silent change of project.

## Current repository evidence and implementation implications

The existing runner provides observations, free-form prompting, intervals, paused inference, queue cancellation, recordings, and private per-step evaluation. Its task scorer is currently specific to CerealAndBowl; generic multi-task scoring is not implemented. Three families require new task contracts, predicate adapters, checkpoint-selection rules, and simulator validation. Supplying a prompt, including unchanged text, clears the action queue and calls reset_skill; omitting it continues the queue. This is documented behavior, not a confirmed bug. It makes an identical-prompt requery a necessary experimental control. See src/robot_benchmark/runner.py and docs/protocol.md.

The simulator adapter currently retains the initial flattened state/XML and subsequent state hashes, not restorable full checkpoints at every step. RemotePolicy has no snapshot/restore endpoint. Exact branch reproduction therefore needs implementation and validation; existing videos and hashes alone are insufficient. See src/robot_benchmark/adapters/robocasa.py and src/robot_benchmark/adapters/policy.py.

The September 27 development pass contained three live episodes on different seeds, none with physical task success. It is not a paired comparison, qualified failure rate, or evidence that every GR00T task is incapable. The reference prompts and full-task gates remain incomplete. See [feasibility.md](feasibility.md).

No harness code, task contract, model configuration, or GPU deployment was changed by this review.

## Go/no-go sequence

1. Audit the full closest protocols before claiming the proposed control set is distinct. In particular, compare What Matters, Embody, VoLo, ReSteer, and LIBERO-MAX against the exact contrasts above.
2. Implement and validate task-specific scoring plus checkpoint continuations: identical-prompt twin branches must agree within declared simulator and policy tolerances. Investigate controller and GPU nondeterminism instead of assuming seed equality is enough.
3. Screen simple task families and prompt pairs on development seeds. Retain all attempts. Establish physical competence, language responsiveness, and meaningful alternative continuations without training or injected disturbances.
4. If at least three families support informative supervisory choices, freeze a separate pilot set and run two LLMs through the same contract. Keep source/checkpoint IDs, models, conditions, and budgets constant within comparisons.
5. If task competence remains at a floor, do not publish model rankings as orchestration ability. Report the evidence as a validity/feasibility audit or revisit the executor/task choice with the user.

The honest proposed headline is: **a controlled benchmark of the value and failure modes of LLM supervision during learned robot-policy execution**. Its contribution must be earned through the evaluation and results; the research review alone does not establish novelty.
