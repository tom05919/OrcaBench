# Candidate task catalog

Candidate pool of 16 RoboCasa365 tasks (10 `atomic_seen`, 6 `composite_seen`); the
frozen release keeps 10 after screening. Configs live in `configs/tasks/<Task>.json`
(`status: candidate_unscreened`, `goal: null`, `goal_source: native_instruction`).
Each config's `reference_prompts` contains only the `native_instruction` card. Its
prompt is the literal template `"{goal}"`; the runner shows the episode's native goal
text in its place in each observation. `publish-cards` fills in its performance after
screening.
Composite predicates and diagnostic step prompts live in
`src/robot_benchmark/tasks/predicates.py`; the diagnostic supervisors in
`src/robot_benchmark/diagnostics.py`.

All findings below come from reading upstream source at the pinned revision
`456174f62b89b8fca99eaaf33949c29fec9cfc2a` (`https://raw.githubusercontent.com/robocasa/robocasa/<rev>/<path>`).
Horizons come from `vendor/reference/robocasa/robocasa/utils/dataset_registry.py`
(the same revision); every horizon in the brief was verified there.

**Verification status.** RoboCasa is not installed locally. The predicates were checked
only against source reading and mocked unit tests. Source inspection and mock tests do
not qualify them: each predicate must be checked against `_check_success` in the real
simulator on GPU before any diagnostic result is relied on.

## Shared findings

- `Kitchen.__init__` (`robocasa/environments/kitchen/kitchen.py`) defaults
  `use_novel_instructions=False`, so composites use the fixed template below. The atomic
  classes listed here never consult the flag; they always set the template. Nothing in
  this repository passes the flag.
- robosuite calls `reward()` → `_check_success()` on every step from `_post_action`, and
  `Kitchen._post_action` then calls `update_state()`. Several composite checkers keep
  episode-cumulative state there (`washed_loc`, `washed_time`, `board_contact_*`), so
  their predicates read those attributes rather than recomputing from the current pose.
  These are private upstream attributes, and a revision change can break them.
- `OU.gripper_obj_far(env, obj_name="obj", th=0.25)` and fixture `gripper_button_far`
  conjuncts mean that many checkers require the robot to move away after the action.
  That is more than the instruction says. The sequencer has no separate step for this.
  When every step predicate is true but `success` is false, it keeps the last prompt
  and does not re-submit it.
- Default door thresholds (`models/fixtures/fixture.py`): `is_open` needs every door
  joint at ≥0.90 of normalised range; `is_closed` needs every joint at ≤0.005.

## Diagnostic sequences (composites)

**Privileged.** These step prompts are a subtask decomposition derived from upstream
annotations, and the judgement the benchmark measures includes working this
decomposition out. They live only in `tasks.predicates.SEQUENCES`, which only the
diagnostic sequencer and offline attribution use. They must never appear in a task
config, an observation, or anything else a model adapter can see. Task configs list
only the `native_instruction` card, and `tests/test_task_catalog.py` enforces this.

The design rule is one step per checker conjunct (merging conjuncts that describe one
physical step). Each step prompt is a short imperative paraphrase of the upstream
docstring step. Two kinds of docstring steps have no conjunct of their own. A step that
precedes another (picking up the sponge) is merged into the following step's prompt. A
precondition implied by a conjunct (water on) becomes its own step. The sequencer
prompts the first step whose predicate is false, so if an earlier step regresses, its
prompt comes back.

| Task | step | predicate | prompt |
|---|---|---|---|
| ScrubCuttingBoard | 1 | `board_scrubbed` | Pick up the sponge from the counter and scrub the cutting board. |
| | 2 | `sponge_released` | Place the sponge down. |
| RinseSinkBasin | 1 | `water_on` | Turn on the sink. |
| | 2 | `basin_rinsed` | Move the spout left and right to rinse all locations of the sink basin. |
| KettleBoiling | 1 | `kettle_on_burner` | Pick the kettle from the counter and place it on a stove burner. |
| | 2 | `kettle_burner_on` | Turn the burner on. |
| WashLettuce | 1 | `water_on` | Turn on the sink. |
| | 2 | `lettuce_washed` | Wash the lettuce under the sink. |
| LoadDishwasher | 1 | `dishes_on_rack` | Take the dishes from the counter and place them on the top rack of the dishwasher. |
| | 2 | `dishwasher_closed` | Close the dishwasher fully. |
| PrepareCoffee | 1 | `mug_under_dispenser` | Pick the mug from the cabinet and place it under the coffee machine dispenser. |
| | 2 | `machine_on` | Press the start button. |

## Atomic tasks (`atomic_seen`; no predicates, `task_predicates` returns `{}`)

### OpenDrawer — horizon 750
Source: `robocasa/environments/kitchen/atomic/kitchen_drawer.py` (`ManipulateDrawer`, behavior `open`).
Instruction: `"Open the {left|right} drawer."`. `drawer_side` is set when the robot is placed, so it depends on the seed.
Checker: every drawer joint must reach ≥0.95 of its normalised range. This is stricter than the generic 0.90.

### CloseFridge — horizon 900
Source: `atomic/kitchen_doors.py` (`CloseFridge(CloseDoor)`, fixture `FRIDGE`).
Instruction: `"Close the {fridge nat_lang} {door|doors}."` (it says "doors" for `FridgeFrenchDoor`).
Checker: `fxtr.is_closed(env)`, which requires every door joint at ≤0.005.

### TurnOnSinkFaucet — horizon 600
Source: `atomic/kitchen_sink.py` (`ManipulateSinkFaucet`, behavior `turn_on`).
Instruction: `"Turn on the sink faucet."`.
Checker: `sink.get_handle_state(env)["water_on"]`, which means the handle angle is in (0.40, π).

### PickPlaceCounterToCabinet — horizon 750
Source: `atomic/kitchen_pick_place.py`.
Instruction: `"Pick the {obj} from the counter and place it in the cabinet."`. The cabinet door is opened during setup.
Checker: `OU.obj_inside_of(obj, cab)` and `OU.gripper_obj_far` (0.25 m). The release requirement is not stated in the instruction.

### TurnOnMicrowave — horizon 450
Source: `atomic/kitchen_microwave.py` (`MicrowavePressButton`, behavior `turn_on`).
Instruction: `"Press the start button on the microwave."`.
Checker: `microwave.get_state()["turned_on"]` and `gripper_button_far(start_button)`. The hand must also leave the button.

### PickPlaceCounterToStove — horizon 600
Source: `atomic/kitchen_pick_place.py`.
Instruction: `"Pick the {obj} from the plate and place it in the {pan}."`.
Checker: `OU.check_obj_in_receptacle(obj, "container", th=0.07)` (the container is the pan on the stove) and `gripper_obj_far`.
Note: the object starts in a counter receptacle sampled from the `container` group (`try_to_place_in`). I have not verified that this receptacle is always a plate, as the instruction says.

### CloseToasterOvenDoor — horizon 450
Source: `atomic/kitchen_doors.py`.
Instruction: `"Close the toaster oven door."`.
Checker: `toaster_oven.is_closed(env)`, using the default ≤0.005 threshold.

### CoffeeSetupMug — horizon 600
Source: `atomic/kitchen_coffee.py` (`PickPlaceCoffee`, behavior `counter_to_machine`).
Instruction: `"Pick the {mug} from the counter and place it under the coffee machine dispenser."`.
Checker: `coffee_machine.check_receptacle_placement_for_pouring(obj)` (xy within 0.04 m of the pour site and |dz| < 0.10 m) and `gripper_obj_far`.

### TurnOffStove — horizon 750
Source: `atomic/kitchen_stove.py` (`ManipulateStoveKnob`, behavior `turn_off`).
Instruction: `"Turn off the {front left|…} burner of the stove."`. The knob is chosen at random per episode.
Checker: `not stove.is_burner_on(knob)` (knob angle outside [0.35, 2π−0.35]). Only the named knob is checked.

### OpenCabinet — horizon 1050
Source: `atomic/kitchen_doors.py` (`OpenCabinet(OpenDoor)`, fixture `CABINET_WITH_DOOR`).
Instruction: `"Open the {cabinet nat_lang} {door|doors}."` (it says "doors" for `HingeCabinet`).
Checker: `fxtr.is_open(env)`, which requires every door joint at ≥0.90. A hinge cabinet therefore needs both doors open.

## Composite tasks (`composite_seen`)

### ScrubCuttingBoard — horizon 1200
Source: `robocasa/environments/kitchen/composite/sanitizing_cutting_board/scrub_cutting_board.py`.
Instruction: `"Pick up the sponge from the counter and clean the cutting board by briefly scrubbing or pressing down on the cutting board. Once finished, release the sponge."`.
Docstring steps: (1) pick up the sponge, (2) scrub the board, (3) place the sponge down.
Checker: three conjuncts.
- `board_contact_timer >= 5`, counting new contact points. A point counts when it is ≥2 cm from earlier ones and is recorded in `update_state` while the sponge is grasped and touching the board.
- The xy spread of those points must be ≥0.1 m.
- `gripper_obj_far(sponge, th=0.15)`.

Predicates:
- `board_scrubbed` is the first two conjuncts. The spread is the hypotenuse of the per-axis ranges, which equals `np.linalg.norm(max_xy - min_xy)`.
- `sponge_released` is the third conjunct.

Docstring step 1 has no conjunct of its own. A grasp predicate would also turn false again when the sponge is released and re-trigger "pick up", so step 1 is merged into the scrub prompt.
Note: the checker never requires the sponge to be put down on the counter, only that the gripper is 0.15 m away. That is less than "place the sponge down".

### RinseSinkBasin — horizon 1350
Source: `composite/cleaning_sink/rinse_sink_basin.py`.
Instruction: `"Turn on the sink and manuever the spout to wash all locations of the sink basin."` (the typo "manuever" is upstream).
Docstring steps: turn on the sink; move the spout left and right.
Checker: each time it is called with the water on, it latches the spout bin it sees (`left`, `center` or `right`) into `washed_loc`. Success is `all(washed_loc)`.
Predicates: `water_on` (from the handle state; this is the precondition for latching) and `basin_rinsed = all(washed_loc)`.
Note: the checker enforces less than "wash all locations". It needs only one checker call in each of three coarse spout-angle bins while the water is on, with no dwell time and no check of water coverage. The centre bin is likely latched as soon as the water turns on if the spout starts centred; I have not verified this.

### KettleBoiling — horizon 1500
Source: `composite/brewing/kettle_boiling.py`.
Instruction: `"Pick the kettle from the counter and place it on a stove burner. Then turn the burner on."`.
Checker: success needs one burner site that meets all of these:
- the kettle (`obj`) touches the stove;
- the kettle body is within 0.15 m in xy of that burner's site;
- that burner has a knob and `is_burner_on`;
- `gripper_obj_far(obj)` holds (0.25 m).

Predicates: `kettle_on_burner` (stove contact and within 0.15 m of any burner site) and `kettle_burner_on` (one such burner is on). Gripper-far is not a step.
Note: a pan or pot distractor sits on one burner, and all knobs start off.

### WashLettuce — horizon 1650
Source: `composite/making_salads/wash_lettuce.py`.
Instruction: `"Wash the lettuce in the sink by running water over it."`.
Docstring: "Turn on the sink. Wash the lettuce under the sink for 25 timesteps".
Checker: `washed_time >= 25`. `washed_time` increases in `update_state` on every step where `sink.check_obj_under_water(lettuce)` holds. That check requires all of:
- the lettuce body is within its horizontal radius in xy of the water site;
- it is below the water site's top;
- `water_on`.

Predicates: `water_on` (a precondition implied by the checker, not a separate conjunct) and `lettuce_washed`.
Note: the 25 steps add up across the episode and need not be consecutive.

### LoadDishwasher — horizon 1800
Source: `composite/loading_dishwasher/load_dishwasher.py`.
Instruction: `"Pick up the {dish0} and {dish1} from the counter, place them in the dishwasher, and close the dishwasher door."`. dish0 comes from the `cup` group and dish1 from the `bowl` group, at scale 0.5. The door starts open with the rack slid out.
Checker: both dishes must touch the top rack (`check_rack_contact`) and the door must satisfy `is_closed(th=0.05)`.
Predicates: `dishes_on_rack` (both dishes) and `dishwasher_closed`.
Notes:
- Upstream computes `check1` and `check2` with the identical call, which is redundant but harmless.
- The `th=0.05` threshold is ten times looser than the default, so "close fully" is enforced only approximately.
- The checker does not require the rack to be pushed back in.

### PrepareCoffee — horizon 1800
Source: `composite/brewing/prepare_coffee.py`.
Instruction: `"Pick the {mug} from the cabinet, place it under the coffee machine dispenser, and press the start button."`. The cabinet door is opened during setup.
Checker: all of these:
- `check_receptacle_placement_for_pouring(obj)` (xy < 0.04 m, |dz| < 0.10 m);
- `gripper_obj_far`;
- `coffee_machine._turned_on`;
- `gripper_button_far`.

Predicates: `mug_under_dispenser` and `machine_on`. The two gripper-far conjuncts are not steps.
Note: the checker enforces less than the instruction's order. `_turned_on` latches on any gripper contact with the start button, including a press before the mug is in place. Pressing first and then placing the mug therefore still succeeds.
