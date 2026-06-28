"""Phase 5.1e — does a learned value let us truncate rollouts to depth 0 (pure value
leaf) for a speed and/or strength win?

Timing (measured separately): value@d0 ~37ms/decision vs heuristic@d10 ~141ms (3.8x).
Here we test strength:
  * value@d0 (equal iters)        vs heuristic@d10  -> as strong but ~3.8x faster?
  * value@d0 (~time-matched iters) vs heuristic@d10  -> does the freed compute win?
"""
import sys
import time
from functools import partial

from catanatron.players.weighted_random import WeightedRandomPlayer

from catansolver.eval import AdvisorPlayer, play_match

MODEL = "docs/value_model.json"


def main():
    n_games = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 6

    value0 = partial(AdvisorPlayer, value_model=MODEL, n_determinizations=2, iterations=25, rollout_depth=0)
    value0_big = partial(AdvisorPlayer, value_model=MODEL, n_determinizations=2, iterations=90, rollout_depth=0)
    heur10 = partial(AdvisorPlayer, n_determinizations=2, iterations=25, rollout_depth=10)

    def show(label, res):
        lo, hi = res.ci
        print(f"{label:42}{res.a_wins}-{res.b_wins}-{res.draws}  {res.a_winrate * 100:5.0f}%  "
              f"[{lo * 100:3.0f}-{hi * 100:3.0f}]  {'SIG' if res.significant else ''}")

    print(f"{n_games} games/matchup, workers={workers}\n")
    t = time.time()
    show("value@d0 (eq iters) vs heuristic@d10", play_match(value0, heur10, n_games, seed=4242, workers=workers))
    show("value@d0 x90 (~eq time) vs heuristic@d10", play_match(value0_big, heur10, n_games, seed=909, workers=workers))
    show("value@d0 vs WeightedRandom (sanity)", play_match(value0, WeightedRandomPlayer, n_games, seed=515, workers=workers))
    print(f"\ntotal {time.time() - t:.0f}s")


if __name__ == "__main__":
    main()
