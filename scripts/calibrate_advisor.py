"""Phase 4.2 — measure how calibrated the advisor's win-prob is. Plays the advisor vs
the rollout-level opponent (WeightedRandom), scores the (prediction, outcome) pairs,
and prints Brier / log-loss / ECE + a reliability table.

Run (repo root, Anaconda PATH + PYTHONPATH set):
    .\\.venv\\Scripts\\python.exe scripts\\calibrate_advisor.py [n_games] [dets] [iters] [depth]
"""
import sys
import time
from functools import partial

from catansolver.eval import AdvisorPlayer, collect_samples, reliability


def main():
    n_games = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    dets = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    iters = int(sys.argv[3]) if len(sys.argv) > 3 else 25
    depth = int(sys.argv[4]) if len(sys.argv) > 4 else 10

    advisor = partial(AdvisorPlayer, n_determinizations=dets, iterations=iters, rollout_depth=depth)
    print(f"advisor {dets}x{iters} depth={depth} vs WeightedRandom, {n_games} games")
    t = time.time()
    samples = collect_samples(advisor, n_games=n_games, seed=3000)
    r = reliability(samples)
    print(f"collected {r.n} predictions in {time.time() - t:.0f}s\n")
    print(f"base rate (actual win freq): {r.base_rate:.3f}   mean prediction: {r.mean_pred:.3f}")
    print(f"Brier: {r.brier:.4f}  (base-rate predictor: {r.base_rate * (1 - r.base_rate):.4f})")
    print(f"log-loss: {r.log_loss:.4f}    ECE: {r.ece:.4f}\n")
    print(f"{'predicted':>10}{'observed':>10}{'count':>8}")
    for mp, of, count in r.bins:
        print(f"{mp:>10.2f}{of:>10.2f}{count:>8}")


if __name__ == "__main__":
    main()
