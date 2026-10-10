# Abstract-environment results: can an LLM learn when to interrupt and how often to observe? (October 9, 2026)

The study specified in `docs/env_design.md` (decided by an Opus design agent from `docs/env_design_brief.md`), built in
`src/robot_benchmark/sim/` and run on the CPU plus the Claude API. Records are `sim_development` and are never
benchmark scores. API spend for the study: **$2.22** (hard stop was $4.50); GPU: none. The environment is abstract:
the VLA and perception are parametric models calibrated to the real stage 2-3 data and the offline probes, and some
parameters are assumptions (listed below). Read the results as "what these models do in an environment built from
the measured qualities", not as measurements of GR00T.

## The environment, as built

Latent task process (work, pauses that resolve on their own, stalls only a restart frees, a visually complete state
that precedes the checker by about 20 steps, loss of success), three VLA profiles, a text perception model, the real
decision interface (`run_policy(prompt?, steps)`, `complete`, any prompt restarts), experience records, and a score in
dollars. The full specification is `docs/env_design.md`; the one-page summary is `docs/env_building_blocks.md`.

Calibration on 2,000 held-out seeds per VLA (success / expected utility):

| | Steady | Hesitant | Brittle |
|---|---|---|---|
| Always-defer (no intervention) | 0.97 / 0.80 | 0.82 / 0.65 | 0.29 / 0.12 |
| Restart every 100 steps | 0.68 / 0.39 | 0.10 / -0.19 | 0.69 / 0.40 |
| Best rule for this VLA (pi*) | 0.98 / **0.887** | 0.82 / **0.655** | 0.72 / **0.502** |
| Best single rule across VLAs (pi_pool) | 0.96 / 0.834 | 0.72 / 0.544 | 0.55 / 0.375 |
| Privileged oracle | 1.00 / 0.932 | 0.85 / 0.732 | 0.94 / 0.791 |

The best rule differs by VLA: wait about 400 steps and declare at the first sight of "looks complete" for the steady
one; look once at 100 then every 400 and leave it alone for the hesitant one; look every 100 and restart after 80
steps without visible progress for the brittle one. **Adapting to the VLA is worth 0.053, 0.111 and 0.127 per episode**
(a success is worth 1.0). A sweep over the dials the data does not pin down (the hesitant VLA's restart break
probability 0.01 to 0.30, the chance a restart undoes a completion 0.1 to 0.5, the wording surcharge 0 to 0.15) never
changed the best rule for any VLA and kept the value of adaptation positive (0.06 to 0.17), so the conclusions do not
depend on those restart dials. The sweep did not cover the brittle VLA's stall rate and rescue probability, which the
headline result (the only profile where supervision adds much value) rests on; no real-robot measurement of whether a
restart rescues GR00T was run (`handoff.md`, "Next steps", item 1). Calibration against the design's prototype is
within about 0.04 on success and up to 0.04 on the best rule's utility (0.08 on the pooled rule's, whose chosen rule
differs), not the planned 0.02; the orderings hold. The first two rows come from 500 seeds, the rest from 2,000.

## Part 1: log probes (108 answers per model, all valid)

The agent reads raw records of 0, 3 or 8 earlier episodes per VLA (each VLA once per block of three, policies named
K, R, T, with two label permutations) and answers three standard situations. Answers are scored against Monte Carlo
action values (0 is the best candidate).

| | Opus 5.5 | Sonnet 5.5 |
|---|---|---|
| **When to interrupt.** Share of apparent stalls it restarts, brittle VLA (its stalls are real), level 0 / 3 / 8 | 0.00 / **1.00 / 0.75** | 0.00 / 0.00 / 0.00 |
| Same, steady and hesitant VLAs (restarting is wrong) | 0 at every level | 0 at every level |
| **How often to observe.** First interval chosen (median), level 0 -> 8, steady / hesitant / brittle | 200 -> 350 / 400 / 350 | 200 -> 350 / 350 / 275 |
| Best first interval | 400 or more / any / **100** | |
| Declare at the first "looks complete"? Share that wait, level 0 -> 8 | 0.83 -> 0.83 | **0.25 -> 0.75** |

- **Opus learned when to interrupt.** With no experience it never restarts, even a genuinely stalled brittle policy;
  with 3 to 8 earlier episodes it restarts the brittle policy's stalls and never the others'. This meets the
  pre-declared criterion.
- **Neither model learned how often to observe.** Both lengthen the first interval for every VLA (200 steps with no
  experience, 275 to 400 with it), which is right for the steady and hesitant VLAs and wrong for the brittle one, where
  the best interval is 100. Opus's advantage on the brittle first interval got worse with experience (-0.01 to -0.11).
  The agent learns to save calls (a call costs the equivalent of 200 steps of robot time) but not to look more often at
  an unreliable VLA.
- **Sonnet learned only the declaration timing.** At level 0 it declares at the first sight in 100% of steady cases
  (advantage -0.97); with experience it waits. It never learned to restart.
- Opus mostly waits 20 to 60 more steps at the first sight of completion from the start (0.83 at every level), unlike
  the real harness's Opus, which declared 12 to 48 steps early in 5 of the 19 stage 3 episodes where it left the policy
  alone. That is only partly a finding about the model: this environment tells the agent that readings are noisy and
  states the costs, which the real harness does not.

## Part 2: closed-loop sessions (24 episodes, 8 per VLA, interleaved; the agent sees every earlier outcome)

Regret against the best rule for each VLA (advantage-sum estimate; lower is better). The best single rule's regret is
the reference: a negative gap means the agent beat what a non-adaptive supervisor can do.

| Session | Steady | Hesitant | Brittle |
|---|---|---|---|
| Best single rule (pi_pool) regret | 0.053 | 0.111 | 0.127 |
| Opus, session 1 (success; regret) | 1.00; 0.011 | 0.50; 0.066 | 0.38; **0.340** |
| Opus, session 2 (reversed seeds, new labels) | 1.00; 0.092 | 0.50; 0.012 | 0.50; **0.356** |
| Sonnet, session 1 (same seeds as Opus 1) | 0.88; 0.144 | 0.50; -0.045 | 0.38; **0.552** |

- On the steady and hesitant VLAs the agents are at or below the best single rule in most sessions; on the **brittle
  VLA they are far worse than any fixed rule in every session** (0.34 to 0.55 against 0.13).
- **No closed-loop learning curve.** Second-half regret on the brittle VLA is not lower than first-half in any session
  (0.24 -> 0.44, 0.31 -> 0.40, 0.39 -> 0.72); the other VLAs move up and down within noise. The probe result (Opus
  restarts a stall when shown one) does not carry into closed loop because the agent often does not see the stall in
  time: Opus's first interval on the brittle VLA is 250 to 310 steps against a best of 100, and 3 to 4 of its 8 brittle
  episodes in each session end with the policy still stalled. Sonnet restarted 0.25 times per brittle episode, and 3 of its 4
  episodes that ended stalled had no restart at all.
- Sonnet also declares early on the steady VLA (success 0.88, 325 steps used against Opus's 462).
- With 8 episodes per VLA the standard error of a regret estimate is about 0.04 to 0.14, so only the brittle gap and
  Sonnet's steady gap are clearly outside noise.

## What this shows for the user's two questions

1. **Does the agent know when to interrupt?** Opus learns, from raw records alone, to restart a policy that stalls
   when earlier episodes show restarts rescuing it, and never to restart the others. Sonnet does not. In neither model
   does this translate into good closed-loop supervision of the unreliable VLA.
2. **Does it learn how often to observe from a VLA's observed performance?** Not in these runs. It lengthens
   intervals to save calls for every VLA and does not shorten them for the unreliable one. This is the failure to fix
   or to build the benchmark around.

## What this does not show

- Real-robot transfer. The real harness has none of the three additions (experience, outcomes, dollar score), and
  perception is a calibrated model, so the conclusions hold for the environment as specified. They are consistent with
  the real stage 3 behavior (an Opus supervisor that rewrites, restarts and declares by phase of its looks), not proof of it.
- Calibrated VLA stalls. The hesitant VLA's long pauses, the brittle VLA's stall rate and rescue probability, and the
  perception noise level are assumptions; the sensitivity sweep covers the restart dials only.
- Statistical power. Probes have 4 answers per cell and 2 log sets; sessions have 8 episodes per VLA and two Opus
  sessions plus one Sonnet session. Opus's own sampling variance is untested beyond the mirrored session.
- Models other than Opus 5.5 and Sonnet 5.5, and prompts other than the one in `sim/agent.py`.

## Reproduce

```bash
PYTHONPATH=src python3 scripts/sim_calibrate.py --train 1000 --heldout 2000   # fits pi*, pi_pool; CPU
PYTHONPATH=src python3 scripts/sim_probes.py --model claude-opus-5-5 --output runs/sim/probes-opus.jsonl
PYTHONPATH=src python3 scripts/sim_session.py --model claude-opus-5-5 --output runs/sim/session-opus-1.jsonl
PYTHONPATH=src python3 scripts/sim_session.py --regret runs/sim/session-opus-1.jsonl
PYTHONPATH=src python3 scripts/sim_analyze.py --probes runs/sim/probes-opus.jsonl --session runs/sim/session-opus-1.jsonl
PYTHONPATH=src python3 scripts/sim_sensitivity.py
```
