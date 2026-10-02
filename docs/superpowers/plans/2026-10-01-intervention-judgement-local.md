# Intervention-Judgement Benchmark: Local Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement every part of the intervention-judgement benchmark that can be built and unit-tested without a GPU: seed separation, native goals, generic scoring, the task catalog, diagnostic supervisors, public baselines, screening/seed labelling, release freezing, the scorecard, and failure attribution.

**Architecture:** The existing synchronous `Runner` and two-operation interface stay. New logic lives in focused new modules (`tasks/predicates.py`, `diagnostics.py`, `baselines.py`, `screening.py`, `scorecard.py`); `cli.py` only wires them. Tasks 2–5 create new files only, so they can run in parallel after Task 1; Task 6 integrates.

**Tech Stack:** Python 3.11 standard library, `unittest`. RoboCasa/robosuite/MuJoCo and the policy worker are not installed locally; anything needing them is exercised with fakes and verified later on GPU.

**Spec:** `docs/superpowers/specs/2026-10-01-intervention-judgement-design.md`

## Global Constraints

- Project root `/Users/tomwang/robot_benchmark`; all files and caches under it.
- Run tests with `PYTHONPATH=src python3 -m unittest discover -s tests -v`; all must pass at the end of every task.
- Never expose reward, success, predicates, object coordinates, subtask labels, seed groups, or reference outcomes to a model adapter or to a non-privileged agent.
- No artificial disturbances, scripted manipulation, or training. Diagnostic supervisors may read simulator truth; their results are never mixed with model scores.
- Unknown performance is `null`/`"untested"`, never zero.
- Preserve every attempted episode, including infrastructure errors.
- Do not modify files owned by another task (listed per task). Do not `git commit`; the coordinator reviews and the user decides on commits.
- Match existing style: compact functions, short docstrings stating the contract, `ValueError` for contract violations.
- Pinned RoboCasa revision: `456174f62b89b8fca99eaaf33949c29fec9cfc2a`. Raw source: `https://raw.githubusercontent.com/robocasa/robocasa/456174f62b89b8fca99eaaf33949c29fec9cfc2a/<path>`. Read-only; do not vendor whole files.

## Shared data formats (all tasks rely on these)

**Episode directory** (written by `cli.run_episode` via `Records`):

- `manifest.json`: `{"artifact_type": "episode", "kind": str, "agent": {"kind": str, "model": str, ...}, "task": str, "seed": int, "scene_seed": int, "policy_seed": int, "contract_hash": str, ...}`. `seed` equals `scene_seed` (kept for backward compatibility).
- `result.json`: existing runner result plus `"goal": str`, `"scene_seed": int`, `"policy_seed": int`. Key fields: `status` in `{"success","false_completion","step_budget_exhausted","decision_budget_exhausted","infrastructure_error"}`, `success`, `physical_success_any`, `false_completion`, `steps`, `model_calls`, `prompt_submissions`, `prompt_changes`, `prompt_restarts`, `discarded_actions`, `intervals`, `usage`, `wall_seconds`.
- `policy_transitions.jsonl`: one row per prompt submission: `{"step", "previous_instruction", "instruction", "discarded_actions"}`.
- `evaluator/events.jsonl`: one row per evaluation: `{"step", "success", ...predicates}`.

**Kinds:** `diagnostic_reference` (plain VLA, privileged stop), `diagnostic_retry`, `diagnostic_sequencer`, `baseline_always_defer`, `baseline_reissue`, `llm_development`, `llm`.

**Seed-groups file** (`screening.label_seeds` output):

```json
{"schema_version": 1,
 "thresholds": {"trials": 5, "leave_alone_min": 4, "needs_help_max": 1, "rescue_min": 2,
                "min_per_group": 2, "max_per_group": 4},
 "tasks": {"KettleBoiling": {
     "qualified": true,
     "scene_seeds": {"1000": {"group": "leave_alone", "reference": [5, 5],
                              "retry": [0, 0], "sequencer": [0, 0]}},
     "selected": {"leave_alone": [1000, 1003], "needs_help": [1001, 1004]}}}}
```

`group` is one of `leave_alone`, `needs_help`, `medium`, `pending`. Pairs are `[successes, usable_trials]`.

---

### Task 1: Foundation: seed separation, native goals, generic scoring and config

**Owner of:** `src/robot_benchmark/runner.py`, `contracts.py`, `adapters/robocasa.py`, `feasibility.py`, `evaluation.py`, `cli.py`, `configs/splits.json`, `tests/fakes.py`, `tests/test_runner.py`, `tests/test_cli.py`, `tests/test_evaluation.py`, `tests/test_feasibility.py`, new `tests/test_robocasa_adapter.py`.

**Interfaces produced:**
- `Runner(..., goal: str | None, ...)`; `goal=None` means "after `env.reset`, use `env.native_instruction()`".
- `Runner.run(seed: int, policy_seed: int | None = None) -> dict`; result gains `goal`, `scene_seed`, `policy_seed`.
- `Environment.native_instruction() -> str` (protocol method).
- `RoboCasaEnvironment.evaluate()` → `{"success": bool, **task_predicates(task, raw)}` for every task (CerealAndBowl keeps its audited fields).
- `cli.task_parts(path) -> (config, reference_prompts, limits)` validates any schema-3 task config.
- `cli.run_episode(*, seed, policy_seed=None, ...)`.
- `splits.json` gains `screening_policy_seeds: [0,1,2,3,4]` and `reference_policy_seeds: [5,6,7,8,9]`.

- [ ] **Step 1: Write failing tests**

In `tests/test_runner.py` add:

```python
class SeedAndGoalTests(unittest.TestCase):
    def test_policy_seed_defaults_to_scene_seed_and_can_differ(self):
        for policy_seed, expected in ((None, 7), (3, 3)):
            policy = FakePolicy(chunks=[[action()]])
            env = FakeEnvironment()
            runner = make_runner([{"op": "complete"}], env=env, policy=policy)
            result = runner.run(seed=7, policy_seed=policy_seed)
            self.assertEqual(env.reset_seeds, [7])
            self.assertEqual(policy.reset_episode_seeds, [expected])
            self.assertEqual((result["scene_seed"], result["policy_seed"]), (7, expected))

    def test_native_goal_is_read_after_reset(self):
        env = FakeEnvironment(native="Open the left drawer.")
        runner = make_runner([{"op": "complete"}], env=env, goal=None)
        result = runner.run(seed=1)
        self.assertEqual(runner.agent.observations[0]["goal"], "Open the left drawer.")
        self.assertEqual(result["goal"], "Open the left drawer.")

    def test_blank_native_goal_is_an_infrastructure_error(self):
        runner = make_runner([], env=FakeEnvironment(native="  "), goal=None)
        self.assertEqual(runner.run(seed=1)["status"], "infrastructure_error")
```

Update `tests/fakes.py`: `FakeEnvironment(..., native="native goal")` with `native_instruction()` returning it; `FakePolicy` already records `reset_episode` seeds in `reset_episode_seeds`; `make_runner(..., goal="put the cereal and bowl on the counter and close the cabinet")` passing `goal` through.

In `tests/test_cli.py` add tests for `task_parts` on temporary config files: a valid native-goal config (fields below) passes; `max_interval != 400`, `interval_keyframes != 4`, `artificial_disturbances` true, a goal that is neither a nonblank string nor `null` with `goal_source == "native_instruction"`, and an empty `reference_prompts` list each raise `ValueError`; `configs/cereal_and_bowl.json` still passes and still rejects a changed CerealAndBowl prompt. Add a `validate_splits` test: shipped splits pass; overlapping `screening_policy_seeds`/`reference_policy_seeds` raise.

Valid native-goal config used in tests:

```python
NATIVE = {"schema_version": 3, "status": "candidate_unscreened", "task": "OpenDrawer",
          "task_set": "atomic_seen", "split": "pretrain", "goal": None,
          "goal_source": "native_instruction", "max_steps": 750, "max_decisions": 100,
          "max_interval": 400, "camera_size": 256, "video_record_interval": 1,
          "agent_image_history": "current_frames_plus_interval_keyframes_plus_decision_history",
          "interval_keyframes": 4, "artificial_disturbances": False,
          "reference_prompts": [{"id": "native_instruction",
              "prompt": "Use the goal text verbatim as the instruction.",
              "description": "Card for the native RoboCasa instruction shown as the goal.",
              "performance": {"status": "untested", "trials": 0, "success_rate": None, "conditions": []}}]}
```

New `tests/test_robocasa_adapter.py`: construct `RoboCasaEnvironment` via `object.__new__` (no simulator import), attach a fake `env` whose `unwrapped.env` has `_check_success()` and set `task`, `obs`. Test that `native_instruction()` returns `obs["annotation.human.task_description"]` stripped, raises `ValueError` when blank, and that `evaluate()` for a non-CerealAndBowl task returns `{"success": <bool>}` merged with `robot_benchmark.tasks.predicates.task_predicates` output, and rejects a predicate named `success`. Task 2 creates that module in parallel, so the test must not depend on it: use `unittest.mock.patch.dict(sys.modules, {"robot_benchmark.tasks": types.ModuleType("robot_benchmark.tasks"), "robot_benchmark.tasks.predicates": fake})` where `fake.task_predicates = lambda task, raw: {"kettle_on_stove": True}`.

In `tests/test_evaluation.py`: two episodes with the same `seed` but different `policy_seed` in one group must not raise "duplicate"; the same `(seed, policy_seed)` twice must.

- [ ] **Step 2: Run tests, confirm failures** (`PYTHONPATH=src python3 -m unittest discover -s tests -v`).

- [ ] **Step 3: Implement**

- `contracts.Environment`: add `def native_instruction(self) -> str: ...`.
- `runner.py`: `goal` may be `None`. In `run(self, seed, policy_seed=None)`: `policy_seed = seed if policy_seed is None else policy_seed`; after `env.reset(seed)`, if `self.goal is None`, set `self.goal = self.env.native_instruction()` and raise `ValueError("native instruction must be nonblank text")` if it is not a nonblank `str` (caught by the existing infrastructure-error handler). Call `self.policy.reset_episode(policy_seed)`. Add `"goal"`, `"scene_seed"`, `"policy_seed"` to the result.
- `adapters/robocasa.py`: add `native_instruction()` reading `self.obs["annotation.human.task_description"]`, returning stripped text, `ValueError` if blank. In `evaluate()`: keep the CerealAndBowl branch exactly; otherwise `success = bool(raw._check_success())`, `extra = task_predicates(self.task, raw)` (import `from ..tasks.predicates import task_predicates` inside the method), raise `RuntimeError` if `"success" in extra`, return `{"success": success, **extra}`.
- `feasibility.OrdinaryPolicySupervisor.decide`: when `active_instruction is None`, use the `full_task` reference prompt if present, else `observation["goal"]`.
- `cli.py`:
  - `task_parts`: generic validation. Required keys: `schema_version`(3), `task`(nonblank str), `split`(`"pretrain"`), `goal`, `max_steps`(positive int), `max_decisions`(100), `max_interval`(400), `camera_size`(256), `video_record_interval`(positive int), `interval_keyframes`(4), `agent_image_history`(the schema-3 string), `artificial_disturbances`(False), `reference_prompts`(nonempty list of objects with `id`,`prompt`,`description`,`performance`). Goal rule: nonblank string, or `None` with `goal_source == "native_instruction"`. If `task == "CerealAndBowl"`, additionally require the existing `SCORED_GOAL`, `(4350,100,400)` and the existing `REFERENCE_PROMPTS` check.
  - `validate_splits`: also require `screening_policy_seeds` and `reference_policy_seeds`: nonempty, unique ints in `[0, 2**32)`, disjoint from each other (they need not be disjoint from scene seeds).
  - `run_episode(*, seed, policy_seed=None, ...)`: manifest adds `scene_seed=seed`, `policy_seed=(seed if policy_seed is None else policy_seed)`; episode directory name `seed-{seed}-p{policy_seed}-{stamp}`; pass `task_config["goal"]` (may be `None`) and call `runner.run(seed, policy_seed)`. `infrastructure_result` gains `goal: None`, `scene_seed`, `policy_seed` (add parameters).
  - `feasibility` and `run` subcommands: optional `--policy-seeds` (parsed by `parse_seeds`); when given, run every `(scene, policy)` pair, scene-major order; otherwise legacy behaviour.
- `configs/splits.json`: add the two policy-seed lists.
- `evaluation.summarize`: duplicate detection keyed by `(seed, policy_seed)` using `manifest.get("policy_seed", manifest["seed"])`.

- [ ] **Step 4: Run full suite; all pass.**

---

### Task 2: Task catalog, predicates, and diagnostic supervisors

**Owner of (new files only):** `src/robot_benchmark/tasks/__init__.py`, `src/robot_benchmark/tasks/predicates.py`, `src/robot_benchmark/diagnostics.py`, `configs/tasks/*.json`, `docs/task_catalog.md`, `tests/test_task_catalog.py`, `tests/test_diagnostics.py`.

**Interfaces produced:**
- `tasks.predicates.CANDIDATE_TASKS: dict[str, str]` task → task set (`"atomic_seen"` or `"composite_seen"`).
- `tasks.predicates.task_predicates(task: str, raw) -> dict[str, bool]` (empty dict for tasks without predicates; never contains `"success"`).
- `tasks.predicates.SEQUENCES: dict[str, list[tuple[str, str]]]` composite task → ordered `(predicate_name, prompt)`.
- `diagnostics.PrivilegedRetrySupervisor(env, stall_steps=300, interval=50)` with `identity = {"kind": "diagnostic", "model": "privileged_retry_v1"}` and `decide(observation) -> ModelReply`.
- `diagnostics.PrivilegedSequencer(env, task, interval=50)` with identity model `privileged_sequencer_v1`.

**Candidate pool (16; the frozen release keeps 10):**
atomic_seen: `OpenDrawer`(750), `CloseFridge`(900), `TurnOnSinkFaucet`(600), `PickPlaceCounterToCabinet`(750), `TurnOnMicrowave`(450), `PickPlaceCounterToStove`(600), `CloseToasterOvenDoor`(450), `CoffeeSetupMug`(600), `TurnOffStove`(750), `OpenCabinet`(1050).
composite_seen: `ScrubCuttingBoard`(1200), `RinseSinkBasin`(1350), `KettleBoiling`(1500), `WashLettuce`(1650), `LoadDishwasher`(1800), `PrepareCoffee`(1800).
Horizons come from `vendor/reference/robocasa/robocasa/utils/dataset_registry.py`; verify each.

- [ ] **Step 1: Read upstream sources.** For each composite, fetch its file (paths: `robocasa/environments/kitchen/composite/sanitizing_cutting_board/scrub_cutting_board.py`, `cleaning_sink/rinse_sink_basin.py`, `brewing/kettle_boiling.py`, `making_salads/wash_lettuce.py`, `loading_dishwasher/load_dishwasher.py`, `brewing/prepare_coffee.py`) with `curl -s <raw-url>`; for atomic tasks read `robocasa/environments/kitchen/atomic/*.py` to confirm each class's `get_ep_meta()["lang"]` and `_check_success`. Also confirm in `robocasa/environments/kitchen/kitchen.py` that `use_novel_instructions` defaults to false. Record findings (native instruction text or template, checker summary, horizon, steps) in `docs/task_catalog.md`, one section per task, citing the file path and revision. If a checker enforces less than its instruction says, note it.

- [ ] **Step 2: Write failing tests.**

`tests/test_task_catalog.py`:
- every `configs/tasks/<Task>.json` name is in `CANDIDATE_TASKS` and vice versa (16 files);
- each config: `schema_version` 3, `goal` null, `goal_source` `"native_instruction"`, `max_steps` equals the registry horizon (parse `dataset_registry.py` with a regex `(\w+)=dict\(` … `horizon=(\d+)` as in the coordinator's survey), `max_interval` 400, `interval_keyframes` 4, `artificial_disturbances` false, `task_set` matches `CANDIDATE_TASKS`, first reference prompt id `native_instruction` with `performance.status == "untested"` and `success_rate` null;
- each composite's config contains one reference prompt per `SEQUENCES[task]` entry with identical prompt text, ids `step_1`…`step_n`, performance untested;
- `task_predicates("UnknownTask", object())` returns `{}`; for each composite, `task_predicates` called with a fake raw object (build it with `unittest.mock.MagicMock` and patch the `robocasa` helper functions the predicate uses) returns booleans keyed exactly by the `SEQUENCES` predicate names, never `"success"`.

Do not import `robocasa` at module import time in `predicates.py` (it is absent locally); import it inside each predicate function so tests can patch `sys.modules` or the helper.

`tests/test_diagnostics.py` (use a tiny fake env whose `evaluate()` returns a scripted dict):
- retry: first call issues `observation["goal"]` with `steps == min(50, max_interval, remaining_steps)`; continues without prompt while `success` false and steps since last prompt `< 300`; re-issues the goal once `>= 300` steps have elapsed since the last prompt; returns `{"op": "complete"}` as soon as `success` is true.
- sequencer: issues the prompt of the first `SEQUENCES` entry whose predicate is false; keeps it without re-prompting while that step is unmet; moves to the next step's prompt when its predicate becomes true; completes on `success`; if all predicates are true but `success` is false, keeps the last prompt without re-submitting it.
- both identities have `kind == "diagnostic"`.

- [ ] **Step 3: Implement** `predicates.py`, `diagnostics.py`, and the 16 config files (use the `NATIVE` config shape from Task 1 with `status: "candidate_unscreened"` and the correct `task`, `task_set`, `max_steps`, plus `step_k` prompts for composites). Step prompts should be short imperative sentences taken from the upstream docstring steps (e.g., KettleBoiling: `"Pick the kettle from the counter and place it on a stove burner."`, `"Turn the burner on."`). Predicates should mirror the conjuncts the upstream `_check_success` uses, one per sequence step, using the same `object_utils`/fixture helpers.

- [ ] **Step 4: Run full suite; all pass.**

---

### Task 3: Public baselines

**Owner of (new files only):** `src/robot_benchmark/baselines.py`, `tests/test_baselines.py`.

**Interfaces produced:**
- `AlwaysDeferAgent()` identity `{"kind": "baseline", "model": "always_defer_v1"}`.
- `ReissueAgent(every=100)` identity `{"kind": "baseline", "model": "reissue_every_100_v1"}` (embed `every` in the model name).
- Both: `decide(observation) -> ModelReply`; read only public observation fields (`goal`, `active_instruction`, `remaining_steps`, `max_interval`, `step`); no environment handle.

Behaviour (the runner ends the episode as soon as `remaining_steps` reaches 0, so `complete` must be sent while one step remains):
- AlwaysDefer: if `remaining_steps <= 1` → complete. Else `steps = min(max_interval, remaining_steps - 1)`; include `prompt = goal` only when `active_instruction is None`.
- Reissue: if `remaining_steps <= 1` → complete. Else `steps = min(every, max_interval, remaining_steps - 1)`; always include `prompt = goal`.

- [ ] **Step 1: Write failing tests** using `make_runner` from `tests.fakes` with the baseline as agent is not possible (it takes replies), so construct `Runner` directly: `Runner(FakeEnvironment(), FakePolicy(chunks=[[action()]*k]...), AlwaysDeferAgent(), reference_prompts(), "goal text", Limits(max_steps=250, max_decisions=100, max_interval=100))`. Assert: AlwaysDefer submits exactly one prompt (`result["prompt_submissions"] == 1`), ends with `status` in (`"success"`, `"false_completion"`) and `steps == 249`; Reissue with `every=100` has `prompt_submissions == 3` (steps 0, 100, 200) and `steps == 249`. Assert neither agent's `decide` reads keys outside the public set by passing an observation dict subclass that raises on unexpected keys. Assert identities.

`FakePolicy` pops supplied chunks and afterwards returns 4-action chunks indefinitely, so no chunk list is needed. Do not modify `tests/fakes.py`.

- [ ] **Step 2: Run, confirm failures. Step 3: Implement. Step 4: Full suite passes.**

---

### Task 4: Screening labels and release freeze

**Owner of (new files only):** `src/robot_benchmark/screening.py`, `tests/test_screening.py`.

**Interfaces produced:**
- `load_episodes(root: Path) -> list[tuple[dict, dict]]`: every `(manifest, result)` with `artifact_type == "episode"` under `root`; missing `result.json` becomes an infrastructure-error result.
- `label_seeds(episodes, policy_seeds: list[int], thresholds: dict | None = None) -> dict`: seed-groups file (format above). Uses only episodes whose `policy_seed` is in `policy_seeds` (screening set A).
- `freeze_release(groups: dict, task_configs: dict[str, dict], reference_policy_seeds: list[int], models: list[str], contract_hash: str) -> dict`.

Rules for `label_seeds` (defaults are the shared thresholds):
- Per `(task, scene_seed)`, count usable (`status != "infrastructure_error"`) episodes and successes for each kind: `diagnostic_reference` → `reference`, `diagnostic_retry` → `retry`, `diagnostic_sequencer` → `sequencer`.
- `pending` if reference usable trials `< 5`.
- `leave_alone` if reference successes `>= 4`.
- `needs_help` if reference successes `<= 1` and (retry has `>= 5` usable trials with `>= 2` successes, or sequencer does).
- `medium` otherwise (including `<= 1` without rescue evidence).
- `qualified` if `>= 2` leave_alone and `>= 2` needs_help; `selected` takes the lowest-numbered `max_per_group` (4) seeds of each group, only for qualified tasks.
- Reject duplicate `(task, scene_seed, policy_seed, kind)` with `ValueError`.

`freeze_release` returns `{"schema_version": 1, "status": "frozen", "created_at": <utc iso>, "contract_hash", "models", "reference_policy_seeds", "tasks": {task: {"config": <config>, "leave_alone": [...], "needs_help": [...]}}}` for qualified tasks only; raise `ValueError` if fewer than 10 tasks qualify unless `allow_fewer=True` (keyword, default False), and if `reference_policy_seeds` overlaps the thresholds' screening seeds recorded in `groups["screening_policy_seeds"]` (have `label_seeds` record that list).

- [ ] **Step 1: Write failing tests** with synthetic `(manifest, result)` tuples covering each group, pending, duplicates, infrastructure errors not counted, qualification, selection cap and ordering, `freeze_release` under/over 10 tasks and the overlap check, and `load_episodes` on a temporary directory with one missing `result.json`.
- [ ] **Step 2: Run, confirm failures. Step 3: Implement. Step 4: Full suite passes.**

---

### Task 5: Scorecard and failure attribution

**Owner of (new files only):** `src/robot_benchmark/scorecard.py`, `tests/test_scorecard.py`.

**Interfaces produced:**
- `load_scored_episodes(root: Path) -> list[dict]`: per episode `{"manifest", "result", "transitions": [...], "success_steps": [...]}` (`success_steps` = steps in `evaluator/events.jsonl` where `success` is true). Do not load images.
- `scorecard(episodes: list[dict], release: dict, bootstrap_samples=2000, rng_seed=0) -> dict`.
- `attribute_failure(episode: dict, group: str, paired_reference: dict | None) -> str`.

Scorecard semantics:
- Only episodes whose task and scene seed are in the release (`leave_alone`/`needs_help`) and whose `policy_seed` is in `release["reference_policy_seeds"]` count.
- Systems are keyed by `(kind, agent.model)`; `diagnostic_reference` episodes form the reference, never a system row.
- Per system and group: attempted, infrastructure errors, usable, successes, success rate, Wilson 95% (reuse `evaluation.wilson_interval`), false completions, no-declaration count (`step_budget_exhausted` + `decision_budget_exhausted`), totals and means of model calls, steps, prompt submissions/changes/restarts, discarded actions, token usage (reuse the summing approach in `evaluation._usage_totals`), wall seconds.
- Per system: `harm` on leave_alone = reference rate − system rate; `rescue` on needs_help = system rate − reference rate. Rates are pooled over usable episodes. 95% interval by seed-clustered percentile bootstrap: resample `(task, scene_seed)` clusters with replacement using `random.Random(rng_seed)`, recompute both pooled rates from the resampled clusters' system and reference episodes.
- `attribution`: counts of `attribute_failure` labels over failed usable system episodes.
- Output also includes `"note"`: diagnostic reference is privileged and not a model result; scores are conditional on the executor and task set.

`attribute_failure` rules, first match wins:
1. `status == "false_completion"` → `"false_completion"`.
2. `physical_success_any` and status is a budget exhaustion → `"missed_completion"`.
3. `deviation_step` = step of the first transition after the first one, or of the first transition whose `instruction != result["goal"]`, whichever is earlier (None if neither). If `deviation_step is not None` and the paired reference (same task, scene seed, policy seed, kind `diagnostic_reference`) has a first success step `s` and `deviation_step < s` → `"unnecessary_intervention"`.
4. `group == "needs_help"` and `deviation_step is None` → `"missed_intervention"`.
5. Otherwise `"executor_or_other"`.

- [ ] **Step 1: Write failing tests** with synthetic episodes: each attribution rule; harm/rescue values on a hand-computed example (e.g., reference 9/10 vs system 5/10 on leave_alone → harm 0.4); bootstrap interval brackets the point estimate and is deterministic for a fixed `rng_seed`; episodes outside the release or with non-reference policy seeds are excluded; reference episodes never appear as systems; infrastructure errors counted separately; `load_scored_episodes` on a temporary episode directory.
- [ ] **Step 2: Run, confirm failures. Step 3: Implement. Step 4: Full suite passes.**

---

### Task 6: CLI integration, contract files, and documentation (after Tasks 1–5)

**Owner of:** `src/robot_benchmark/cli.py`, `docs/decisions.md`, `docs/protocol.md`, `README.md`, `tests/test_cli.py`.

- [ ] **Step 1: Write failing tests** in `tests/test_cli.py` for argument parsing and dispatch of the new subcommands (patch `run_episode` and `RemotePolicy` so no network or simulator is touched): `screen` runs every `(task, scene, policy, kind)` combination requested and passes `video_record_interval` override; `label-seeds` and `scorecard` read a temporary run directory and write JSON; `freeze-benchmark` writes a release; `baseline` agents dispatch by name; and all shipped `configs/tasks/*.json` pass `task_parts`.
- [ ] **Step 2: Implement**
  - `CONTRACT_FILES` += `tasks/predicates.py`, `diagnostics.py`, `baselines.py`, `scorecard.py`, `screening.py`, `feasibility.py`.
  - `screen --task-configs <paths...> --scene-seeds <list> --policy-seeds <list> --mode reference|retry|sequencer --output <dir> [--video-record-interval N]`: kinds `diagnostic_reference` (OrdinaryPolicySupervisor), `diagnostic_retry`, `diagnostic_sequencer` (only for tasks in `SEQUENCES`). The override is recorded in the manifest.
  - `baseline --task-configs ... --scene-seeds ... --policy-seeds ... --agent always_defer|reissue --output ...` (kinds `baseline_always_defer`, `baseline_reissue`).
  - `run` accepts `--task-config` for any task and `--policy-seeds`.
  - `label-seeds <root> --splits <path> --output <path>` (uses `screening_policy_seeds`).
  - `freeze-benchmark --groups <path> --task-configs <paths...> --splits <path> --models <ids...> --policy-url <url> --output <path> [--allow-fewer]`.
  - `scorecard <root> --release <path> --output <path>`.
- [ ] **Step 3: Docs.** `docs/decisions.md`: one dated row each for native goals, generic official-checker scoring, scene/policy seed separation, new diagnostics and baselines, per-task native-instruction cards, candidate pool. `docs/protocol.md`: benchmark section describing groups, conditions, scoring. `README.md`: short "Intervention-judgement benchmark" section with the command sequence: screen → label-seeds → screen reference on set B → freeze-benchmark → baseline/run → scorecard. Label everything as not yet GPU-verified.
- [ ] **Step 4: Full suite passes; `python3 scripts/bootstrap_gpu.py --dry-run --skip-gpu-check` still succeeds.**

## Execution order

Task 1 and Tasks 2–5 can start together: Tasks 2–5 only create new files and depend on Task 1 solely through the formats above. Task 6 starts after all five pass review.

## Not in this plan (needs GPU)

Verifying predicates and native instructions against the real simulator, screening, freezing, and model runs.
