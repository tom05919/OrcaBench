# Simplified supervision environment: decisions and specification (October 9, 2026)

This answers `docs/env_design_brief.md`. It is a design, not results. Nothing here has been built or run against a
model. The numbers in the calibration tables come from a throwaway CPU prototype of this specification (written in a
scratch directory and not committed). They are the targets that the real implementation must reproduce, so they
double as its acceptance tests. They are not measurements of any LLM.

## Decisions in brief

1. **Environment: an abstract CPU simulator** with a latent task process and parametric VLAs. It reproduces the
   real harness's decision interface exactly (`run_policy(prompt?, steps 1..400)` and `complete`, the same JSON
   schema, validation and restart semantics). It uses no images, no GPU and no real policy. Three VLA profiles
   ("steady", "hesitant", "brittle") are placed so that the best observation and interruption rules differ by
   VLA. With these profiles, a supervisor that adapts to each VLA is worth 0.08 to 0.12 of a task's value per
   episode more than the best single rule.
2. **Protocol, in two parts, for about $2.4 to $3.9 of API spend.** **Part 1 (primary): log probes.** Opus 5.5
   reads raw records of 0, 3 or 8 earlier episodes per VLA and is asked what to do in standardized situations:
   the first observation interval, an apparent stall, and the first sight of completion. Each answer is scored
   against exact Monte Carlo action values. This is the cheapest and least noisy way to answer both of the user's
   questions. **Part 2 (secondary): closed-loop sessions.** One session of 24 interleaved episodes (8 per VLA)
   in which the agent generates its own experience; a second, mirrored session runs only if the money allows.
   This part measures realized success, calls, robot time and regret against the best fixed rule for each VLA.
   Haiku 5.5 repeats everything for about $0.25 as a lower-capability contrast. Noise is controlled by common
   random numbers, expected-value scoring and repeats. Temperature cannot be set on these models.
3. **No further GPU run now.** The environment takes restart cost, wording sensitivity and undo-after-success as
   stated parameters that bracket the evidence. The brief's lean run would spend about $3 of the remaining $5 of
   API, and it could not pin those dials down at the sample sizes it allows. A run becomes worthwhile only on a
   trigger defined in section 3. If it is run, it is API-free (about 3 pod-hours, about $1.6).

## 0. Problems with the brief's framing

These shaped the decisions. Each is backed by repository data or by the prototype.

1. **The real harness cannot learn in context across episodes.** Each decision is a stateless single API call
   (`adapters/agents.py`) with the current episode's `history`. There is no memory across episodes, no outcome
   after an episode, and the system prompt never states what a call or a robot-second costs. Asking whether an
   agent learns "how often to call it to minimize cost" is not a fair question unless the agent is told the costs
   and sees past outcomes. The environment therefore adds three things to the interface: an `experience` record of
   past episodes, the outcome after each episode, and an explicit score. These are deliberate contract additions.
   Results transfer to the real harness only if it adopts the same three additions.
2. **No real evidence shows that interrupting ever helps.** The rescue arm was lost. On the 37 confirmed pairs,
   leaving the policy alone is right by construction: the second always-defer run succeeded on 35 of 36 usable
   pairs. In the stored plain episodes, real failures are not stalls: only 6 of 82 failed plain episodes end in a
   still period, and the policy keeps moving without achieving the goal. If no VLA can be rescued, "when to
   interrupt" collapses to "never". So the VLA in which a restart rescues ("brittle") is an **explicit
   assumption**, not a calibrated fact.
3. **Robot motion carries no information about completion.** I measured commanded stillness: the smoothed action
   magnitude stays below 0.05 for at least 20 steps. In 156 stage 3 plain episodes the robot is still in 4 to 5% of
   the steps before success. In 48 always-defer successes the median still fraction after success is 3%. GR00T
   keeps acting after the task is done, which is also why success can be lost. A "the arm stopped" cue would make
   completion easy to detect, which the real robot does not allow, so the environment gives no motion cue.
4. **Temperature is not available.** Opus 5.5 rejects sampling parameters, and Haiku 5.5 rejects non-default
   values. Sampling noise has to be handled with repeats and with designs that need few samples.
5. **Learning curves from realized outcomes are too noisy at this budget.** In the prototype, detecting the gap
   between the best rule for each VLA and the best pooled rule at 2 sigma from realized utility needs **35 to 90
   paired episodes per VLA** (46 to 213 unpaired). The budget affords about 8 to 16. Asking the agent directly
   what it would do in fixed situations, after it has seen fixed amounts of experience, removes environment noise
   entirely. Those log probes
   are the cheaper way to answer both questions, so they are the primary measurement.
6. **"Ability" is not one axis.** The best supervision rule depends on four things: (a) how often the VLA gets
   stuck in a way that a restart fixes, (b) how often it only looks stuck, (c) how fragile it is to restarts, and
   (d) how fast and how variable it is. Plain success alone does not set the rule. The three profiles are points
   in that space, ordered by plain success (0.97, 0.83, 0.26).
7. **The lean GPU run has the wrong shape for this question.** See section 3.

## 1. Decision 1: the environment

### Why an abstract simulator and not real or hybrid tasks

- **Counterfactuals.** Scoring "should it have interrupted here?" needs the value of actions that were not taken.
  Only a process that can be resampled from any state provides that. Recorded real rollouts cannot (a restart has
  no recorded continuation), and simplified real tasks would need a GPU rollout for every counterfactual.
- **Control of how much the VLA messes up.** The stuck rate, apparent-stall rate, restart fragility and speed are
  separate parameters. GR00T's competence cannot be dialed, and other real VLAs would mean new checkpoints and new
  validity work.
- **Validity and cost.** It is deterministic given a seed, so there are no scene mismatches, host-specific start
  states or renderer faults (the three stage 2/3 validity problems), and it costs no GPU money.
- **What is lost.** Real perception is replaced by a calibrated perception model. The offline completion probes
  already measured Opus's perception separately: 36% false negatives, 11% false positives, a lead of about 20
  steps. Real VLA dynamics are replaced by a calibrated process. A hybrid that feeds stored frames by phase was
  rejected for now. It cannot follow counterfactual trajectories, and it would bring back about 4,000 image tokens
  per call, roughly 10 times the input cost. It stays available as a later "perception from real frames" variant.

### Building blocks

All time is in control steps (20 steps = 1 s). One episode is defined by `(VLA profile, seed)`.

**B1. Clock and budgets.** Step budget 900. Real budgets are 450 to 1,800, and 900 is 3.3 times the steady VLA's
median completion and 1.7 times the hesitant VLA's; the real range of budget slack is 1.5 to 4 times. Maximum
interval 400, maximum 100 decisions per episode, as in the real harness.

**B2. Latent task process.** The state is one of WORK, HOVER, STUCK, DELAY, RETREAT, DONE, LOST or BROKEN.

| Rule | Specification |
|---|---|
| Work needed | `W = round(LN(m_W, s_W))`, at least 20 steps of WORK |
| WORK | `work_done` grows by 1 per step. When it reaches a pending stuck onset the state becomes STUCK; at a hover onset, HOVER(d); at `W`, RETREAT(L) |
| HOVER(d) | no progress for d steps, then WORK. Resolves on its own: an apparent stall |
| STUCK | no progress until a restart frees it: a real stall |
| RETREAT(L) | visually complete, checker still false for L steps (hidden post-conditions such as gripper retreat or door angle), then DONE |
| DONE | the checker is true. Success is lost (LOST) after `E ~ Exp(h)` DONE-steps, because the policy keeps acting |
| LOST, BROKEN | the checker is false for the rest of the episode |
| Hover onsets | Poisson process over work-steps, rate `λ_h` per 100 work-steps; durations `round(LN(m_h, s_h))` |
| Stuck onsets | Poisson process over work-steps, rate `λ_s` per 100; consumed in order (after an escape the next onset applies) |
| Lag | `L = round(LN(20, 0.5))`: median 20, p10 10, p90 38 |
| Loss hazard | `h = 5e-5` per DONE-step |

**B3. VLA profiles.** The policy labels the agent sees are neutral names (K, R, T), permuted between replications.

| Parameter | Steady (A) | Hesitant (B) | Brittle (C) | Calibrated to |
|---|---|---|---|---|
| `m_W`, `s_W` | 240, 0.20 | 300, 0.30 | 260, 0.25 | real median first success 188 to 1,066 and CV 0.06 to 0.37 |
| Hover rate per 100, median, `s_h` | 0.15, 30, 0.5 | **1.0, 80, 0.6** | 0.15, 30, 0.5 | A and C: real still periods of at least 1 s, 0.09 per 100 steps, median 33, p90 68. B: **assumption**, standing for slow or invisible-progress phases (kettle, rinse, scrub, where "complete" was recognized 0.00 of the time) |
| Stuck rate per 100 | 0 | 0 | **0.5** | C: **assumption**, set so that plain success (0.26) sits at the real low end (0.17 to 0.33) |
| Restart break `z` | 0.02 | **0.15** | 0.01 | A: stage 2 reissue (5 against 2 failures over about 8 restarts each, about 2.5% per restart). B: upper end of the rewrite bracket (about 16% per rewrite in stage 3, confounded). C: assumption |
| Rescue `r_esc` | (no stalls to rescue) | (none) | **0.85** | **assumption**; rescue was never measured |
| Resulting T_c median, CV | 272, 0.20 | 538, 0.33 | 277, 0.22 (left alone, 0.29 reach success) | inside the real range |
| Always-defer success | 0.97 | 0.83 | 0.26 | real plain success 0.17 to 1.00; always-defer loses success 1 of 36 |

**B4. Interrupt (restart) model.** A `run_policy` that supplies any prompt after the first submission restarts the
policy, whatever the text, exactly as in `Runner.apply`. Each restart draws three uniforms from its own stream:

- **Break.** With probability `z` (plus `z_w` if the text is not the native goal), the state becomes BROKEN.
- **STUCK.** With probability `r_esc`, the policy escapes: DELAY(D), then WORK. Otherwise it stays STUCK.
- **RETREAT or DONE.** With probability `q_undo = 0.3`, the policy undoes its completion: `work_done = W - 40`,
  then DELAY(D). This is calibrated to stage 3's "achieved but not recognized" episodes (OpenCabinet, scrub,
  microwave), where 3 of 3 failed after several further restarts, and to reissue_100's success ratio (below).
- **HOVER.** DELAY(D), then the rest of the hover. A restart does not cure an apparent stall.
- **WORK or DELAY.** DELAY(D).
- **Delay.** `D = round(LN(40, 0.4))`, calibrated to stage 2 rewrites, which delayed success by 110 to 163 steps
  over several rewrites.
- **Wording surcharge `z_w` = 0 in the main experiment.** Rewording and restating cost the same. The real split is
  unmeasured, and the environment could not reward good wording in any case: it has no semantics. The dial is
  implemented, and whether the agent rewrites or restates is logged.

**B5. Checker and declaration.** Success means `complete` while the state is DONE, as in the real harness. Visual
completion (RETREAT) leads the checker by L steps, which reproduces "declared 12 to 48 steps before the checker
turned true". An exhausted budget is a failure.

**B6. What the LLM observes (perception model).** Text replaces images. Each frame is one reading of how far along
the task looks: `not started`, `early`, `midway`, `late`, or `looks complete`. Noise comes from its own stream,
keyed by absolute step, so two agents looking at the same step see the same reading.

- In RETREAT, DONE or LOST: `looks complete` with probability 0.70, otherwise `late`. Calibrated to the probe
  (about 0.70 after the checker, 0.66 in the last 20 steps before). A lost success stays invisible.
- In other states: `looks complete` with probability 0.30 if `W - work_done < 60`, otherwise 0.02. Calibrated to
  0.26 to 0.34 at 20 to 80 steps before the checker.
- Otherwise the reading is `q = work_done/W + 0.1·z`, binned at 0.2, 0.45 and 0.7. A stage lasts about 60 to 75
  work-steps, so identical readings during normal work are common. This reproduces Opus's "cannot tell progress"
  and "looks stalled" cues. The noise level is an assumption.
- There is no motion cue (point 3 of section 0).
- Each observation carries the current reading plus four keyframe readings at `start + n·i//5` (`i = 1..4`),
  strictly inside the interval. This is the same sampling rule as `Runner.apply` with `interval_keyframes=4`; on
  the first call there are no keyframes.
- **Legibility variants (defined, not in the main experiment).** *Hidden completion*: `looks complete` never
  appears (TurnOnMicrowave, rinse, scrub). *False positive*: 0.9 throughout (WashLettuce).

**B7. Agent interface (kept identical where it can be).**

| Element | Real harness | Environment |
|---|---|---|
| Operations, fields, ranges | `run_policy` with optional prompt, `steps` 1..400; `complete` | identical: `contracts.validate_decision` and `Limits(900, 100, 400)` |
| Restart semantics | any prompt restarts, even the same text; omitting continues | identical |
| Reply format and parsing | `DECISION_FORMAT`, `parse_decision_text`, transient retries | identical: reuse the functions |
| Invalid reply | consumes a decision, shown as `last_error` | identical |
| Model settings | effort `medium`, adaptive thinking (summarized), `max_tokens` 4,096 | identical |
| Sensors | 3 RGB views, proprioception, 4 keyframes per camera | one text reading, 4 keyframe readings |
| `history` (current episode) | decisions only | decisions **plus the reading returned after each one**, so the agent has the same memory as the reference policies. Recorded difference: the real harness drops earlier frames |
| Reference cards | native instruction, set-A performance | native instruction, `performance: null` (untested, per AGENTS.md) |
| New fields | none | `policy` (label), `episode`, `experience` (raw past episodes), score rules in the system prompt |

The system prompt is version 5 with three changes. The camera and proprioception paragraphs are replaced by the
perception description ("readings come from an imperfect perception system and can be wrong in either direction").
One paragraph is added: "you supervise several policies, named K, R and T, in interleaved episodes of the same
task. They differ in ability; you are not told how." The score is stated in dollars: **+$1.00 for a correct
completion declaration, -$0.02 per response (invalid ones included), -$0.002 per second of robot time (20 steps =
1 s); maximize the total.** The decision paragraphs stay verbatim. The baselines in `baselines.py` read only
`goal`, `remaining_steps`, `max_interval` and `active_instruction`, so they run unchanged.

**B8. Experience record and feedback.** After each episode the harness appends one raw record:

- the policy label;
- each decision (step, operation, prompt text, steps) with the readings it returned;
- the outcome (`success`, `false completion`, or `step budget exhausted`);
- steps, calls, and the episode's dollar score.

The record holds no harness-computed statistics, no latent states, no completion time and no parameters, so the
agent has to do the learning itself. Each past episode is a separate content block (about 180 tokens) placed after
the system prompt and before the current observation. The record is append-only, with a cache breakpoint on its
last block, so earlier episodes are cache reads. Showing outcomes **after** an episode is the one deliberate
exposure of task success. It cannot affect the episode it describes, it exists only in this study, and it is
recorded as a deviation from the benchmark rule.

**B9. Randomness and common random numbers.** Each episode seed drives three independent streams: (1) the latent
draws (W, hovers, stucks, L, E); (2) restart outcomes, indexed by the restart's position in the episode; and (3)
perception noise, indexed by absolute step. Every agent, baseline and probe therefore faces the same world.
Differences in outcome come from decisions only.

**B10. Reference policies and evaluator (CPU only, never shown to the agent, never mixed with model scores).**

- `always_defer` and `reissue_50/100/200` (the existing baseline classes).
- Fixed observers that look every 100, 200 or 400 steps.
- The fixed family F(t0, N, τ, rule): first look at t0, then every N; restart with the native goal if the highest
  visible stage has not risen for τ steps; declare on first sight of `looks complete` (`first`) or once it has
  held for 40 steps (`confirm`); complete with 1 step left.
- **π*_v**, the best F rule per VLA. This is the "hazard-optimal observer": its grid is fitted on 10,000 training
  seeds and scored on held-out seeds.
- **π_pool**, the best single F rule across the three VLAs: the best a non-adaptive supervisor can do.
- A **privileged oracle** that sees the latent state (an unattainable bound).
- An **Opus-like rule**, used as a calibration check: first look at 150, then every 150; declare at the first
  `looks complete`; reword whenever the visible stage did not rise.
- **Evaluator.** The advantage-sum regret estimator (section 2) and probe scoring.

**B11. Records.** Each episode keeps the same `result.json` fields as `Runner` where they apply: status, success,
physical success final and ever, steps, calls, prompt submissions, changes and restarts, intervals, rejected
replies, reply parse, usage and model seconds. Each episode also keeps the private latent trace, every request
and response, and the thinking summaries. Every attempted episode is preserved. Kind `sim_development`, output
under `runs/sim/`.

### Real-task qualities reproduced, and the check

| Quality | Real evidence | Mechanism | Prototype value |
|---|---|---|---|
| Visual completion leads the checker | probe: lead of about 20 steps; 5 early declarations 12 to 48 steps early | RETREAT(L) | an Opus-like rule on A fails 22%, 20 points of it early declarations (real fast visible tasks: 7 of 24, 6 of them early) |
| Apparent stalls that resolve on their own | Opus rewrote on "looks stalled" or "unclear progress" (14 of 48) on slow tasks and failed 7 of 10 there | B hovers plus restart fragility | Opus-like rule on B: 59% failure, 1.5 restarts per episode |
| Restarts cost something | reissue_100: 12 of 17 against defer 15 of 17 | z, D, q_undo | A: reissue_100 0.70 against defer 0.97 |
| Success can be lost | always-defer lost 1 of 36 (and 2 of 17 in stage 2) | loss hazard h | A: always-defer 0.97 (of 1.00 reached) |
| Variable completion time | CV 0.06 to 0.37 | LN work plus hovers | CV 0.20 to 0.33 |
| Motion is uninformative; failures keep moving | robot still 3 to 5%; 76 of 82 failures do not end still | no motion cue | (by design) |
| Spread of plain success | 0.17 to 1.00 | the profiles | 0.97, 0.83, 0.26 |

### Calibration targets (prototype, 2,000 held-out seeds per VLA)

Each cell is success / expected utility in $ / calls / robot steps.

| Policy | Steady (A) | Hesitant (B) | Brittle (C) |
|---|---|---|---|
| always-defer | 0.97 / 0.804 / 4.0 / 899 | 0.83 / 0.658 / 4.0 / 899 | 0.26 / 0.089 / 4.0 / 899 |
| reissue every 100 | 0.70 / 0.408 / 10.0 / 899 | 0.10 / -0.192 / 10.0 / 899 | 0.72 / 0.427 / 10.0 / 899 |
| reissue every 200 | 0.76 / 0.545 / 6.0 / 899 | 0.30 / 0.092 / 6.0 / 899 | 0.69 / 0.475 / 6.0 / 899 |
| observe every 200, never restart, confirm | 0.96 / 0.809 / 4.6 / 544 | 0.79 / 0.601 / 5.6 / 752 | 0.25 / 0.060 / 5.7 / 791 |
| Opus-like rule | 0.78 / 0.672 / 3.4 / 366 | 0.41 / 0.234 / 5.3 / 651 | 0.54 / 0.382 / 5.0 / 601 |
| π_pool = F(300, 300, τ 80, confirm) | 0.94 / 0.807 / 3.8 / 581 | 0.70 / 0.533 / 4.1 / 799 | 0.61 / 0.453 / 4.0 / 780 |
| **π*_v** | 0.98 / **0.887** / 2.5 / 445 | 0.81 / **0.654** / 4.0 / 816 | 0.73 / **0.540** / 5.8 / 731 |
| privileged oracle | 1.00 / 0.931 / 2.0 / 279 | 0.84 / 0.719 / 3.0 / 601 | 0.99 / 0.676 / 13.6 / 371 |

- **The best rules differ by VLA.** A: F(400, 100, never restart, first). B: F(400, 400, never restart, confirm),
  which is essentially leaving it alone. C: F(100, 200, restart after 80 steps without a visible rise, confirm).
- **Value of adaptation** (π*_v minus π_pool): **A 0.080, B 0.121, C 0.087** per episode.
- **The answers differ by VLA on identical kinds of situation.** For an apparent stall of 160 steps or more,
  restarting rather than continuing is worth -0.11 (A), -0.16 (B) and **+0.12 (C)**. At the first sight of
  `looks complete`, declaring now rather than waiting 40 steps costs 0.47 to 0.70 for every VLA. For the first
  interval, the best is 400 or more for A (0.888 against 0.80 to 0.84 for 300 or less), anything for B (flat
  within 0.02), and 100 for C (0.56 against 0.45 to 0.50).

Acceptance test for the implementation: on 2,000 held-out seeds, every success rate is within ±0.03 and every
utility within ±0.02 of this table, and the three stated orderings hold.

## 2. Decision 2: experiment protocol

### Agents

- **Opus 5.5** is the subject, for continuity with stages 2 and 3. Settings are as in the real harness: effort
  `medium`, adaptive thinking with summaries, `max_tokens` 4,096, the structured reply format, and no sampling
  parameters (they are rejected).
- **Haiku 5.5** repeats every part. It costs about 1/40 as much, debugs the harness, and gives a capability
  contrast.
- Both are charged the same nominal $0.02 per call in the score, so their decisions are comparable. Actual API
  dollars are reported separately.

### Part 1 (primary): log probes, "what does it infer from observed performance?"

- **Experience logs.** These are raw B8 records generated on CPU by an exploring behaviour policy: per episode, F
  with t0 drawn from {100..500}, N from {50..400}, τ from {80, 160, never} and the rule from {first, confirm}.
  The logs therefore show the consequences of both waiting and restarting, and of both declaration rules. Two
  independent log sets use different seeds and different label permutations. Levels are **0, 3 and 8 episodes
  per VLA**, interleaved in blocks of three. Each level is a prefix of the next, so the earlier levels are cache
  reads.
- **Situations.** Three classes, each generated from that VLA's own process by rule (first match in a fixed probe
  seed range):
  - S1, the start: choose the first interval.
  - S2, an apparent stall: the highest stage has not risen for at least 160 steps, the current reading is not
    `looks complete`, and at least 300 steps remain. Restart or continue, and for how long.
  - S3, the first sight of `looks complete`. Declare or continue.
- **Design.** 3 classes × 3 labels × 2 instances × 2 log sets at each of levels 3 and 8 (72 calls), plus 3 × 3 × 4
  at level 0 (36 calls). Total: **108 calls**.
- **Scoring.** Each answer gets its advantage against the best answer. Action values are latent-conditioned Monte
  Carlo estimates (K = 500 continuations under π*_v). For S1, the continuation is the best F rule with the
  answered t0. Averaging over instances gives the value for the situation class.

### Part 2 (secondary): closed-loop sessions, "does it act well when it must generate its own experience?"

- **Session.** 24 episodes, 8 per VLA, in 8 blocks of 3 with a seeded order inside each block. Episode seeds are
  the first 8 of a held-out range per VLA (chosen by rule, never by outcome).
- **Second session (conditional, see the stop rules).** The same seeds in reversed order within each VLA, new
  block orders and a new label permutation. Each seed is then early in one session and late in the other, which
  allows within-seed early-against-late contrasts.
- **End-of-session probes.** S1 to S3 × 3 labels, once each (9 calls).
- **Pilot (not analysed with the main data).** Haiku 5.5 runs one full session and the level-0 probes (smoke
  test). Opus 5.5 runs 6 episodes plus 9 probes on pilot seeds, to measure output tokens per call, parse rate and
  latency. Prompt or harness changes are allowed only before the main runs. Freeze after the pilot.

### Baselines and metrics

- **Baselines.** All CPU, on the same seeds plus 10,000 extra for exact expected values: always-defer, reissue
  50/100/200, fixed observers 100/200/400, π*_v, π_pool, the oracle, and the Opus-like rule.
- **Per-episode metrics.** Success; failure kind (early declaration with the latent state at that moment, never
  achieved, lost, broken, budget exhausted); robot steps; calls; nominal and actual dollars; intervals; restarts.
- **Restart quality.** Restarts are split by the latent state they hit: precision is the share that hit STUCK.
  Unnecessary restarts are those in HOVER, WORK or DONE. Undo events are counted.
- **Declaration timing** relative to visual and checker completion.
- **Primary performance metric: expected regret against π*_v.** The advantage-sum estimator is
  `-Σ_t [Q(s_t, h_t, a_t) - Q(s_t, h_t, π*_v(h_t))]` over the agent's decisions. The Q-values are Monte Carlo
  continuations of π*_v from the true latent state with fresh future randomness (K = 200). It is an unbiased
  estimate of the regret, by the performance-difference lemma and the tower property. In the prototype it cut
  variance by a median of about 2.5 times (1.3 to 6.5 times; in one of six cases it was 0.7, slightly worse).
  Realized paired regret against π*_v on the same seed is reported beside it.
- **Also reported.** Regret against π_pool (a negative value means the agent beat the best non-adaptive rule) and
  against the oracle.

### Analysis, fixed before any model call

- **Question (1), when to interrupt.**
  - S2 restart rate by label and level.
  - Part 2 restart precision and unnecessary restarts by VLA, first half against second half.
  - *Learned* means: at level 8 (and in the end probes) the agent restarts on C's stall instances and continues
    on B's in at least 3 of 4 answers per label, while at level 0 the labels do not separate them.
- **Question (2), how often to observe.**
  - S1 interval by label and level, against the per-VLA optima (A at least 400, C 100).
  - Calls and robot time against π*_v.
  - *Learned* means: at level 8 the first interval chosen for C is below the one chosen for A in at least 3 of 4
    paired answers, and the mean S1 advantage improves from level 0 to level 8.
- **Declaration.** The S3 wait rate rises with experience; waiting is correct for every VLA.
- **Adaptation.** Part 2 second-half regret against π_pool's regret for each VLA. The agent "adapts beyond any
  fixed rule" if it is below π_pool on at least 2 of 3 VLAs.
- **Reporting.** Counts first. Bootstrap over episodes within a session; sessions are too few for session-level
  intervals. With an advantage-sum standard deviation of about 0.1 to 0.4 per episode, 8 episodes per VLA give a
  standard error of about 0.04 to 0.14. That separates "near π*" (regret under 0.05) from Opus-like behaviour (0.2
  to 0.4); it does not resolve small learning slopes, which is why Part 1 carries the learning question.

### Noise control, in order of effect

1. Common random numbers (B9) for every agent and baseline.
2. Expected-value scoring (advantage-sum) and exact probe values: environment noise is removed from probes and
   reduced in sessions.
3. Fixed probe situations with nested experience levels: learning is measured as within-situation change.
4. Mirrored seed order across sessions, if the second session runs.
5. Repeats (instances × log sets) for the agent's own sampling noise, which temperature cannot reduce.
6. Seeds chosen by rule; π* fitted on training seeds and scored on held-out seeds.
7. No infrastructure noise: deterministic, CPU, resumable (decisions are replayed from the records to resume).

### Cost estimate

Prices are from the claude-api reference (cached October 6), per million tokens. Opus 5.5: $4 input, $20 output,
cache write $5, cache read $0.20. Haiku 5.5: $0.10 and $0.50.

Token sizes:
- system prompt: about 1,000 tokens;
- experience: about 180 tokens per past episode (at most about 4.3k);
- current episode: about 300 tokens;
- output, thinking included: **325 tokens central** (the real harness averaged 143 at the same effort) and **625
  pessimistic**.

That gives about $0.009 per Opus call centrally and $0.015 pessimistically. Output is about 75% of the cost.

| Item | Opus calls | Central | Pessimistic |
|---|---|---|---|
| Pilot: Opus 6 episodes plus 9 probes; Haiku full smoke | about 33 | $0.27 + $0.05 | $0.45 + $0.05 |
| Part 1 log probes (Opus) | 108 | $1.00 | $1.65 |
| Part 2, session 1 plus end probes (Opus) | about 105 | $0.90 | $1.53 |
| Haiku replicas of Parts 1 and 2 | (about 320 Haiku calls) | $0.20 | $0.20 |
| **Subtotal** | | **$2.42** | **$3.88** |
| Part 2, session 2 (conditional) | about 105 | +$0.90 | +$1.53 |

**Stop rules.**
- Hard stop at **$4.50** cumulative API spend, tracked from `usage` after every call.
- If the pilot's mean output exceeds 450 tokens per call, Part 1 drops the level-0 repeats from 4 to 2 (saving
  about $0.15 to $0.25).
- **Session 2 runs only if** cumulative spend after session 1 is at most $3.30 **and** Part 1 showed the agent's
  answers moving with experience in at least one class. If Part 1 shows no learning, a second closed-loop session
  cannot show it either.
- Per call, `max_tokens` stays at 4,096; rejected replies count.

GPU: $0. Wall time: under an hour on the Mac (about 5 s per call, sequential to keep caches warm).

### Implementation outline (for the build; not done here)

- **New package `src/robot_benchmark/sim/`:**
  - `process.py` (B2 to B4, B9);
  - `perception.py` (B6);
  - `harness.py`, a runner mirroring `Runner.run` and `Runner.apply` semantics and reusing
    `contracts.validate_decision` and `Limits`;
  - `agent.py`, a text adapter reusing `DECISION_FORMAT`, `parse_decision_text` and the retry logic, with cache
    breakpoints;
  - `references.py` (B10, grid search);
  - `evaluate.py` (advantage-sum, probe scoring).
- **Scripts:** `scripts/sim_probes.py` and `scripts/sim_session.py`.
- **Tests:**
  - CRN determinism;
  - parity of restart semantics and counters with `Runner` on identical decision sequences;
  - `baselines.py` agents running unchanged;
  - the calibration acceptance table.
  - Run `python -m unittest discover -s tests -v`.
- **Contract and records.** The package is outside the benchmark contract hash. The `sim_development` kind and
  the outcome-feedback deviation are recorded in `docs/decisions.md` when built, and results are never placed in
  a benchmark table.

### What this design cannot show

- **Real perception.** The probes measured it separately.
- **Real VLA dynamics beyond the calibrated qualities.** In particular, rescue (C) and long apparent stalls (B) are
  assumptions.
- **Transfer.** It does not show that conclusions hold for the real harness until that harness gets the same three
  additions and a small real check.
- **Generality.** Results are conditional on the stated exchange rates ($1 a success, $0.02 a call, $0.002 a
  robot-second). A CPU sensitivity table of π*_v at 0.5 and 2 times the call price is reported with the results.

## 3. Decision 3: no further real-robot measurement now

**Decision: take restart cost, wording sensitivity and undo-after-success as parameters with the brackets above.
Do not rent a pod for this study.**

Reasons:

- **The question does not need GR00T's point values.** The environment deliberately places its VLAs at different
  values of the restart dials (z = 0.01, 0.02, 0.15) to ask whether the agent learns which regime it is in.
  GR00T's exact value would locate GR00T in that space; it would not change whether the agent learns.
- **The run could not pin the dials down at the affordable size.** Stage 2's reissue contrast was 5 against 2
  failures on 17 pairs (p of about 0.45). About a dozen re-confirmed pairs with roughly 8 restarts each would give
  a per-restart break probability whose interval spans about 0.005 to 0.07, which is most of the bracket.
- **Budget.** The brief's version spends about $3 of the remaining $5 of API, leaving too little for the
  experiment that answers the user's questions. The GPU total would reach about $9.7. The last pod ran 13.75 h,
  about 2.75 times its planned length, because the Mac slept, and cost $7.5 against a $5 cap.
- **Setup overhead.** Start states are host-specific, so any new pod must first rerun plain and always-defer
  references (about 1.4 h of setup plus references) before a single attributable arm.

**Trigger.** Run real measurement only if:
- (a) a CPU sensitivity sweep shows that a Part 1 or Part 2 conclusion reverses within a dial's bracket (z 0.01
  to 0.15, q_undo 0.1 to 0.5, z_w 0 to 0.15); for example, if the best rule for B switches from never restarting
  to restarting; or
- (b) a claim specifically about GR00T is wanted.

**Minimal set if triggered. It is API-free: no model calls.**
- **Host re-confirmation.** Plain and always-defer on 12 pairs from fast, high-success tasks (OpenCabinet,
  OpenDrawer, the two pick-and-place tasks, CloseFridge).
- **Arms:**
  - restate-once at step 100 (single-restart cost: z and D);
  - paraphrase-once at step 100, with one hand-written paraphrase per task frozen before the run (z_w as the
    difference);
  - reissue_100 (restart dose);
  - restart-after-success: a privileged diagnostic that re-issues the goal 20 steps after the checker's first
    success (q_undo). It is diagnostic only and never mixed with model scores.
- **Replays.** `exact`, `native_text` and `no_interruption` replays of the stage 3 Opus rewrite episodes whose
  pairs re-confirm (at most 27 episodes). The logged decisions exist locally, so this needs no API.
- **Size.** About 100 episodes, about 3 pod-hours, **about $1.6 GPU, $0 API.**
- **Safeguards.** Watchdog armed for the run plus 30 minutes, the Mac kept awake and plugged in, results copied
  back after every phase.

## Assumptions stated instead of asked

1. **Profiles.** The user wants VLAs of different ability inside one study, labeled so that the agent can tell
   them apart. Three profiles are enough. One task with visible completion and a lag is enough; the
   hidden-completion and false-positive variants are follow-ups.
2. **Feedback and experience.** "Learned in context from observed performance" includes seeing each past
   episode's outcome after it ends. A raw experience record in every call counts as "one context window". It is
   cheaper than a literal multi-turn transcript (whose preserved thinking would grow the context by about 300 to
   600 tokens per call), and it matches the real harness's stateless calls. The agent's earlier private reasoning
   is not carried, as in the real harness.
3. **Exchange rates.** $1 per success, $0.02 per call (Opus measured $0.019) and $0.002 per robot-second. They
   are part of the environment's definition and are told to the agent.
4. **Calibration values.** Hover statistics for A and C come from commanded action magnitude, a proxy for visible
   motion. B's long apparent stalls, C's stuck rate and rescue probability, the perception noise level and the
   wording surcharge are assumptions, labeled as such. No unknown is set to zero as an estimate: `z_w = 0` is a
   design choice for the main experiment, not a claim that wording is harmless.
5. **Remaining budget.** About $5 of API remains, and no GPU will be rented without the trigger above.
