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
}


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


_PREDICATES = {"ScrubCuttingBoard": _scrub_cutting_board, "RinseSinkBasin": _rinse_sink_basin,
               "KettleBoiling": _kettle_boiling, "WashLettuce": _wash_lettuce,
               "LoadDishwasher": _load_dishwasher, "PrepareCoffee": _prepare_coffee}


def task_predicates(task, raw):
    """Named booleans for `task` read from the raw upstream env; {} when the task has none."""
    function = _PREDICATES.get(task)
    return {} if function is None else {name: bool(value) for name, value in function(raw).items()}
