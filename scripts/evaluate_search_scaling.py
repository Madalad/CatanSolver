"""How much does pure extra search buy? value@d0 (learned-value leaf, no rollout) is fast,
so we can crank iterations hard. Compare a default vs a big budget against the strongest
available bot (VictoryPoint) and head-to-head.

Run:  .venv\\Scripts\\python.exe scripts\\evaluate_search_scaling.py [n_games] [workers]
"""
import sys
import time
from functools import partial

from catanatron.players.search import VictoryPointPlayer

from catansolver.eval import AdvisorPlayer, play_match

MODEL = "docs/value_model.json"


def main():
    n_games = int(sys.argv[1]) if len(sys.argv) > 1 else 36
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 6

    default = partial(AdvisorPlayer, value_model=MODEL, n_determinizations=2, iterations=25, rollout_depth=0)
    big = partial(AdvisorPlayer, value_model=MODEL, n_determinizations=2, iterations=300, rollout_depth=0)

    def show(label, res):
        lo, hi = res.ci
        print(f"{label:38}{res.a_wins}-{res.b_wins}-{res.draws}  {res.a_winrate * 100:5.0f}%  "
              f"[{lo * 100:3.0f}-{hi * 100:3.0f}]  {'SIG' if res.significant else ''}", flush=True)

    print(f"{n_games} games/matchup, workers={workers}  (value@d0; default=2x25, big=2x300 iters)\n")
    t = time.time()
    show("default vs VictoryPoint", play_match(default, VictoryPointPlayer, n_games, seed=11, workers=workers))
    show("big vs VictoryPoint", play_match(big, VictoryPointPlayer, n_games, seed=22, workers=workers))
    show("big vs default (12x search)", play_match(big, default, n_games, seed=33, workers=workers))
    print(f"\ntotal {time.time() - t:.0f}s")


if __name__ == "__main__":
    main()
