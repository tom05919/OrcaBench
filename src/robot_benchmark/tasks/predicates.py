"""Privileged per-step predicates for candidate tasks (RoboCasa @ 456174f).

Evaluator and diagnostic use only: never pass these values to a model adapter.
Each predicate mirrors a conjunct of the upstream `_check_success`; see
docs/task_catalog.md. RoboCasa is imported lazily because it is absent locally.
"""
import math

CANDIDATE_TASKS = {
    **dict.fromkeys(("OpenDrawer", "CloseFridge", "TurnOnSinkFaucet", "PickPlaceCounterToCabinet",
                     "TurnOnMicrowave", "PickPlaceCounterToStove", "CloseToasterOvenDoor",
                     "CoffeeSetupMug", "TurnOffStove", "OpenCabinet"), "atomic_seen"),
    **dict.fromkeys(("ScrubCuttingBoard", "RinseSinkBasin", "KettleBoiling", "WashLettuce",
                     "LoadDishwasher", "PrepareCoffee"), "composite_seen"),
    # Stage 5 (docs/stage5_plan.md): every composite_unseen target task, for plain-policy measurement.
    **dict.fromkeys(("ArrangeBreadBasket", "ArrangeTea", "BreadSelection", "CategorizeCondiments",
                     "CuttingToolSelection", "GarnishPancake", "GatherTableware", "HeatKebabSandwich",
                     "MakeIceLemonade", "PanTransfer", "PortionHotDogs", "RecycleBottlesByType",
                     "SeparateFreezerRack", "WaffleReheat", "WashFruitColander", "WeighIngredients"),
                    "composite_unseen"),
}

# Privileged subtask decomposition: never expose these prompts to model adapters or task configs.
SEQUENCES = {
    "ScrubCuttingBoard": [
        ("board_scrubbed", "Pick up the sponge from the counter and scrub the cutting board."),
        ("sponge_released", "Place the sponge down."),
    ],
    "RinseSinkBasin": [
        ("water_on", "Turn on the sink."),
        ("basin_rinsed", "Move the spout left and right to rinse all locations of the sink basin."),
    ],
    "KettleBoiling": [
        ("kettle_on_burner", "Pick the kettle from the counter and place it on a stove burner."),
        ("kettle_burner_on", "Turn the burner on."),
    ],
    "WashLettuce": [
        ("water_on", "Turn on the sink."),
        ("lettuce_washed", "Wash the lettuce under the sink."),
    ],
    "LoadDishwasher": [
        ("dishes_on_rack", "Take the dishes from the counter and place them on the top rack of the dishwasher."),
        ("dishwasher_closed", "Close the dishwasher fully."),
    ],
    "PrepareCoffee": [
        ("mug_under_dispenser", "Pick the mug from the cabinet and place it under the coffee machine dispenser."),
        ("machine_on", "Press the start button."),
    ],
    # Stage 6 ceiling test (docs/stage6_ceiling.md): unseen composites. A prompt never names a scene-specific object
    # or plate side, because SEQUENCES is fixed per task; the step predicates are symmetric in the two plates.
    "PortionHotDogs": [
        ("bun_on_plate", "Pick up a hot dog bun from the bowl and place it on a plate."),
        ("portion_on_plate", "Pick up a sausage from the bowl and place it on the plate with the bun."),
        ("bun_on_each_plate", "Pick up the other hot dog bun from the bowl and place it on the empty plate."),
        ("both_plates_portioned", "Pick up the other sausage from the bowl and place it on the plate with only a bun."),
    ],
    "GarnishPancake": [
        ("strawberry_out_of_fridge", "Pick the strawberry from the fridge."),
        ("strawberry_on_pancake", "Place the strawberry on top of the pancake on the dining counter."),
    ],
    "MakeIceLemonade": [
        ("lemon_in_cup", "Pick the lemon wedge from the fridge and place it in the glass of lemonade."),
        ("ice_in_cup", "Pick an ice cube from the ice bowl and place it in the glass of lemonade."),
    ],
    "SeparateFreezerRack": [
        ("meat_on_freezer_rack", "Take the meat container and place it on the second highest rack of the freezer."),
        ("veg_on_freezer_rack", "Take the vegetable container and place it on the highest rack of the freezer."),
    ],
    "PanTransfer": [
        # pan_on_stove is true at step 0, so the vegetables step must come first.
        ("vegetables_on_plate", "Pick up the pan and dump the vegetables in it onto the plate."),
        ("pan_on_stove", "Return the pan to the stove."),
    ],
}

# Clock triggers for W1's time-sensitive stories (docs/work_split.md): false at step 0, logged like the other
# predicates, never subgoals of the task.
TRIGGERS = ("ice_out_of_bowl", "pan_off_stove")


def _scrub_cutting_board(raw):
    from robocasa.utils import object_utils as OU
    positions = raw.board_contact_positions
    sweep = math.hypot(*(max(float(p[axis]) for p in positions) - min(float(p[axis]) for p in positions)
                         for axis in (0, 1))) if positions else 0.0
    return {"board_scrubbed": raw.board_contact_timer >= 5 and sweep >= 0.1,
            "sponge_released": OU.gripper_obj_far(raw, "sponge", th=0.15)}


def _rinse_sink_basin(raw):
    # washed_loc is updated by upstream _check_success, which robosuite calls every step via reward().
    return {"water_on": raw.sink.get_handle_state(env=raw)["water_on"], "basin_rinsed": all(raw.washed_loc)}


def _kettle_boiling(raw):
    from robocasa.utils import object_utils as OU
    stove, placed, lit = raw.stove, False, False
    knobs = stove.get_knobs_state(env=raw)
    kettle = raw.sim.data.body_xpos[raw.obj_body_id[raw.objects["obj"].name]]
    if OU.check_obj_fixture_contact(raw, "obj", stove):
        for location, site in stove.burner_sites.items():
            if site is None:
                continue
            burner = raw.sim.data.get_site_xpos(site.get("name"))
            if math.hypot(float(burner[0]) - float(kettle[0]), float(burner[1]) - float(kettle[1])) < 0.15:
                placed = True
                lit = lit or (location in knobs and bool(stove.is_burner_on(env=raw, burner_loc=location)))
    return {"kettle_on_burner": placed, "kettle_burner_on": lit}


def _wash_lettuce(raw):
    return {"water_on": raw.sink.get_handle_state(env=raw)["water_on"], "lettuce_washed": raw.washed_time >= 25}


def _load_dishwasher(raw):
    return {"dishes_on_rack": all(raw.dishwasher.check_rack_contact(raw, name) for name in ("dish0", "dish1")),
            "dishwasher_closed": raw.dishwasher.is_closed(raw, th=0.05)}


def _prepare_coffee(raw):
    machine = raw.coffee_machine
    return {"mug_under_dispenser": machine.check_receptacle_placement_for_pouring(raw, "obj"),
            "machine_on": machine._turned_on}


# Subgoal progress for the five time-sensitive candidates among the unseen composites (stage 5). Each mirrors a
# conjunct of the upstream `_check_success`, except the progress signals `strawberry_reached` (gripper distance),
# `strawberry_out_of_fridge` and the PortionHotDogs step counts, and the TRIGGERS.
def _make_ice_lemonade(raw):
    from robocasa.utils import object_utils as OU
    cubes = ("ice_cube1", "ice_cube2")
    return {"lemon_in_cup": OU.check_obj_in_receptacle(raw, "lemon_wedge", "glass_cup", th=0.5),
            "ice_in_cup": any(OU.check_obj_in_receptacle(raw, cube, "glass_cup", th=0.5) for cube in cubes),
            "ice_out_of_bowl": not all(OU.check_obj_in_receptacle(raw, cube, "ice_bowl") for cube in cubes)}


def _separate_freezer_rack(raw):
    rack = raw.fridge.check_rack_contact
    return {"meat_on_freezer_rack": rack(raw, "meat_tupperware", compartment="freezer", rack_index=-2),
            "veg_on_freezer_rack": rack(raw, "veg_tupperware", compartment="freezer", rack_index=-1)}


def _pan_transfer(raw):
    from robocasa.utils import object_utils as OU
    on_stove = raw._check_obj_location_on_stove("vegetable_container") is not None
    return {"vegetables_on_plate": OU.check_obj_in_receptacle(raw, "vegetable", "plate"),
            "pan_on_stove": on_stove, "pan_off_stove": not on_stove,
            "food_untouched": not raw._robot_touched_food}


def _portion_hot_dogs(raw):
    from robocasa.utils import object_utils as OU
    def count(names, plate):
        return sum(bool(OU.check_obj_in_receptacle(raw, name, plate)) for name in names)
    buns, sausages, plates = ("hotdog_bun1", "hotdog_bun2"), ("sausage1", "sausage2"), ("plate1", "plate2")
    portioned = [count(buns, plate) == 1 and count(sausages, plate) == 1 for plate in plates]
    return {"plate1_portioned": portioned[0], "plate2_portioned": portioned[1],
            "any_item_on_plate": any(count(buns + sausages, plate) for plate in plates),
            "bun_on_plate": any(count(buns, plate) for plate in plates),
            "portion_on_plate": any(portioned),
            "bun_on_each_plate": all(count(buns, plate) for plate in plates),
            "both_plates_portioned": all(portioned)}


def _garnish_pancake(raw):
    from robocasa.utils import object_utils as OU
    return {"strawberry_reached": not OU.gripper_obj_far(raw, "strawberry", th=0.1),
            # Centre point only: a full bounding-box check could call a strawberry at the shelf edge "outside".
            "strawberry_out_of_fridge": not OU.obj_inside_of(raw, "strawberry", raw.fridge, partial_check=True),
            "strawberry_on_pancake": OU.check_obj_in_receptacle(raw, "strawberry", "pancake")}


_PREDICATES = {"ScrubCuttingBoard": _scrub_cutting_board, "RinseSinkBasin": _rinse_sink_basin,
               "KettleBoiling": _kettle_boiling, "WashLettuce": _wash_lettuce,
               "LoadDishwasher": _load_dishwasher, "PrepareCoffee": _prepare_coffee,
               "MakeIceLemonade": _make_ice_lemonade, "SeparateFreezerRack": _separate_freezer_rack,
               "PanTransfer": _pan_transfer, "PortionHotDogs": _portion_hot_dogs, "GarnishPancake": _garnish_pancake}


def task_predicates(task, raw):
    """Named booleans for `task` read from the raw upstream env; {} when the task has none."""
    function = _PREDICATES.get(task)
    return {} if function is None else {name: bool(value) for name, value in function(raw).items()}
