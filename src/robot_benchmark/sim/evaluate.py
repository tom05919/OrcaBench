"""Evaluation on the CPU: rule grids, the best rule per VLA (pi*_v) and across VLAs (pi_pool), and Monte Carlo action
values for scoring probes. Training seeds fit the rules; held-out seeds score them."""
import statistics
from multiprocessing import Pool

from .harness import Setup, SimEpisode
from .process import PROFILES
from .references import GRID, FixedRule, Oracle

TRAIN_SEEDS = range(1_000_000, 1_001_000)
HELDOUT_SEEDS = range(2_000_000, 2_002_000)


def run_episode(args):
    params, profile_name, seed = args
    agent = Oracle() if params == "oracle" else FixedRule(**params)
    r = SimEpisode(Setup(PROFILES[profile_name], seed)).run(agent, privileged=params == "oracle")
    return r["success"], r["utility"], r["model_calls"], r["steps"]


def evaluate(params, profile_name, seeds, pool=None):
    jobs = [(params, profile_name, s) for s in seeds]
    rows = pool.map(run_episode, jobs, chunksize=64) if pool else list(map(run_episode, jobs))
    n = len(rows)
    return {"success": sum(r[0] for r in rows) / n, "utility": statistics.mean(r[1] for r in rows),
            "calls": statistics.mean(r[2] for r in rows), "steps": statistics.mean(r[3] for r in rows)}


def fit_rules(seeds=TRAIN_SEEDS, workers=8, grid=GRID):
    """Utility of every rule in the grid on every profile (training seeds); pi*_v and pi_pool follow."""
    table = {}
    with Pool(workers) as pool:
        for params in grid:
            for name in PROFILES:
                table[(tuple(sorted(params.items())), name)] = evaluate(params, name, seeds, pool)["utility"]
    best = {name: max(grid, key=lambda p: table[(tuple(sorted(p.items())), name)]) for name in PROFILES}
    pooled = max(grid, key=lambda p: statistics.mean(table[(tuple(sorted(p.items())), n)] for n in PROFILES))
    return best, pooled, table
