"""Phase 5.2a — is the value model trustworthy as an *opening* win-%?

Evaluates the value model at the post-draft position (both colours) and labels by the
eventual winner, on a TRAIN and a disjoint TEST split of self-play games. Reports raw
calibration (Brier/ECE + reliability), fits an isotonic recalibration on train, re-scores
on test, and saves the opening calibrator to docs/opening_calibrator.json.

Run:  .venv\\Scripts\\python.exe scripts\\calibrate_opening.py [n_train] [n_test]
"""
import sys
import time

from catansolver.eval import fit_isotonic, reliability
from catansolver.learn import ValueModel, collect_opening_samples

OUT = "docs/opening_calibrator.json"


def main():
    n_train = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    n_test = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    vm = ValueModel.load("docs/value_model.json")

    t = time.time()
    train = collect_opening_samples(vm, n_train, seed=6000)
    test = collect_opening_samples(vm, n_test, seed=10000)
    print(f"opening samples: train={len(train)} test={len(test)}  ({time.time() - t:.0f}s)\n")

    cal = fit_isotonic(train)
    raw = reliability(test)
    recal = reliability([(cal(p), o) for p, o in test])

    print(f"{'':14}{'Brier':>8}{'ECE':>8}{'meanP':>8}{'base':>8}")
    print(f"{'raw (test)':14}{raw.brier:8.4f}{raw.ece:8.4f}{raw.mean_pred:8.3f}{raw.base_rate:8.3f}")
    print(f"{'recalibrated':14}{recal.brier:8.4f}{recal.ece:8.4f}{recal.mean_pred:8.3f}{recal.base_rate:8.3f}")

    print("\nraw reliability (predicted -> observed, count):")
    for mp, of, count in raw.bins:
        print(f"  {mp:5.2f} -> {of:5.2f}  (n={count})")

    fit_isotonic(train + test).save(OUT)
    print(f"\nsaved opening calibrator -> {OUT}")


if __name__ == "__main__":
    main()
