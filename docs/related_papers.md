# Papers behind OrcaBench

Compiled October 16, 2026 from `docs/research.md`, `docs/benchmark_direction_research.md`,
`docs/first_interactive_task_outline.md`, the October 1 design spec, and the papers read while choosing the direction.

**Read this first.**

- "Inspired" is too strong for most of these. Group 1 shaped the question and the scoring. Group 2 supplied the
  environment and policies. The rest set the line we draw around what we do **not** claim as new.
- **No single paper is the source of the current design.** Scoring "when to interrupt and how often to look", charging
  each LLM call on the task clock, and testing adaptation across policies of different ability came from the
  October 11-12 discussion and the stage 3-5 results (`docs/direction.md`). The nearest precedents are PACE,
  VoLo's two-timescale monitoring and *What Matters*' termination study.
- **Checked** = the paper or post was opened and its summary compared with the entry below. Everything not checked is
  as summarised in the October 1 review (`docs/benchmark_direction_research.md`); its dates and IDs come from that
  memo and were not re-verified.
- Claims of absence ("no released benchmark does X") are limited to that review of about 25 papers.

## 1. LLM or VLM supervision of a pretrained VLA (closest work)

- [Embody / Claude plays robotics](https://www.anthropic.com/research/claude-plays-robotics) (Anthropic, July 2026).
  **Checked.** Twelve models supervising a fixed MolmoAct policy on LIBERO. Every model did worse than the policy
  alone on familiar tasks, and the strongest model scored below weaker ones because it overrode the policy more often
  than warranted. Uplift appeared only on new tasks the policy could not do. *Why it matters:* the premise that supervision can hurt, and the reason a trained-task-only benchmark
  rewards "never interrupt".
- [What Matters in Orchestrating Robot Policies](https://arxiv.org/html/2606.10267v1), arXiv:2606.10267 (June 2026).
  **Checked.** Varies the VLM, the termination rule (fixed frequency, success detection, VLM-predicted horizon),
  observations and memory; some conditions use privileged simulator information. *Why it matters:* the closest
  precedent for treating how often to check as a design variable. Success-detection termination beat fixed frequency.
- [VoLo](https://arxiv.org/html/2606.07723v1), arXiv:2606.07723 (June 2026). **Checked.** A VLM orchestrator treats
  VLAs such as π0.5 as interruptible tools and monitors at 0.2 Hz while the policy moves at 15 Hz. Completion-monitoring
  errors were over two thirds of VLM failures and grew with model capability. *Why it matters:* it echoes our stage 3
  finding that models declare "done" early, and it motivates scoring "declaring done" as its own measure.
- [RoboHarness](https://arxiv.org/html/2607.18060v1), arXiv:2607.18060 (July 2026). An LLM agent routes among
  learned policies using a capability memory. *Why it matters:* prior work on routing across policies of different
  ability, which is the setting our session mode puts one supervisor in.
- [Hi Robot](https://arxiv.org/html/2502.19417v1), arXiv:2502.19417 (February 2025). A trained high-level VLM over
  π0 handling complex instructions and corrections. *Why it matters:* a hierarchical stack is not itself new.
- [CheckVLA](https://arxiv.org/html/2607.26789v1), arXiv:2607.26789 (July 2026). Execution verification with an
  action-conditioned world model. *Why it matters:* verification alone is already studied.

## 2. Environment and policies

- [RoboCasa365](https://arxiv.org/html/2603.04356v1), arXiv:2603.04356. **Checked, and not cited in any repo doc
  until now.** 365 kitchen tasks (65 atomic, 300 composite), a pretraining split, and official checkpoints. Its own
  multitask results for GR00T N1.5 were 43.0% on atomic, 9.6% on seen composite and 4.4% on unseen composite tasks.
  *Why it matters:* the source of our tasks, success checkers and checkpoints, and the reason the benchmark mixes
  trained tasks with unseen composites.
- GR00T N1.5 and π0.5 are the policies being supervised. They are models under test, not inspirations; the repo
  docs do not cite their papers, so none is listed here.

## 3. Timing, pairing and protocol precedents

- [PACE](https://arxiv.org/html/2606.00537v1), arXiv:2606.00537 (June 2026). Changing a chunked policy's execution
  horizon alone changes outcomes. *Why it matters:* the nearest precedent for timing mattering by itself. We keep
  re-querying separate from instruction content, and every restart discards queued actions.
- [LIBERO-MAX](https://arxiv.org/html/2609.36518v1), arXiv:2609.36518 (September 2026). Pairs continuations from the
  same initial state, policy seed and executed prefix. *Why it matters:* matched-prefix pairing is established. Our
  scorer pairs a supervised run with a plain run on the same scene and policy noise.
- [ConflictVLA-Bench](https://arxiv.org/html/2609.31792v1), arXiv:2609.31792 (September 2026). Eight VLAs, paired
  and capability-qualified outcome evidence. *Why it matters:* the memo says to borrow the distinction between not
  completing and correctly disengaging, not to claim it.
- [FailBench](https://arxiv.org/html/2609.03611v1), arXiv:2609.03611 (September 2026). Scores failure detection from
  recordings and explicitly does not measure what a supervisory decision causes next. *Why it matters:* motivates
  scoring by executing the decision.
- [Fast Plans, Faithful Actions](https://arxiv.org/html/2609.30833), arXiv:2609.30833. **Checked, not cited in repo
  docs.** In a planner-plus-executor VLA, the executor barely used the planner's waypoints (a 0.6% action change
  when erased). *Why it matters:* a reminder that what we send the policy may influence it less than we assume.

## 4. Do VLAs follow changed instructions? (limits of re-prompting)

- [LIBERO-Plus](https://arxiv.org/html/2510.13626v1), arXiv:2510.13626. **Checked, not cited in repo docs.** Ten
  VLAs largely ignored language: with a blank instruction most kept working, and with a swapped target they still
  went for the original. *Why it matters:* the same concern as the ceiling test in `docs/direction.md`: if perfect
  instructions cannot help, no LLM can.
- [ReSteer](https://arxiv.org/html/2603.17300v1), arXiv:2603.17300 (March 2026): language steerability from
  intermediate states.
- [SwitchVLA](https://arxiv.org/html/2506.03574v1), arXiv:2506.03574 (June 2025): switching tasks mid-execution.
- [CoRe / LangSwitch](https://arxiv.org/html/2608.14822v1), arXiv:2608.14822 (August 2026): training-free recovery
  of frozen π0, π0.5 and GR00T N1.7 at several timings.
- [One Word, Different Action](https://arxiv.org/html/2609.05260v1), arXiv:2609.05260 (September 2026): policy
  response to minimally changed instructions.
- [AquaMend](https://arxiv.org/html/2609.28973v1), arXiv:2609.28973 (September 2026): diagnosis and conditional
  rollback.

## 5. Harmful intervention in digital agents

Not in the October 1 memo's table. Found while framing the "harm" half of the original plan and cited in the
October 1 design spec. Only search-result summaries were seen, not the papers.

- [The Intervention Paradox](https://arxiv.org/html/2602.03338), arXiv:2602.03338: a critic with strong offline
  accuracy can still degrade an agent when it intervenes.
- [Calibration Is Not Control](https://arxiv.org/html/2606.21399), arXiv:2606.21399: the decision object is the
  gain from intervening versus continuing, measured by branching from identical prefixes.

## 6. Embodied planning benchmarks (the original comparison, `docs/research.md`)

- [Embodied Agent Interface](https://arxiv.org/html/2410.07166v2), arXiv:2410.07166: ability-oriented evaluation
  with execution-feedback replanning.
- [EmbodiedBench](https://arxiv.org/html/2502.09560v1), arXiv:2502.09560: vision-driven planning across several
  environments.
- [RoboBench](https://arxiv.org/html/2510.17801v1), arXiv:2510.17801: robotics reasoning with a world-simulator
  planning evaluator.
- [REFLECT](https://arxiv.org/html/2306.15724v4), arXiv:2306.15724: failure explanation and correction.

*What transferred:* separating abilities, and failure taxonomies. *What we do differently:* none of these interrupts
a running learned policy, and we withhold privileged feedback from the model.

## 7. Dialogue and persistent-task work (the abandoned breakfast direction)

These set what we decided not to claim, not what we built.

- [tau2-bench](https://arxiv.org/html/2506.07982v1), arXiv:2506.07982, with [DialFRED](https://arxiv.org/abs/2202.13330),
  [TEACh](https://arxiv.org/abs/2110.00534) and [AmbiK](https://arxiv.org/abs/2506.04089) (`docs/first_interactive_task_outline.md`).
- [Ask-to-Act](https://arxiv.org/html/2504.00907v5), [Ask-to-Clarify](https://arxiv.org/html/2509.15061v1),
  [PARTNR](https://arxiv.org/html/2411.00081v1) and its [dialogue extension](https://arxiv.org/html/2605.12920v1).
- [WorldLines](https://arxiv.org/html/2606.18847v1), [AppWorld-UL](https://arxiv.org/html/2607.20536v1),
  [AgentChangeBench](https://arxiv.org/html/2510.18170v1), [ATRBench](https://arxiv.org/abs/2605.28108).

## 8. Safety and benchmark audits

- [ManiGuard](https://arxiv.org/html/2608.17386v1), arXiv:2608.17386: temporal safety monitors.
- [SafeVLA-Bench](https://arxiv.org/html/2606.00773), arXiv:2606.00773: post-hoc safety scoring on LIBERO and
  RoboCasa-365.
- [Faster and Better? Benchmark Bugs](https://arxiv.org/html/2609.37771v1), arXiv:2609.37771: an audit of robotics
  benchmarks.

## 9. Read, related, not cited elsewhere

All **checked** against their pages. They informed the October 1-2 choice of direction and are in no other repo doc.

- [Harness VLA](https://arxiv.org/html/2607.08448v3), arXiv:2607.08448: an agent wraps frozen VLAs as retryable
  primitives with memory, evaluated on LIBERO-Pro and RoboCasa365.
- [SEES](https://arxiv.org/html/2609.32698), arXiv:2609.32698: a frozen VLM planner decomposes RoboCasa365
  composite tasks; the paper reports no planner-only baseline.
- [inspect-robots](https://github.com/robocurve/inspect-robots) (GitHub): a framework for running LLM agents on
  robot benchmarks. Its README publishes no results.
