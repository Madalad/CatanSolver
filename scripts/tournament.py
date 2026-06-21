"""Phase 4.1 — round-robin tournament with Elo ratings. Puts random / heuristic /
search baselines and our advisor on one comparable scale.

Run (repo root, Anaconda PATH + PYTHONPATH set):
    .\\.venv\\Scripts\\python.exe scripts\\tournament.py [n_games] [dets] [iters] [depth] [workers]
"""
import sys
import time
from functools import partial

from catanatron import RandomPlayer
from catanatron.players.search import VictoryPointPlayer
from catanatron.players.weighted_random import WeightedRandomPlayer

from catansolver.eval import AdvisorPlayer, run_tournament


def main():
    n_games = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    dets = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    iters = int(sys.argv[3]) if len(sys.argv) > 3 else 25
    depth = int(sys.argv[4]) if len(sys.argv) > 4 else 10
    workers = int(sys.argv[5]) if len(sys.argv) > 5 else 6

    entrants = [
        ("Random", RandomPlayer),
        ("WeightedRandom", WeightedRandomPlayer),
        ("VictoryPoint", VictoryPointPlayer),
        ("Advisor(PIMC)", partial(AdvisorPlayer, n_determinizations=dets, iterations=iters,
                                  rollout_depth=depth, method="pimc")),
    ]

    print(f"round-robin: {n_games} games/pair, workers={workers}, "
          f"advisor={dets}x{iters} depth={depth}")
    t = time.time()
    res = run_tournament(entrants, n_games=n_games, seed=2000, workers=workers)
    print(f"took {time.time() - t:.0f}s\n")

    print(f"{'rank  entrant':<24}{'Elo':>6}  {'W-L-D':<12}{'win%':>6}  95% CI")
    for i, s in enumerate(res.standings, 1):
        lo, hi = s.ci
        rec = f"{s.wins}-{s.losses}-{s.draws}"
        print(f"{i:>2}.  {s.name:<18}{s.elo:6.0f}  {rec:<12}{s.win_rate * 100:5.0f}  "
              f"[{lo * 100:3.0f}-{hi * 100:3.0f}]")

    print("\npairwise (row's wins vs column):")
    names = [s.name for s in res.standings]
    print(f"{'':<16}" + "".join(f"{n[:10]:>11}" for n in names))
    for a in names:
        cells = []
        for b in names:
            if a == b:
                cells.append(f"{'-':>11}")
            elif (a, b) in res.matrix:
                cells.append(f"{res.matrix[(a, b)].a_wins:>11}")
            elif (b, a) in res.matrix:
                cells.append(f"{res.matrix[(b, a)].b_wins:>11}")
            else:
                cells.append(f"{'?':>11}")
        print(f"{a:<16}" + "".join(cells))


if __name__ == "__main__":  # ProcessPoolExecutor re-imports __main__ on Windows
    main()
