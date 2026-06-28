"""Larger head-to-head to confirm the learned-value leaf beats the heuristic leaf."""
import sys
import time
from functools import partial

from catansolver.eval import AdvisorPlayer, play_match


def main():
    n_games = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    cfg = dict(n_determinizations=2, iterations=25, rollout_depth=10)
    value = partial(AdvisorPlayer, value_model="docs/value_model.json", **cfg)
    heuristic = partial(AdvisorPlayer, **cfg)
    t = time.time()
    res = play_match(value, heuristic, n_games, seed=4242, workers=workers)
    lo, hi = res.ci
    print(f"value-leaf vs heuristic-leaf: {res.a_wins}-{res.b_wins}-{res.draws}  "
          f"{res.a_winrate * 100:.0f}%  95% CI [{lo * 100:.0f}-{hi * 100:.0f}]  "
          f"{'SIGNIFICANT' if res.significant else 'not significant'}  ({time.time() - t:.0f}s)")


if __name__ == "__main__":
    main()
