# The building blocks of the supervision environment (October 9, 2026)

> **Status, October 12.** These blocks describe the abstract simulator, which is now a development tool, not the
> benchmark (`docs/direction.md`). Blocks 2, 5, 6 and 7 carry over to the real-robot environment: checker lag,
> completion legibility, the decision interface, and a cost on every call, now as time on the task clock. Block 4's
> assumed rescue (0.85 per restart) is about ten times too optimistic against stage 4's real measurement.

What a simplified environment needs in order to test whether an LLM knows **when to interrupt** a learned robot policy
and **how often to observe** it, and where each block comes from. Specification and parameters: `docs/env_design.md`;
results: `docs/sim_results.md`; real-task evidence: `docs/stage3_results.md`. Blocks marked (assumed) are not measured.

| # | Block | What it is | Why it is needed (the evidence) |
|---|---|---|---|
| 1 | **Latent task process** | Progress that accumulates over steps, a completion time that varies by task (CV 0.06 to 0.37), and a state machine of working, pausing, stalled, visually complete, done, lost | Plain-policy success time varies 190 to 1,066 steps; the policy often hovers before acting; success can be lost |
| 2 | **Checker lag** | After the task looks finished, the official check turns true about 20 steps later (hidden post-conditions) | Opus declared 12 to 48 steps early in 5 of 19 episodes where it left the policy alone; the probe's "complete" rate rises from 0.3 to 0.66 in the last 20 steps before the checker |
| 3 | **VLA ability profile**, four independent dials | (a) stall rate that only a restart frees, (b) pauses that look like stalls but resolve (assumed), (c) restart fragility, (d) speed and variability. Three points in this space: steady, hesitant, brittle | Plain success ranges 0.17 to 1.00 by task; the best supervision rule differs by VLA (adaptation worth 0.05 to 0.13 per episode) |
| 4 | **Restart model** | Any prompt after the first restarts the policy, whatever the text. A restart costs a delay, can break the episode, frees a stalled policy with some probability (assumed), and can undo a completion | Rewriting episodes failed 9 of 14 against 5 of 19 when left alone; restarting every 100 steps failed 5 of 17 stage 2 pairs against 2. Wording and restart effects are not separable in the real data |
| 5 | **Perception channel** | One reading per look ("not started" to "looks complete"), imperfect in both directions, recognizing completion with probability about 0.7; variants where completion is never visible or always claimed | Completion probe: visible-state tasks recognized, hidden or cumulative ones never (RinseSinkBasin, ScrubCuttingBoard, TurnOnMicrowave 0.00), WashLettuce falsely complete 0.9; false negatives 36%, false positives 11% |
| 6 | **Decision interface** | `run_policy(prompt?, steps 1..400)` and `complete`; success only if the task is actually done when declared; step and decision budgets; same validation and keyframe rules as the real harness | Keeps results transferable to the real harness and lets the real baselines run unchanged |
| 7 | **Cost model** | Dollars: +$1 per correct declaration, -$0.02 per response, -$0.002 per robot second | Measured supervisor cost $0.019 per call; a call costs the equivalent of 200 steps of robot time, which is what drives agents to long intervals |
| 8 | **Experience channel** | Raw records of earlier episodes, each labeled by an anonymous policy name, with the outcome shown after the episode ends; policies interleaved in blocks | The real harness is stateless, so learning "from a VLA's observed performance" needs this. Not in the real harness |
| 9 | **Reference policies and evaluator** | Always-defer, fixed-interval observers, restart-every-N, a fixed-rule family fitted per VLA (pi*) and across VLAs (pi_pool), a privileged oracle; Monte Carlo action values for probes; advantage-sum regret for sessions | The only way to say whether a decision was good, not just whether the episode succeeded |
| 10 | **Noise control** | Common random numbers (the same world, the same readings for every agent), seeds chosen by rule, experience levels nested so learning is a within-situation change, repeats for the agent's own sampling | Real-robot runs were limited by unreproducible scenes, host-specific start states and rare renderer faults |

## What the first run says about the blocks

- Blocks 3 and 4 make "when to interrupt" a real decision: the best rule restarts stalled policies of one VLA and never
  those of the others. Opus learned that from records; Sonnet did not.
- Blocks 7 and 3 together expose the second failure: agents learn to save calls but not to look more often at an
  unreliable VLA, so they lose 0.34 to 0.55 on the brittle VLA against 0.13 for the best fixed rule.
- Blocks 2 and 5 reproduce the early-declaration and "cannot recognize completion" problems seen on real tasks; the
  probe agents mostly avoid the first when told readings are imperfect.
