"""How much does the *opening* decide the game, as a function of skill level?

For each "equal vs equal" tier (random, simple-heuristic, search, learned-value), play N
self-play games. After the snake draft, score each player's opening with a fixed,
tier-neutral heuristic (summed node production over their two settlements). Then play the
game out and ask: **how often does the player who drafted the stronger opening win?**

That favoured-win-rate, minus 50%, is the opening's *leverage* at that skill level. We also
report the mean opening-strength gap each tier's drafting produces, so a low leverage can be
read as "openings are close" and/or "good players recover".

Run:  PYTHONPATH=. .venv\\Scripts\\python.exe scripts\\opening_leverage.py [n_fast] [n_adv] [workers]
"""
import os

for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from functools import partial

from catanatron import Color, RandomPlayer
from catanatron.players.search import VictoryPointPlayer
from catanatron.players.weighted_random import WeightedRandomPlayer

from catansolver.engine import COLONIST_1V1, new_1v1_game
from catansolver.eval import AdvisorPlayer
from catansolver.placement import wilson_interval
from catansolver.placement.heuristic import node_score

MODEL = "docs/value_model.json"
_TIE = 1e-9


def _one_game(factory, seed):
    """Play one self-play game; return (gap, favoured_won) where gap is the opening-strength
    margin of the stronger drafter and favoured_won is whether they won. None if no winner."""
    random.seed(seed)
    game = new_1v1_game([factory(Color.RED), factory(Color.BLUE)], rules=COLONIST_1V1, seed=seed)
    while game.state.is_initial_build_phase and game.winning_color() is None:
        game.play_tick()
    cmap = game.state.board.map
    strength = {
        c: sum(node_score(cmap, n) for n in game.state.buildings_by_color[c].get("SETTLEMENT", []))
        for c in game.state.colors
    }
    ticks = 0
    while game.winning_color() is None and ticks < 4000:
        game.play_tick()
        ticks += 1
    winner = game.winning_color()
    if winner is None:
        return None
    (c_hi, s_hi), (c_lo, s_lo) = sorted(strength.items(), key=lambda kv: kv[1], reverse=True)
    if s_hi - s_lo < _TIE:
        return (0.0, None)  # tied opening — excluded from favoured-win-rate
    return (s_hi - s_lo, winner == c_hi)


def run_tier(name, factory, n, workers, seed0):
    args = [(factory, seed0 + i) for i in range(n)]
    t = time.time()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = [r for r in pool.map(_one_game, *zip(*args)) if r is not None]
    gaps = [g for g, _ in results]
    decided = [(g, w) for g, w in results if w is not None]
    fav_wins = sum(1 for _, w in decided if w)
    n_dec = len(decided)
    lo, hi = wilson_interval(fav_wins, n_dec) if n_dec else (0.0, 0.0)
    # leverage among the clearest out-drafts (top tercile of gap)
    thr = sorted(gaps)[int(len(gaps) * 2 / 3)] if gaps else 0.0
    big = [w for g, w in decided if g >= thr]
    big_rate = sum(big) / len(big) if big else float("nan")
    print(f"{name:26}{n_dec:5d}{fav_wins / n_dec * 100:8.0f}%{lo * 100:6.0f}-{hi * 100:.0f}"
          f"{sum(gaps) / len(gaps):9.2f}{big_rate * 100:11.0f}%   ({time.time() - t:.0f}s)")


def main():
    n_fast = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    n_adv = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    advisor = partial(AdvisorPlayer, value_model=MODEL, n_determinizations=2, iterations=25, rollout_depth=0)

    print("how often the stronger-opening drafter wins (equal vs equal self-play)\n")
    print(f"{'tier (equal vs equal)':26}{'N':>5}{'fav-win':>8}{'  95% CI':>10}{'mean gap':>9}"
          f"{'big-gap win':>14}")
    run_tier("random vs random", RandomPlayer, n_fast, workers, 1000)
    run_tier("simple (WeightedRandom)", WeightedRandomPlayer, n_fast, workers, 2000)
    run_tier("search (VictoryPoint)", VictoryPointPlayer, n_fast, workers, 3000)
    run_tier("learned-value (value@d0)", advisor, n_adv, workers, 4000)
    print("\nfav-win = win-% of the player who drafted the stronger opening (50% = opening doesn't matter)")
    print("big-gap win = same, but only games in the top tercile of opening-strength gap")


if __name__ == "__main__":
    main()
