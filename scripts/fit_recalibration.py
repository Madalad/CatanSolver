"""Phase 4.2b — fit the isotonic recalibration map and report its honest (held-out)
effect. Collects advisor-vs-WeightedRandom games for a TRAIN split and a disjoint TEST
split, fits the map on train, and compares raw vs recalibrated Brier/ECE on test. Saves
the map (refit on all data) to docs/recalibration.json for the API/UI to apply.

Run:  .venv\\Scripts\\python.exe scripts\\fit_recalibration.py [n_train] [n_test]
"""
import sys
from functools import partial

from catansolver.eval import AdvisorPlayer, collect_samples, fit_isotonic, reliability

ROOT_OUT = "docs/recalibration.json"


def main():
    n_train = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    n_test = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    advisor = partial(AdvisorPlayer, n_determinizations=2, iterations=25, rollout_depth=10)

    print(f"collecting train ({n_train} games) + test ({n_test} games) vs WeightedRandom...")
    train = collect_samples(advisor, n_games=n_train, seed=4000)
    test = collect_samples(advisor, n_games=n_test, seed=8000)
    print(f"train={len(train)} preds, test={len(test)} preds")

    cal = fit_isotonic(train)
    raw = reliability(test)
    recal = reliability([(cal(p), o) for p, o in test])

    print(f"\n{'':14}{'Brier':>8}{'ECE':>8}{'meanP':>8}{'base':>8}")
    print(f"{'raw (test)':14}{raw.brier:8.4f}{raw.ece:8.4f}{raw.mean_pred:8.3f}{raw.base_rate:8.3f}")
    print(f"{'recalibrated':14}{recal.brier:8.4f}{recal.ece:8.4f}{recal.mean_pred:8.3f}{recal.base_rate:8.3f}")

    # final artifact: refit on all data
    fit_isotonic(train + test).save(ROOT_OUT)
    print(f"\nsaved calibrator -> {ROOT_OUT}")
    print("knots:", [(round(x, 3), round(y, 3)) for x, y in fit_isotonic(train + test).knots])


if __name__ == "__main__":
    main()
