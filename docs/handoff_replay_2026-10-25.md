# Handoff: replay benchmark (October 25, 2026, 21:15 EDT; grid corrected 21:30)

**Correction at 21:30 (Tom): the grid is exactly `none` (GLM: `minimal`), `low`, `high` for every model, probe and sessions. `medium` and `xhigh` runs were stopped (data unused); `default` is excluded entirely (no plotting, no mapping); GLM `default` sessions were stopped; Kimi `high` sessions are running (`runs/replay/run_kimi_high.sh`). Where sections below mention medium, xhigh, default mapping or a pending Kimi budget decision, this paragraph wins.**

For the next agent working with Tom (W1, project owner) on OrcaBench. Read this whole file first, then the design doc
`docs/superpowers/specs/2026-10-24-replay-benchmark-design.md` (every decision and its reason, in order).
Results are due **October 26** (Tom's class report).

## 1. How to work with Tom (learned the hard way)

- **Justify every design choice before you act on it,** in the design doc, with the reason. Tom was rightly angry that
  the reasoning level was never chosen or recorded, and that figures showed Sail's undocumented `default` as if it were a
  level. "Think about these justifications before you actually do them so the benchmark is actually designed well."
- **Uniform design across models** (same levels, same settings). Never let a noisy pilot rule give models different
  condition sets.
- **Be exactly honest about losses and mistakes.** Saying "no data was lost" when in-flight replies were lost was
  called a lie. Count precisely; state what was lost, what was kept, what it cost.
- **Push every commit to `w1-scoring` right away** (memory rule); merging/tagging needs Tom's approval.
- **Money:** Tom authorizes caps explicitly (now $150). Ask before exceeding. Use Sail Research credits; Prime Intellect
  credits are allowed but unused so far.
- **Figures must look like ML/robotics paper figures** (Tom's spec: labeled scatter with Pareto frontier, annotated
  heatmaps, small multiples, grouped dot/bar with CIs; minimalist; consistent model colors; never fabricate data or
  uncertainty). Load the `dataviz` skill before plotting. Check every rendered figure by eye for collisions.
- **When uncertain about an important decision while Tom is away,** have 3 independent subagents vote (done once,
  October 24; recorded in the design doc).

## 2. What the project is now

The original live-robot benchmark (October 15-16 runs, Opus/Sonnet/Kimi on GPU pods) is analysed in
`docs/reanalysis.md` (final: Opus 0.049 [0.004, 0.100], Sonnet 0.066 [0.016, 0.126], Opus − Sonnet −0.016
[−0.058, 0.028]; all lose to a fixed timer; regret is a poor headline). Tom then narrowed the question to two skills:

1. **Done-detection** ("is the task done now?") — the *probe*: 450 single-call questions per condition, labelled by the
   recorded checker (balanced accuracy, 95% bootstrap clustered by recorded run).
2. **Look scheduling** — *sessions*: the model chooses `wait N steps` or `done` while replaying a recorded robot run;
   21 episodes per session (frozen plan order, anonymous policy letters, past outcomes shown); value =
   success × (1 − (robot s + looks × 2 s)/deadline). Primary: leave-alone tasks, value minus the held-out
   perfect-perception detector (fixed look interval), clustered by (task, scene).

Re-prompting was dropped (policies don't respond to instructions). Opus/Sonnet dropped; open models only on Sail:
Kimi K3, Gemma 4 31B, DeepSeek V4.1 Flash 1017, GLM-5.3 Flash (only these four accept images on Sail; Qwen3.6 needs
an async mode). 168 recorded always-defer robot runs (84 add-on pod C, 84 pod B) are replayed; no GPU needed.

## 3. Code (all committed on `w1-scoring`)

| File | What |
|---|---|
| `src/robot_benchmark/replay_bench.py` | trajectories, on-demand frame decode (ffmpeg, PNG cache ≤64), probe sampling, Sail client (idempotency keys, retries incl. transient 400s, 409 wait, 404 → new key), `EFFORTS` (reasoning levels), `Ledger` (cap; timeouts counted at the condition's 99th-percentile reply cost), sessions |
| `scripts/replay_run.py` | `probe` / `sessions`, `--effort {default,off,minimal,low,medium,high,xhigh}`, `--pass`, `--cost-per-look`, `--cap`, `--timeout`, `--max-tokens`; resumes; outputs under `runs/replay/` (Git-ignored) |
| `scripts/replay_analyze.py` | summary JSON: probe (BA, contrasts), sessions (baselines, primary, adaptation within blocks), reliability, spend (raw and estimated) |
| `scripts/replay_figures.py` | 4 figures (probe accuracy by level; said-done heatmap; session value + looks trade-off; declaration timing) |
| `tests/test_replay_bench.py` | 20 tests; full suite `PYTHONPATH=src python3.12 -m unittest discover -s tests` (all pass) |

**The figure script still plots `default` as a level — this must change** (Tom's review): drop `default` from the
level figures; describe it separately (section 6).

## 4. Data and what is running (as of 21:15)

Outputs: `runs/replay/probe/[effort-<level>/]pass<N>/<model>.jsonl`, `runs/replay/sessions/c<cost>/[effort-<level>/]pass<N>/<model>/<pod>-scene<N>.jsonl`
(+ `.looks.jsonl`: every look, saved on arrival). `default` runs have no `effort-` folder. Pass 0 = pilots (never
analysed); pass 9 = the `xhigh` default-mapping subset.

**Complete (450 probes / 168 episodes):** all probes at off/low/high/default for Kimi; off/low/high/default ×2 for
Gemma; off/low/default ×2 for DeepSeek; minimal/medium/default for GLM. Sessions: Kimi default/off/low; Gemma
default ×2 (c=2), default c=6, low, high; DeepSeek off.

**Running** (each wrapped in a restart-until-complete loop, detached with `nohup caffeinate -i`):
- `runs/replay/run_finish2.sh`: DeepSeek default sessions (c2 pass1, c2 pass2, c6 pass1), DeepSeek low, GLM default.
- `runs/replay/run_glm_levels.sh`: GLM sessions minimal, medium.
- `runs/replay/run_grid.sh` (started 21:10): probes Kimi medium, Gemma medium, DeepSeek medium/high, GLM low/high;
  sessions Gemma off/medium, DeepSeek medium/high, GLM low/high.
- default-mapping probes: Kimi and GLM at `xhigh`, 150 probes, `--pass 9` (log `runs/replay/logs/default-mapping.log`).

**Not started — needs Tom's budget decision:** Kimi sessions at `medium` (~$11) and `high` (~$20-25). Estimated spend
at 21:15 was $108.15; everything else should end near $120-125; Kimi medium+high would reach ~$150-155, i.e. the
cap must rise a little above $150. Ask Tom before raising it.

**GLM fallback (Tom):** if GLM's sessions are not complete when the final analysis runs on October 26, the main session
comparison is Kimi, Gemma, DeepSeek; GLM sessions are reported as partial with n.

**Monitoring:** `runs/replay/logs/status.log` (one line per finished condition); `bash runs/replay/watch.sh` (run with
`run_in_background` so Tom sees it; it alerts on 45 min with no call or estimated spend > $145 — raise its threshold if
the cap rises). Progress check: count lines in the probe files and `"outcome"` lines in session files (not
`.looks.jsonl`).

## 5. Pitfalls already hit (do not repeat)

- **zsh does not word-split `$var`:** loops over levels must run in `bash` scripts.
- **`pkill -f <pattern>` kills any process whose command line contains the pattern,** including your own watcher. Kill by
  PID, or keep patterns out of other command lines (the watcher runs from a script file for this reason).
- **Memory:** caching whole decoded videos crashed the Mac twice (fixed: on-demand frames). Keep run processes ≤ ~20.
- **Sail quirks:** transient HTTP 400 (retry), 404 "response … not found" after a timeout with an idempotency key (new
  key), 409 while the original runs (wait), Gemma 400 "input exceeds the model's maximum context length" occasionally
  (retry works), GLM's default is very slow (~3,100 output tokens/reply).
- **Ledger:** raw file books timeouts at worst case; the cap uses the estimate (`Ledger(...).spent`). Report both.
- **Scratchpad is wiped on restart;** nothing important lives there.
- **Never print `.env`** (`SAIL_API_KEY`, `ANTHROPIC_API_KEY`).

## 6. What to do next (in order)

1. Get Tom's decision on Kimi medium/high sessions (and cap). If yes, start them with the same pattern as
   `run_grid.sh` (`--cap <new> --timeout 900 --max-tokens 32768 --effort medium|high`, workers 8).
2. When `status.log` shows every condition complete (or on October 26 per the GLM fallback), run
   `python3.12 -B scripts/replay_analyze.py --out results/w1/replay/summary.json`.
3. **Default mapping:** for each model, compare `default`'s output tokens with each explicit level's on the same probes
   (paired; for Kimi/GLM include the pass-9 `xhigh` subset). Preliminary: Gemma default = off (no thinking block, 6
   tokens); DeepSeek default ≈ low (341 vs 373 output tokens; 1,534 vs 1,555 thinking chars); Kimi default (473 tokens)
   > high (361); GLM default (502) ≫ high (~46 in the pilot). Report the mapping in a table; never pool default runs
   with a level (they used a 6,144-token limit).
4. Update `scripts/replay_figures.py`: explicit levels only, same level order for every model (off|minimal, low,
   medium, high); keep the stamp/collision fixes; re-render; inspect each PNG.
5. Write the report (`docs/replay_report.md`), Tom's requirement: **justify everything**, including what went wrong and
   was fixed (reasoning level unrecorded, pilot gate, ledger accounting, crashes, lost in-flight replies, timeouts).
   Pull reasons from the design doc. Sections: question and why replay; data; models and levels (with the
   manipulation check); measures and baselines; results per skill (with CIs); reasoning-level effects within model;
   reliability (timeouts, cut-offs, unreadable); spend; limitations; what was lost. Then publish/send to Tom.
6. Commit and push each step.

## 7. Preliminary findings (20:40 data; check against final)

- Probe: reasoning on raises balanced accuracy for Kimi (0.71 off → 0.77 low/high) and DeepSeek (0.69 → 0.76);
  Gemma flat (0.74-0.76); GLM best at medium (0.79). Models say "done" 62-80% of the time 2 s before success and
  36-50% on runs that never succeed.
- Sessions (leave-alone, c=2): every condition is below the perfect detector. Reasoning off → ~2× more looks, more
  often right when declaring (76-82% vs 58-70%), lower value; reasoning on → declares a few seconds early in 30-60%
  of episodes.

## 8. Final state at 21:50 (supersedes sections 4 and 6 where they differ)

**Decision (Tom, confirmed 21:50): the grid is `none` / `low` / `high` for every model, probe and sessions; GLM uses
`minimal` for `none`.** All four models accept `medium` on Sail, but adding it would have finished around midday
October 26 for about $147; Tom chose to keep three levels. Do not add levels.

**Stopped (data kept on disk, not used):** every `medium` and `xhigh` run; GLM `default` sessions; DeepSeek `default`
session runs (c=2 pass 1: 143/168, c=2 pass 2: 104/168, c=6 pass 1: 82/168). `default` is excluded from the comparison
entirely: not plotted, not mapped. The analysis and figures must use only `off` (GLM: `minimal`), `low`, `high`.

**Grid status at 21:50 (probe out of 450; sessions out of 168 episodes):**

| Model | none | low | high |
|---|---|---|---|
| Kimi K3 | probe ✓, sessions ✓ | probe ✓, sessions ✓ | probe ✓, sessions 50 (running, ~1 h) |
| Gemma 4 31B | probe ✓, sessions 115 (running, ~15 min) | probe ✓, sessions ✓ | probe ✓, sessions ✓ |
| DeepSeek V4.1 Flash | probe ✓, sessions ✓ | probe ✓, sessions 139 (running, ~2 h) | probe 147 (running, ~1 h), sessions 12 (running, ~4-5 h) |
| GLM-5.3 Flash (none = minimal) | probe ✓, sessions 107 (running) | probe ✓, sessions 64 (running) | probe ✓, sessions 39 (running, ~1.5 h) |

Expected: everything complete around **3-5 am, October 26**; estimated spend about **$135** of the $150 cap
($117.22 at 21:45). Running scripts: `run_grid.sh` (Gemma none sessions, DeepSeek high, GLM low/high),
`run_glm_levels.sh` (GLM minimal), `run_finish2.sh` (DeepSeek low; its default and GLM default loops were killed),
`run_kimi_high.sh`. Each condition writes a line to `runs/replay/logs/status.log` when complete.

**Next steps (replace section 6):**

1. When every grid cell is complete, run `python3.12 -B scripts/replay_analyze.py --out results/w1/replay/summary.json`.
   The script currently summarises every level it finds (including partial `medium` and the `default` runs): restrict
   the reported tables and the contrasts to `off`/`minimal`, `low`, `high` (filter, do not delete data).
2. Update `scripts/replay_figures.py` to plot only those three levels, in the same order for every model (label GLM's
   first level "none (minimal)"), drop all `default` handling, re-render, and inspect every PNG for collisions.
3. Write `docs/replay_report.md` with a justification for every decision (from the design doc), including the mistakes
   and their fixes, then send it and the figures to Tom. Commit and push each step.

## 9. Update, October 26, ~12:00

- **Every grid cell is complete except DeepSeek `high` sessions: 154 of 168 episodes** (short: pod B scenes 1001 (13/21),
  1002 (20/21), 1003 (17/21), pod C scene 1002 (20/21)). Their session threads died on Sail's 404 "response … not
  found" when it came on a first attempt (the client only resubmits under a new key after an earlier attempt); one
  remaining thread then hung for 77 minutes, which kept the restart loop from resuming. That process was killed at
  about 11:50; `run_grid.sh`'s loop restarted it (resuming the four sessions). Check `status.log` for
  "sessions deepseek-ai/DeepSeek-V4.1-Flash-1017 high"; if it stalls again, kill the replay process by PID and the loop
  will restart it.
- Estimated spend at 11:46: **$138.53** of the $150 cap.
- Possible small fix if needed: in `SailClient.call`, also resubmit under a new key on a first-attempt 404 "not found".
