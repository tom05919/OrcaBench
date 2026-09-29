# Research context

This project asks a narrow systems question: when the environment, learned robot
policy, model-facing API, reference prompt evidence, observations, budgets, and
evaluator are fixed, how do different LLM orchestrators compare at supervising
that policy? The works below motivate parts of the protocol, but they do not
establish this benchmark's results. No novelty claim is made.

| Work | Primary contribution | Abilities evaluated | Model observations | Model actions | Intervention and recovery | Scoring and artifacts | Arbitrary interruption inside a learned-policy chunk? |
|---|---|---|---|---|---|---|---|
| [Embodied Agent Interface (EAI), arXiv:2410.07166v2](https://arxiv.org/html/2410.07166v2) | Ability-oriented benchmark and simulator evaluation interface | Goal interpretation, subgoal decomposition, action sequencing, and transition modeling in BEHAVIOR and VirtualHome | Symbolic initial state, goal, action/state vocabulary, or operator specification, depending on the module | LTL goals/subgoals, symbolic action sequences, or PDDL-style preconditions and effects | Not merely offline single-pass evaluation: Appendix H executes unsuccessful action-sequence plans, returns detailed grammar/runtime/unsatisfied-goal feedback, appends prior attempts, and permits up to three replans. It also studies stochastic action failures. | Goal and trajectory evaluation, task and execution success, and fine-grained grammar/runtime/planning errors; released data, code, and simulator evaluator are linked by the paper | No. Recovery is plan-level replanning after simulator feedback; the paper does not verify interrupting a running temporally extended learned policy at an arbitrary control step. |
| [EmbodiedBench, arXiv:2502.09560v1](https://arxiv.org/html/2502.09560v1) | Multienvironment benchmark and evaluation harness | Vision-driven planning across ALFRED, Habitat, navigation, and manipulation, with capability subsets for commonsense, complex instructions, appearance, spatial reasoning, and long horizon | Current image (optionally a short image history), instruction, history, task-specific valid skills or action format; manipulation additionally provides marked boxes and object positions | Dynamically sized multi-action JSON plans; high-level skills in some suites, navigation primitives, and a discretized 7-D end-effector action in manipulation | The agent reflects on prior actions and feedback at each planning step; failed or invalid plans restart planning from the latest state | Task and subgoal success rates plus planner/environment step counts; 1,128 test instances and simulator-based suites | No evidence. Multi-step replanning is supported, but the evaluated interfaces are not arbitrary interruption of a fixed learned-policy action chunk. |
| [RoboBench, arXiv:2510.17801v1](https://arxiv.org/html/2510.17801v1) | Robotics reasoning benchmark with a world-simulator planning evaluator | Instruction comprehension, perception reasoning, generalized planning, affordance prediction, and failure analysis | Real-robot images, multi-view/frame sequences, video-derived annotations, or question-specific context | Multiple-choice answers and structured manipulation/navigation function plans | It evaluates failure diagnosis and task-state/next-step reasoning. Long-horizon plans are rolled out by an MLLM world simulator against annotated dependency graphs and object-state milestones; it is not a closed-loop physical recovery controller | Accuracy and structured plan-component scores over 6,092 QA pairs; planning uses the world-simulator evaluator rather than robot-policy execution | No. The published benchmark does not verify arbitrary interruption and resumption of a running learned policy. |
| [REFLECT, arXiv:2306.15724v4](https://arxiv.org/html/2306.15724v4) | Proposed failure-explanation and correction method, evaluated with the RoboFail dataset | Failure localization, explanation, and correction planning | A hierarchical post-execution summary built from RGB-D, audio, robot state, scene graphs, event frames, and subgoal-end states | A high-level correction plan, mapped to executable environment actions | Detects the failed subgoal or planning error, explains it, then executes a correction plan from the final state of the failed run | Human-rated explanation quality, failure-time localization, and correction-plan task success; RoboFail contains 100 simulated and 30 real-world failures | No. Correction follows analysis of a failed execution; the method is not evidence for interruption within an executing learned-policy chunk. |
| This benchmark (design status) | Pilot benchmark protocol plus a thin execution harness | Visual monitoring, free-form policy prompting, observation-interval choice, queue continuation or reset, and truthful completion declaration | RGB from three robot cameras, proprioception, the goal, reference-prompt performance cards, budgets, and non-privileged execution history | `run_policy(prompt?, steps)` or `complete`; a supplied prompt may be any nonblank text up to 512 characters and advancing decisions choose 1–100 control steps | Physics pauses during LLM inference. Omitting the prompt continues the active instruction and action queue; supplying one, even identical text, discards the pending queue and redirects or restarts the policy. Low-level action chunks remain policy-owned. | Primary success requires both the physical predicate and a correct `complete` declaration before either budget expires; traces preserve decisions, prompts, actions, evaluator records, and errors | Implemented and exercised in one unqualified GR00T/Opus development episode. The model submitted dynamic prompts and the runner recorded interruptions, but this single episode ended in false completion; comparative ability and benchmark qualification remain unverified. |

## What transfers into this protocol

EAI supports separating embodied abilities and shows that detailed execution
feedback can materially affect replanning. This benchmark instead withholds
privileged evaluator feedback from the model so the comparison measures visual
and proprioceptive supervision. EAI's Appendix H is still an interactive
replanning experiment and must not be described as offline-only.

EmbodiedBench supports current-image, interaction-history, and variable-length
multi-step decisions. Its direct manipulation setting also supplies detection
boxes and object coordinates; this benchmark intentionally does not. RoboBench
offers useful failure and plan-feasibility taxonomies, while its world-simulator
scores are distinct from execution of a fixed learned policy. REFLECT shows why
temporal evidence helps failure analysis, but uses richer sensing and generated
summaries than this benchmark permits.

The unresolved empirical question is therefore limited and explicit: whether an
LLM can use RGB and proprioception to prompt and monitor a fixed learned policy,
choose when to continue queued actions or replace its instruction, and declare
completion. Source inspection establishes that the runner exposes this API.
Qualification measures the four exact reference prompts; only retained GPU
rollouts can establish how either those prompts or arbitrary dynamic prompts
work with the pinned policy and task.
