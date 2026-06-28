"""Phase 5.1c — train the logistic value model on self-play data and report quality.

Generates disjoint train/val game sets, fits the model on train, evaluates accuracy +
log-loss on the held-out val set, prints the standardised coefficients (feature
importances), and saves the model to docs/value_model.json.

Run:  .venv\\Scripts\\python.exe scripts\\train_value.py [n_train_games] [n_val_games] [l2]
"""
import sys
import time

import numpy as np

from catansolver.learn import FEATURE_NAMES, generate_dataset, train_logistic

OUT = "docs/value_model.json"


def _metrics(model, X, y):
    p = np.clip(model.predict_proba(X), 1e-12, 1 - 1e-12)
    acc = float(((p >= 0.5) == (y >= 0.5)).mean())
    log_loss = float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())
    brier = float(((p - y) ** 2).mean())
    return acc, log_loss, brier


def main():
    n_train = int(sys.argv[1]) if len(sys.argv) > 1 else 250
    n_val = int(sys.argv[2]) if len(sys.argv) > 2 else 80
    l2 = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0

    t = time.time()
    Xtr, ytr = generate_dataset(n_train, seed=5000)
    Xva, yva = generate_dataset(n_val, seed=9000)
    print(f"train={Xtr.shape} val={Xva.shape}  (gen {time.time() - t:.0f}s, "
          f"train win-rate {ytr.mean():.2f})")

    model = train_logistic(Xtr, ytr, l2=l2)
    tr = _metrics(model, Xtr, ytr)
    va = _metrics(model, Xva, yva)
    print(f"\n{'':10}{'acc':>8}{'logloss':>10}{'brier':>8}")
    print(f"{'train':10}{tr[0]:8.3f}{tr[1]:10.3f}{tr[2]:8.3f}")
    print(f"{'val':10}{va[0]:8.3f}{va[1]:10.3f}{va[2]:8.3f}")

    print("\nstandardised coefficients (importance):")
    for name, c in sorted(zip(FEATURE_NAMES, model.coef), key=lambda t: -abs(t[1])):
        print(f"  {name:18}{c:+.3f}")

    model.save(OUT)
    print(f"\nsaved -> {OUT}")


if __name__ == "__main__":
    main()
