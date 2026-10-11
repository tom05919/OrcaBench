# Stage 4 results: does a restart or a new wording rescue a plain-policy failure? (October 11, 2026)

A **diagnostic development run** (`llm_development`, `diagnostic_replay`, baselines). It follows
`docs/stage4_plan.md`, which fixed the selection rule and analysis before any result existed. Nothing here is a
benchmark score: one policy (GR00T N1.5), one model (Opus 5.5), one machine, one episode per arm per pair. Counts, not
rates.

Raw episodes (3.8 GB, 310 episodes) are Git-ignored in `runs/stage4_remote/` on the machine that ran it, and in the
private Hugging Face bucket (ask the person who ran it for access). Per-pair table: `runs/stage4_remote/analysis.json`
(`scripts/analyze_stage4.py`).

## What was run

| Phase | Episodes | Notes |
|---|---|---|
| Plain policy, 16 tasks x scenes 1000-1003 x policy seeds 0, 1 | 128 (46 solved) | 0 infrastructure errors |
| Selection: (task, scene) where both plain seeds failed, cap 2 per task | 22 failure pairs, 16 tasks | |
| Always-defer (continue, never restart) | 22 pairs | 21 failed from the identical start (reproducible failures); 1 never matched the start state |
| Restart with the native wording every 50 / 100 / 200 steps | 66 pairs x arms | |
| Opus 5.5 (effort medium, prompt v5) | 22 pairs | 148 calls, all strict JSON, 0 rejected |
| Replays of every Opus episode: exact, native_text, no_interruption | 57 | |

Every infrastructure error (34 episode attempts) was the start-state guard catching a scene mismatch before any model
call, all on the scenes Tom's stage 3 probe already flagged (sink and scrub tasks, TurnOnSinkFaucet). Each was retried
once; pairs whose arm never matched the plain run's start are `invalid` and excluded.

Machine: one RunPod RTX A6000 48 GB (via Prime), 16 vCPUs, four policy workers. Pipeline 04:44-07:21 UTC; the pod
uploaded its results and terminated itself at 07:21 (3.0 pod-hours, **$1.85**). Opus API at list price: **about $3.03**
(636k input, 24k output tokens).

## Result

On the 21 reproducible-failure pairs (the plain policy failed twice and always-defer failed a third time from the same
start):

| Arm | Usable | Rescued | Which pairs |
|---|---|---|---|
| Restart every 50 steps | 20 | **2** | TurnOffStove 1000, TurnOffStove 1001 |
| Restart every 100 steps | 19 | **1** | TurnOnMicrowave 1001 |
| Restart every 200 steps | 18 | **1** | CloseFridge 1003 |
| Opus 5.5 | 19 | **1** | OpenDrawer 1001 |

- **Restarts can rescue GR00T, rarely.** Four distinct pairs out of 21 were rescued by some restart schedule with the
  wording unchanged; no pair was rescued by more than one schedule. Each is a single episode with no repeat, so some of
  these may be lucky rollouts rather than a reliable effect of restarting. This is the first real evidence that a
  restart can turn a failure into a success. For scale: the simulator's brittle profile assumes each restart frees a
  stall with probability 0.85 (`sim/process.py`); here schedules of 2 to 33 restarts per episode each rescued 1 or 2 of
  about 20 failed episodes. The two are not directly comparable (not every real failure is a stall), but the real
  effect is much smaller than the assumption.
- **Opus rescued 1 of 19**, OpenDrawer 1001: it ran the native instruction, then rewrote it twice ("Grab the handle of
  the left drawer and pull it open", then a longer version) and declared completion at step 550. The `exact` replay
  reproduced the success; `native_text` (same timing, native wording) and `no_interruption` both declared early.
  Attributed to **wording**. One case.
- Opus changed the prompt on 19 of 19 usable pairs and restarted with unchanged text on 2. On the four pairs a fixed
  restart schedule rescued, Opus failed all four.
- Opus declared early once (WashLettuce 1000, step 1320 of 1650); the other 17 failures ran to the budget.
- The reply-format fix worked: 0 rejected replies in 148 calls, against 11 of 72 in stage 1.

## What this does and does not show

- It shows that restarts are not useless for GR00T on these tasks: 4 of 21 failure pairs were rescued by some fixed
  restart schedule, on four different tasks. Per `handoff.md` A.5, the brittle profile can stay, but its rescue
  probability should be recalibrated far down, toward these counts.
- It shows Opus does not find those rescues: it rewrote the prompt nearly everywhere, and its one rescue was by
  wording on a different pair.
- It does **not** show reproducibility of any single rescue (no repeats), or anything about Sonnet or other models.
- The `compare_to_reference.py` step failed for every arm: it reads `decisions.jsonl`, which a scene-mismatch episode
  never writes. `scripts/analyze_stage4.py` replaces it here; the compare script should skip such episodes.

## Suggested next steps

1. Repeat the four restart rescues and the Opus rescue (same pairs, three more episodes each, about 30 minutes of GPU)
   to see whether they are reliable.
2. Feed the measured restart rescue counts into the abstract environment's brittle profile and re-run the simulation
   with the call price varied (`handoff.md` A.5 item 2).
3. Fix `compare_to_reference.py` to skip episodes without `decisions.jsonl`.
