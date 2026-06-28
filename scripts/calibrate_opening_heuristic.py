"""Can the heuristic opening-strength *gap* be turned into a win-% directly — and is it
more accurate than routing through the learned value model?

For a chosen equal-vs-equal tier, collect at the first PLAY position (post-draft), for both
colours: the heuristic opening-strength **gap** (my node-score sum − opponent's), the value
model's raw P(win), and the eventual outcome. Fit a 1-D logistic ``gap -> P(win)`` on TRAIN,
then compare on a disjoint TEST split against the value model + its opening calibrator.

Run:  PYTHONPATH=. .venv\\Scripts\\python.exe scripts\\calibrate_opening_heuristic.py [tier] [n_train] [n_test] [workers]
      tier in {weighted, advisor}   (default weighted — fast)
"""
import os

for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import sys
import random
import time
from concurrent.futures import ProcessPoolExecutor
from functools import partial

import numpy as np
from catanatron import Color
from catanatron.players.weighted_random import WeightedRandomPlayer

from catansolver.engine import COLONIST_1V1, new_1v1_game
from catansolver.eval import AdvisorPlayer, Calibrator, reliability
from catansolver.learn import train_logistic
from catansolver.placement.heuristic import node_score

MODEL = "docs/value_model.json"


def _dual_game(factory, vm_path, seed):
    """First-PLAY (gap, value_raw, outcome) for both colours of one self-play game."""
    from catansolver.learn import ValueModel, extract_features

    vm = ValueModel.load(vm_path)
    random.seed(seed)
    game = new_1v1_game([factory(Color.RED), factory(Color.BLUE)], rules=COLONIST_1V1, seed=seed)
    while game.state.is_initial_build_phase and game.winning_color() is None:
        game.play_tick()
    if game.winning_color() is not None:
        return []
    cmap = game.state.board.map
    strength = {
        c: sum(node_score(cmap, n) for n in game.state.buildings_by_color[c].get("SETTLEMENT", []))
        for c in game.state.colors
    }
    value_raw = {c: vm(extract_features(game, c)) for c in game.state.colors}
    ticks = 0
    while game.winning_color() is None and ticks < 4000:
        game.play_tick()
        ticks += 1
    winner = game.winning_color()
    if winner is None:
        return []
    colors = list(game.state.colors)
    rows = []
    for c in colors:
        other = colors[1] if c == colors[0] else colors[0]
        rows.append((strength[c] - strength[other], value_raw[c], 1.0 if c == winner else 0.0))
    return rows


def collect(factory, n, workers, seed0):
    args = [(factory, MODEL, seed0 + i) for i in range(n)]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return [r for game in pool.map(_dual_game, *zip(*args)) for r in game]


def main():
    tier = sys.argv[1] if len(sys.argv) > 1 else "weighted"
    n_train = int(sys.argv[2]) if len(sys.argv) > 2 else 400
    n_test = int(sys.argv[3]) if len(sys.argv) > 3 else 200
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 6

    if tier == "advisor":
        factory = partial(AdvisorPlayer, value_model=MODEL, n_determinizations=2, iterations=25, rollout_depth=0)
        cal_path = "docs/opening_calibrator_advisor.json"
    else:
        factory = WeightedRandomPlayer
        cal_path = "docs/opening_calibrator.json"

    t = time.time()
    train = collect(factory, n_train, workers, 30000)
    test = collect(factory, n_test, workers, 60000)
    print(f"tier={tier}  train={len(train)} test={len(test)} samples  ({time.time() - t:.0f}s)\n")

    g_tr = np.array([r[0] for r in train])[:, None]
    y_tr = np.array([r[2] for r in train])
    gap_model = train_logistic(g_tr, y_tr, l2=1.0)

    g_te = np.array([r[0] for r in test])[:, None]
    v_te = np.array([r[1] for r in test])
    y_te = [r[2] for r in test]

    cal = Calibrator.load(cal_path)
    gap_pred = gap_model.predict_proba(g_te)
    val_pred = [cal(v) for v in v_te]

    rg = reliability(list(zip(gap_pred, y_te)))
    rv = reliability(list(zip(val_pred, y_te)))
    print(f"{'predictor':28}{'Brier':>8}{'ECE':>8}{'meanP':>8}{'base':>8}")
    print(f"{'heuristic gap -> win%':28}{rg.brier:8.4f}{rg.ece:8.4f}{rg.mean_pred:8.3f}{rg.base_rate:8.3f}")
    print(f"{'value model + calibrator':28}{rv.brier:8.4f}{rv.ece:8.4f}{rv.mean_pred:8.3f}{rv.base_rate:8.3f}")

    # what the gap->win% map looks like, in heuristic-gap units
    print("\ngap (my strength - opp)  ->  win%")
    for gap in (-1.0, -0.5, -0.25, 0.0, 0.25, 0.5, 1.0):
        print(f"  {gap:+5.2f}   {gap_model.predict_proba(np.array([[gap]]))[0] * 100:5.0f}%")

    # production artifact: refit on all data (train+test) and save
    if "--save" in sys.argv:
        all_g = np.array([r[0] for r in train + test])[:, None]
        all_y = np.array([r[2] for r in train + test])
        final = train_logistic(all_g, all_y, l2=1.0)
        final.save("docs/opening_gap_model.json")
        print(f"\nsaved gap model (fit on {len(all_y)} samples) -> docs/opening_gap_model.json")


if __name__ == "__main__":
    main()
