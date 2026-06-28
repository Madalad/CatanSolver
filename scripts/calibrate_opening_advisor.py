"""Approach A — recalibrate the opening win-% against an *advisor-level* opponent
(value@d0 self-play) instead of WeightedRandom. Fits the calibrator on TRAIN, scores on a
disjoint TEST split, and prints the mapping side-by-side with the baseline (WeightedRandom)
calibrator to show the de-saturation. Saves docs/opening_calibrator_advisor.json.

Run:  .venv\\Scripts\\python.exe scripts\\calibrate_opening_advisor.py [n_train] [n_test] [workers]
"""
import sys
import time
from functools import partial

from catansolver.eval import AdvisorPlayer, Calibrator, fit_isotonic, reliability
from catansolver.learn import collect_opening_samples_parallel

MODEL = "docs/value_model.json"
OUT = "docs/opening_calibrator_advisor.json"


def main():
    n_train = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    n_test = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    advisor = partial(AdvisorPlayer, value_model=MODEL, n_determinizations=2, iterations=25, rollout_depth=0)

    t = time.time()
    train = collect_opening_samples_parallel(MODEL, advisor, n_train, seed=12000, workers=workers)
    test = collect_opening_samples_parallel(MODEL, advisor, n_test, seed=20000, workers=workers)
    print(f"advisor self-play opening samples: train={len(train)} test={len(test)} ({time.time() - t:.0f}s)\n")

    cal = fit_isotonic(train)
    raw = reliability(test)
    recal = reliability([(cal(p), o) for p, o in test])
    print(f"{'':14}{'Brier':>8}{'ECE':>8}{'meanP':>8}{'base':>8}")
    print(f"{'raw (test)':14}{raw.brier:8.4f}{raw.ece:8.4f}{raw.mean_pred:8.3f}{raw.base_rate:8.3f}")
    print(f"{'recalibrated':14}{recal.brier:8.4f}{recal.ece:8.4f}{recal.mean_pred:8.3f}{recal.base_rate:8.3f}")

    base = Calibrator.load("docs/opening_calibrator.json")  # vs WeightedRandom
    cal_all = fit_isotonic(train + test)
    print("\nraw value -> calibrated win% (baseline vs advisor opponent):")
    print(f"{'raw':>6}{'vs baseline':>14}{'vs advisor':>13}")
    for raw_p in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        print(f"{raw_p:>6.2f}{base(raw_p) * 100:>13.0f}%{cal_all(raw_p) * 100:>12.0f}%")

    cal_all.save(OUT)
    print(f"\nsaved -> {OUT}")


if __name__ == "__main__":  # ProcessPoolExecutor re-imports __main__ on Windows
    main()
