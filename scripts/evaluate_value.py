"""Phase 5.1d — does the learned value leaf beat the VP-lead heuristic leaf?

Head-to-head: Advisor(value-model leaf) vs Advisor(heuristic leaf) at identical search
settings, plus each vs the baselines for context. The learned value helps iff it wins the
head-to-head above 50%.

Run:  .venv\\Scripts\\python.exe scripts\\evaluate_value.py [n_games] [workers]
"""
import sys
import time
from functools import partial

from catanatron import RandomPlayer
from catanatron.players.search import VictoryPointPlayer
from catanatron.players.weighted_random import WeightedRandomPlayer

from catansolver.eval import AdvisorPlayer, play_match

MODEL = "docs/value_model.json"


def main():
    n_games = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    cfg = dict(n_determinizations=2, iterations=25, rollout_depth=10)

    value = partial(AdvisorPlayer, value_model=MODEL, **cfg)
    heuristic = partial(AdvisorPlayer, **cfg)

    def show(label, res):
        lo, hi = res.ci
        print(f"{label:34}{res.a_wins}-{res.b_wins}-{res.draws}  "
              f"{res.a_winrate * 100:5.0f}%  [{lo * 100:3.0f}-{hi * 100:3.0f}]  "
              f"{'SIG' if res.significant else ''}")

    print(f"{n_games} games/matchup, workers={workers}, settings={cfg}\n")
    t = time.time()
    show("value-leaf vs heuristic-leaf", play_match(value, heuristic, n_games, seed=4242, workers=workers))
    print()
    for name, opp in [("Random", RandomPlayer), ("WeightedRandom", WeightedRandomPlayer),
                      ("VictoryPoint", VictoryPointPlayer)]:
        show(f"value-leaf vs {name}", play_match(value, opp, n_games, seed=5151, workers=workers))
    print(f"\ntotal {time.time() - t:.0f}s")


if __name__ == "__main__":
    main()
