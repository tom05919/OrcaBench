# Replay benchmark for done-detection and look scheduling (design, October 24, 2026)

Written by Tom's agent while Tom is away (Tom delegated judgment; important choices were voted on by three independent
reviewers, recorded at the end). Results are due October 26. Spending cap: $50 across Sail and Prime Intellect.

## Intent

The October 15-16 runs mixed three skills into one time-charged regret and could measure only one of them
(`docs/reanalysis.md`). Tom narrowed the question (October 23-24):

1. **Done-detection:** can the model tell from the cameras that the robot has finished the task?
2. **Look scheduling:** does the model choose how long to let the policy run before looking again, adapting to how
   fast and how reliable each (anonymous) policy is?

Re-prompting is dropped: these policies do not respond to better instructions (stage 6 ceiling test, 3/76 against
4/76), so only restraint could be measured. Opus and Sonnet are dropped; only open-weight models are evaluated.

## Why replay

Without re-prompting, the supervisor's only actions are "let it run N more steps" and "done". Neither changes what the
robot does, so a recorded uninterrupted run (an always-defer run of the plain policy) contains everything a live run
would. Every model sees the identical trajectory (no robot noise between models), runs can be repeated, the look cost
can be varied without robot time, and nothing needs a GPU. Fresh recordings were considered and rejected for the
October 26 deadline (pod setup, a hashed logging change and a new release would not fit).

## Data

- **Trajectories:** the always-defer runs of the add-on pod (`runs/addon/podC/always_defer`, 84, local) and pod B
  (`runs/final/podB/always_defer`, 84, from W3's draft release). Each has three 256 x 256 camera videos (one frame
  every 10 steps plus the final step) and the per-step checker log. Pod A's videos are in a private Hugging Face
  bucket this machine cannot read; they are not used.
- Scene 1003 is usable here: its exclusion came from pairing live sessions with twins, which replay does not need.
- Excluded: infrastructure errors and runs whose checker is true at step 0.
- Limitation: images only (joint readings were not logged densely in these runs); looks land on multiples of 10 steps.

## Models (Sail Research Messages API)

Vision-capable on Sail (probed October 24): `moonshotai/Kimi-K3`, `moonshotai/Kimi-K2.6`, `zai-org/GLM-5.3-Flash`,
`google/gemma-4-31B-it`, and `deepseek-ai/DeepSeek-V4.1-Flash-1017` (found October 25: the October 24 probe tested only
two of Sail's four DeepSeek models; added with the same prompt, settings and passes as Gemma, after GLM's sessions
stalled on Sail). Not usable: the other DeepSeek V4 models, GLM-5.3, gpt-oss-120b and Gemma 4 12B (no image input);
Qwen3.6-35B-A3B (Sail serves it only in an asynchronous mode). Sail serves quantized versions; results are for those.

## Part 1: done-detection probe (skill 1 alone)

One call per probe, no history: the task instruction and three images (the three cameras now; the three cameras 2 s
earlier; the three cameras 5 s earlier, each set tiled side by side into one image, so every model gets 3 images,
under Sail's 4-image limit for GLM-5.3-Flash). The model answers `{"done": true}` or `{"done": false}`.

- **Labels** come from the checker. Positive: a frame at or after the checker's first true step, while it is still
  true. Negative: a frame at least 40 steps (2 s) before the first true step, or any frame of a run that never
  succeeds. Frames in the 2 s before the first true step are not probed, because the checker lags visible
  completion by about 20 steps (stage 3).
- **Sampling** (fixed seed): per successful run, positives at the first true frame and 5 s later, negatives 2 s and
  10 s before; per unsuccessful run, negatives at the middle and at the end.
- **Measures:** accuracy, false "done" rate on negatives, missed "done" rate on positives; per task and per model.
- **Unreadable answers** (no JSON, or the reply limit of 6,144 tokens reached while thinking) count as wrong. The
  pilot (10 probes per model) found 4 of 30 replies cut off at 2,048 tokens, so the limit was raised before any
  scored run.

## Part 2: supervision sessions (skills 1 and 2 together)

- **Sessions:** one per (pod, scene), 21 trajectories in the frozen plan order (`configs/final/plans/scene*.json`:
  task blocks, anonymous policy letters). Every call is self-contained: earlier episodes and earlier looks are given
  as text; only the current look's 3 images are sent (same for every model, under the 4-image limit).
- **Episode:** at step 0 the model sees the task and the first frame and chooses `{"op": "wait", "steps": N}`
  (N from 10 to 400, rounded to a multiple of 10) or `{"op": "done"}`. At each look it sees the cameras now and at two
  earlier points of the last interval (3 tiled images), the step, the time left, the cost per look and its earlier
  looks. "Done" is scored by the checker at that step; reaching the step budget is a failure.
- **Experience:** before each episode the model sees one line per earlier episode of the session: policy letter, task,
  outcome (success / false "done" / ran out), when it declared and how many looks. This is the logged past-outcome
  exception (`docs/decisions.md`, 2026-10-13); nothing about the current episode's checker is shown.
- **Score:** value = success x max(0, 1 - (robot seconds + looks x c) / deadline), deadline = the task's step budget,
  c = a fixed cost per look, the same for every model (not each model's latency, which on Sail measures serving speed).
- **Baselines (no LLM):** the fixed timer (declare at step T, T chosen per policy and task without that scene); a
  perfect detector that looks every k steps (k chosen per policy and task without that scene), which is the bar for
  scheduling; and the oracle (declare at the first success with one look).
- **Measures:** value against the baselines; false "done" and missed "done" rates; detection lag; looks per episode;
  and adaptation: whether the model's first wait and its number of looks follow each policy's typical completion time
  (rank correlation over policy-task cells), and change between the first and second half of a session.

## Spending

A ledger prices every call from its reported usage at Sail's list prices (Kimi K3 $2.50 / $12.50 per million input /
output tokens; GLM-5.3-Flash $0.11 / $0.35; Gemma 4 31B $0.40 / $0.60; Kimi K2.6 assumed equal to K3). Runs stop
before the ledger would pass $45. No Prime Intellect spend is planned.

## Decisions put to the vote (October 24; three independent reviewers, unanimous on every item)

| Decision | Chosen | Reason (summarized) |
|---|---|---|
| Cost per look | 2 s for every model, plus a second pass at 6 s (cheap models first; Kimi K3 at 6 s only if the ledger allows) | Showing a different cost and checking whether the model looks less is the direct test of skill 2; replay can re-score other costs for free but not change behaviour |
| Models | Kimi K3, GLM-5.3-Flash, Gemma 4 31B; Kimi K2.6 dropped | Unknown price, same family as K3 |
| Repeats | Two passes per model at the main cost (at least for the cheap models) | Without them, model differences cannot be told from run-to-run noise |
| Past outcomes in sessions | Shown | Adaptation to anonymous policies is impossible without them; logged exception |
| Probe ambiguity band | 40 steps | Twice the ~20-step checker lag; frames come every 10 steps |
| Order if money runs short | Probe for every model first | Cheapest, isolates skill 1, and needed to read the sessions |

**Primary measures, fixed before any model call** (reviewers' D7 points):

- **Part 1:** balanced accuracy per model (mean of the hit rate on positives and the correct-rejection rate on
  negatives; positives come almost only from the 3 leave-alone tasks, so plain accuracy would mislead), with a 95%
  bootstrap interval clustered by recorded run.
- **Part 2 (c = 2 s):** on the 3 leave-alone tasks, the model's value minus the held-out perfect-detector baseline on
  the same recorded run (positive = the model scheduled better than the best fixed look interval with perfect
  perception), with a 95% bootstrap interval clustered by (task, scene). Both passes at c = 2 s are pooled (each pass is also
  shown). The baselines pay the same look cost as the model: the perfect detector pays one look at step 0 and one at
  every k steps until it declares; the timer pays two (step 0 and the declaration); the oracle pays two. Everything else is descriptive: false and
  missed "done" rates, detection lag, looks per episode, unseen tasks, the timer and oracle, the 6 s pass.
- **Adaptation is exploratory and low-power:** compared within a task block (the policy order inside a block) rather
  than first half against second half, because the plan runs tasks in blocks.
- **Checked:** the always-defer recordings run to the step budget after success (for example CloseFridge, scene
  1000, success with 899 recorded steps), so post-success frames exist; deadlines are the same `deadline_seconds`
  as the earlier score.

## Addendum, October 25: reasoning level (written before any reasoning-level run)

**What was missed.** The main runs sent no reasoning setting, so every model used Sail's default for it. That was not
a choice and was not recorded, and the defaults differ by model (one request per level on the same probe, October
25): Gemma 4 31B does not reason by default (6 output tokens, no thinking block), while Kimi K3, GLM-5.3-Flash and
DeepSeek V4.1 Flash return a thinking block by default. Consequences for the main runs, to be stated in the report:

- **Comparisons across models in the main runs confound the model with whether it reasons.** Kimi against Gemma is a
  reasoning model against a non-reasoning one.
- **The 6,144-token reply limit interacted with reasoning.** It cut off 20% of GLM's session replies (median 3,153
  output tokens) and 2-4% of Kimi's and DeepSeek's; a cut-off reply counts as unreadable.

**Decisions, each fixed before the runs it governs:**

1. **Levels:** `off` (thinking disabled), `low`, `medium`, `high`. For GLM-5.3-Flash, `minimal` replaces `off`,
   because Sail rejects disabling its reasoning. *Reason:* this spans no reasoning to high on every model. `xhigh` is
   left out for cost and latency. The main runs remain the `default` condition.
2. **Within-model comparisons only.** *Reason:* Sail maps each requested level to the model's own native tiers, so
   "high" on one model is not the same amount of reasoning as "high" on another.
3. **Record on every call:** the requested level, Sail's `stop_reason`, the length of any thinking block, output
   tokens and the number of attempts. *Reason:* a level only means something if it measurably changes the reasoning;
   these fields are the manipulation check, and `stop_reason` shows cut-offs directly instead of inferring them.
4. **Reply limit 32,768 tokens for every level run.** *Reason:* with a fixed low limit, higher levels would be
   penalized for being cut off rather than for their answers. The main runs stay at 6,144 and are reported as such.
5. **Per-call time limit 900 s, up to 4 attempts.** *Reason:* longer reasoning takes longer. A timed-out attempt is
   discarded and retried, so a short limit wastes calls: DeepSeek timed out on 5-8% of attempts at 180 s, and
   repeated timeouts stopped GLM's sessions on October 24.
6. **Pilot gate.** The same 10 probes for every model and level, unscored (pass 0). *Reason:* to confirm, before
   spending, that thinking length rises with the level, and to price the full runs. If two levels of a model give the
   same thinking length, the higher one is dropped for that model.
7. **Probe at every level for every model:** all 450 probes, one pass. *Reason:* recognizing "done" is where
   reasoning most plausibly helps, the probe isolates it, and it is cheap except for Kimi. Levels are compared on
   identical probes (paired).
8. **Sessions at `off` and `high` where the projected cost fits** the remaining budget, in priority order DeepSeek,
   Gemma, Kimi (Kimi only at `off`), and no GLM sessions. *Reasons:* Kimi's reasoning sessions cost about $40 per
   pass, which does not fit, while `off` costs about $8 because it produces almost no output. GLM's session calls took
   2-5 minutes each on Sail and its sessions stalled for hours on October 24, so they cannot finish by October 26.
   Two levels per model give the largest contrast for the money.
9. **Primary measures for this addendum.** Per model: probe balanced accuracy at each level, and the paired
   difference between `high` and `off` (or `minimal`), with a 95% bootstrap clustered by recorded run. For sessions:
   the leave-alone value minus the held-out perfect detector at each level. Everything else is descriptive. The noise
   reference is the difference between two default passes of the same model (Gemma and DeepSeek have two).
10. **Budget:** ledger cap $100 (Tom, October 25). The running default-condition GLM and DeepSeek runs are restarted
    with the same cap so that they do not stop when the ledger passes their old $70 cap. Restarting loses nothing,
    since every look is saved when it arrives.

### Pilot gate outcome (October 25, before any scored reasoning-level run)

Median thinking length per call on the same 10 probes (characters of the thinking block; `off` returns none):

| Model | off / minimal | low | medium | high | default (main runs; output tokens) |
|---|---|---|---|---|---|
| Kimi K3 | 0 | 361 | 361 | 1,445 | 394 tokens |
| GLM-5.3-Flash | 19 (minimal) | 0 | 136 | 172 | 714 tokens |
| Gemma 4 31B | 0 | 859 | 568 | 893 | 6 tokens (no reasoning) |
| DeepSeek V4.1 Flash | 0 | 2,621 | 1,568 | 1,511 | 266 tokens |

Every pilot reply ended normally (`stop_reason` `end_turn`); none was cut off at 32,768 tokens.

- **"Same thinking length", made operational now (the pre-run plan did not define it):** going up from the lowest
  level, a level is kept only if its median thinking length is at least 1.5 times that of the last level kept;
  anything under 50 characters counts as no reasoning. *Reason:* the pilot has 10 probes per cell, so small
  differences are noise; 1.5 times is a clear change.
- **Levels kept:** Kimi `off`, `low`, `high`; GLM `minimal`, `medium`; Gemma `off`, `low`; DeepSeek `off`, `low`. For
  GLM and Kimi, Sail's default reasons as much as or more than any explicit level (GLM's default produced a median 714
  output tokens against 46 at `high`), so the main runs are their highest-reasoning condition.
- **Sessions (decision 8) use `off` and the highest level kept,** since `high` was dropped for DeepSeek and Gemma:
  DeepSeek `off` and `low`; Gemma `low` (its `off` behaves exactly like its default, which already has two session
  passes); Kimi `off`. *Projected cost:* probe about $8, sessions about $10, for a ledger total of about $81 of the
  $100 cap.

### Third reasoning level for Kimi and Gemma (Tom, October 25, before any result at these levels)

- **Kimi K3 sessions at `low`,** added to `off` and `default`. *Reason:* three levels per model, as for DeepSeek.
  Kimi's `default` already reasons about as much as `high` (pilot: median 394 output tokens at default, 324 at
  `high`), so `off` / `low` / `default` spans none, little and much. An explicit `high` session pass (about $20) does
  not fit the $100 cap; `low` costs about $10. Caveat for the report: the `default` runs used the 6,144-token reply
  limit (2% of Kimi's session replies cut off), the level runs 32,768.
- **Gemma 4 31B at `high`,** probe and sessions, added to `off`/`default` and `low`. *Reason:* the pilot gate dropped
  `high` because 10 probes showed similar thinking lengths at `low` (859 characters), `medium` (568) and `high` (893).
  Ten probes is a small sample, so a full `high` pass tests that finding (about $1.50); if the levels really do not
  differ, that is reported as a property of how Sail serves Gemma's levels.
- **Projected ledger** with these: about $94 of the $100 cap.

### No cutoff (Tom, October 25, 12:30, before any reasoning-level result)

Every planned run continues until complete, including GLM-5.3-Flash's default sessions (about 74 calls an hour on
Sail, so likely finishing on October 26). *Reason (Tom's choice):* complete conditions over an earlier report. Each run
is restarted until nothing is left; an episode interrupted by a failure is replayed from its start, and its
interrupted looks stay on disk.

### Spending accounting and retries (October 25, 12:40, after the ledger reached the cap)

- **What happened.** The ledger booked every timed-out call at its worst case: the full reply limit at the model's
  output price, about $0.41 for a Kimi call allowed 32,768 tokens. With about 150 requests in flight at once, timeouts
  rose (602 in all), and their bookings ($28.92) pushed the ledger to the $100 cap while replies with reported usage
  totalled $72.26. The runs stopped there; nothing was lost.
- **Decision: count a timed-out call at the 99th-percentile cost of that model's replies in the same part and
  reasoning level** (its worst case while fewer than 20 such replies exist); the cap compares $100 with that
  estimate. *Reason:* Sail's documentation says a timed-out request may or may not have run, so some charge is
  possible, but a no-reasoning Kimi call costs about $0.003, not $0.41. The 99th percentile keeps the estimate
  conservative. The raw worst-case values stay in the ledger file, and the report gives both totals. Tom's Sail
  dashboard has the exact bill.
- **Decision: one idempotency key per call** (`anthropic-idempotency-key`), reused on every retry, waiting on HTTP 409
  while the original is still running. *Reason:* Sail's documentation: without a key, a retry after a timeout can start
  and bill a second generation; with one, Sail returns the original reply. This also recovers replies that previously
  arrived after the client had given up.

### Cap raised to $150 (Tom, October 25, 16:40)

Estimated spending reached the $100 cap at 13:17 with about $8 of planned work left (Kimi K3 without reasoning made
about 13 looks per episode, more than projected). Tom raised the cap to $150 to finish every planned condition.

### GLM-5.3-Flash sessions at `minimal` and `medium` (Tom, October 25, 20:25, before any result at these levels)

- **Added:** GLM sessions at `minimal` and `medium`, the two GLM levels the pilot gate kept, so that GLM has three
  session conditions like the other models (its `default` reasons heavily: median about 3,100 output tokens per
  session reply). *Reason:* at these levels GLM answers in a median of about 30 s for about $0.0001 per call (probe
  data), so both fit before the deadline for under $1, unlike its slow default.
- **Fallback (Tom):** if GLM's sessions are not complete when the final analysis is run on October 26, the main
  session comparison uses Kimi K3, Gemma 4 31B and DeepSeek V4.1 Flash, and GLM's sessions are reported as partial
  with their sample sizes. GLM's probe results (complete at every level) are reported either way.

### Full grid of reasoning levels; `default` off the level figures (Tom's review, October 25, 21:05)

- **What was wrong.** The pilot gate kept a level only if its thinking length differed clearly from the level below,
  judged on 10 probes. That left each model with a different set of levels (DeepSeek had no `medium` or `high`), which
  makes the comparison look arbitrary, and the figures showed Sail's `default` as if it were a level although Sail
  does not document what it is.
- **Decision: every model is run at the same standard levels,** `off` (GLM: `minimal`, since Sail rejects disabling
  its reasoning), `low`, `medium` and `high`, in both the probe and the sessions. Thinking length is reported per level
  as the check that the level changed the model's behaviour; it no longer decides which levels are run. *Reason:* a
  benchmark should apply one grid to every model; whether a provider's levels differ is itself a result to report.
- **Decision: `default` is not plotted as a level.** Sail does not document it, so it is identified empirically: its
  thinking length (output tokens) is compared with each explicit level's on the same probes, adding `xhigh` for Kimi
  and GLM, whose defaults produced more output than their `high`. The main runs that used `default` are reported
  separately, described by that comparison, and never pooled with an explicit level: they also used a 6,144-token
  reply limit instead of 32,768.
- **No result at the added levels has been seen.** They are added to make the design uniform, after preliminary
  figures for the other levels; every level gets identical settings.

### Final grid: none, low, high (Tom, October 25, 21:30) — supersedes the 21:05 grid

- **Levels, for every model, probe and sessions: `none` (thinking disabled), `low`, `high`.** GLM-5.3-Flash uses
  `minimal` for `none`, because Sail rejects disabling its reasoning; the report labels it as such. *Reason (Tom):* the
  same three levels for every model; `medium` and `xhigh` were not asked for and were stopped. Their partial data stays
  on disk and is not used.
- **`default` is excluded from the comparison** (not plotted, not mapped). The earlier main runs at `default` are
  mentioned only as earlier runs at an undocumented provider setting. GLM's `default` sessions were stopped to free
  Sail's GLM capacity for the grid.
- **Kimi K3 `high` sessions started** (~$20-25; within the $150 cap with `medium` dropped).
