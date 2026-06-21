"""Phase 3.5 strength evaluation: play the turn advisor against the reference baselines
and print win-rate + 95% CI for each matchup. The Phase-3 exit criterion is a
statistically significant (Wilson lower bound > 50%) margin over each.

Run (repo root, Anaconda PATH + PYTHONPATH set):
    .\\.venv\\Scripts\\python.exe scripts\\evaluate_advisor.py \\
        [n_games] [dets] [iters] [depth] [method] [workers]

`method` is "pimc" or "ismcts"; `workers` plays games across processes. Defaults are
modest so a run finishes in minutes; raise n_games (and workers) for tighter CIs.
"""
import sys
import time
from functools import partial

from catanatron import RandomPlayer
from catanatron.players.search import VictoryPointPlayer
from catanatron.players.weighted_random import WeightedRandomPlayer

from catansolver.engine import COLONIST_1V1
from catansolver.eval import AdvisorPlayer, play_match

BASELINES = [
    ("RandomPlayer", RandomPlayer),
    ("WeightedRandom (heuristic)", WeightedRandomPlayer),
    ("VictoryPointPlayer (search)", VictoryPointPlayer),
]


def main():
    n_games = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    dets = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    iters = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    depth = int(sys.argv[4]) if len(sys.argv) > 4 else 12
    method = sys.argv[5] if len(sys.argv) > 5 else "pimc"
    workers = int(sys.argv[6]) if len(sys.argv) > 6 else 1

    advisor = partial(AdvisorPlayer, n_determinizations=dets, iterations=iters,
                      rollout_depth=depth, method=method)

    budget = f"{dets} det x {iters} iters" if method == "pimc" else f"{dets * iters} iters"
    print(f"advisor: {method.upper()} ({budget}), rollout_depth={depth}, workers={workers}")
    print(f"{n_games} games/matchup, alternating seat+colour, vps_to_win={COLONIST_1V1.vps_to_win}\n")
    print(f"{'opponent':<30}{'advisor W-L-D':<16}{'win%':>6}  95% CI        sig?")
    for name, factory in BASELINES:
        t = time.time()
        res = play_match(advisor, factory, n_games=n_games, seed=1000, workers=workers)
        lo, hi = res.ci
        rec = f"{res.a_wins}-{res.b_wins}-{res.draws}"
        print(f"{name:<30}{rec:<16}{res.a_winrate * 100:5.0f}  "
              f"[{lo * 100:4.0f}-{hi * 100:4.0f}]   {'YES' if res.significant else 'no':<4}"
              f"({time.time() - t:.0f}s)")


if __name__ == "__main__":  # required: ProcessPoolExecutor re-imports __main__ on Windows
    main()
