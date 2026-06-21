"""Calibrate heuristic -> P(win) logistic models for the SECOND and FIRST_FINAL
seats (FIRST is already covered by heuristic-eval-data.csv).

For each seat we sample spots/pairs spanning the heuristic range, estimate each
one's win probability with WeightedRandom rollouts (the same fast even-strength
baseline used by the rollout mode), then fit a 2-parameter logistic by MLE.
Writes per-seat data CSVs and a combined coefficients JSON.

Run from repo root with Anaconda PATH + PYTHONPATH set.
"""
from __future__ import annotations

import csv
import json
import random
import time
from pathlib import Path

import numpy as np
from catanatron import Action, ActionType
from catanatron.players.weighted_random import WeightedRandomPlayer
from catanatron.models.map import BASE_MAP_TEMPLATE, CatanMap

from catansolver.engine.adapter import map_to_schema, schema_to_map
from catansolver.io.schema import DraftSeat
from catansolver.placement.practice import generate_puzzle
from catansolver.placement.draft import drive_to_user_decision, _pick_road
from catansolver.placement.optimize import _legal_settlements
from catansolver.placement.heuristic import node_score, best_initial_road, pair_score
from catansolver.placement.rollout import estimate_win_prob

BOARDS = 22
CANDIDATES = 10
ROLLOUTS = 200
POLICY = lambda c: WeightedRandomPlayer(c)  # noqa: E731
DOCS = Path("docs")


def spaced(n_sorted: int, k: int):
    if n_sorted <= k:
        return list(range(n_sorted))
    return sorted({round(i * (n_sorted - 1) / (k - 1)) for i in range(k)})


def candidates_single(req, cmap):
    """(heuristic, placements) for spaced single-settlement spots."""
    game, _ = drive_to_user_decision(req, POLICY, seed=0)
    legal = _legal_settlements(game)
    ranked = sorted(legal, key=lambda n: node_score(cmap, n), reverse=True)
    out = []
    for i in spaced(len(ranked), CANDIDATES):
        node = ranked[i]
        out.append((node_score(cmap, node), [(node, best_initial_road(cmap, node))]))
    return out


def candidates_pair(req, cmap):
    """(pair_score, placements) for pairs spanning the heuristic range."""
    game, user = drive_to_user_decision(req, POLICY, seed=0)
    nscore = {n: node_score(cmap, n) for n in cmap.land_nodes}
    firsts = sorted(_legal_settlements(game), key=nscore.get, reverse=True)
    pairs = []
    for fi in spaced(len(firsts), 5):
        first = firsts[fi]
        g2 = game.copy()
        road1 = best_initial_road(cmap, first)
        g2.execute(Action(user, ActionType.BUILD_SETTLEMENT, first))
        g2.execute(_pick_road(g2, road1))
        seconds = sorted(_legal_settlements(g2), key=nscore.get, reverse=True)
        for si in spaced(len(seconds), 3):  # best / mid / worst second
            second = seconds[si]
            road2 = best_initial_road(cmap, second)
            ps = pair_score(cmap, nscore, first, second)
            pairs.append((ps, [(first, road1), (second, road2)]))
    pairs.sort(key=lambda t: t[0])
    return [pairs[i] for i in spaced(len(pairs), CANDIDATES)]


GEN = {DraftSeat.FIRST_FINAL: candidates_single, DraftSeat.SECOND: candidates_pair}


def fit_logistic(h, wins, n):
    X = np.column_stack([np.ones_like(h), h])
    beta = np.zeros(2)
    for _ in range(50):
        eta = X @ beta
        p = 1 / (1 + np.exp(-eta))
        W = n * p * (1 - p)
        z = eta + (wins - n * p) / np.clip(W, 1e-9, None)
        beta = np.linalg.solve(X.T @ (W[:, None] * X), X.T @ (W * z))
    return float(beta[0]), float(beta[1])


def run_seat(seat):
    t0 = time.time()
    H, WP = [], []
    out = (DOCS / f"winprob-{seat.value.lower()}-data.csv").open("w", newline="")
    w = csv.writer(out)
    w.writerow(["board", "heuristic", "winprob", "n"])
    for b in range(BOARDS):
        random.seed(2000 + b)
        board = map_to_schema(CatanMap.from_template(BASE_MAP_TEMPLATE))
        req = generate_puzzle(board, seat, seed=b)
        cmap = schema_to_map(req.board)
        for j, (h, placements) in enumerate(GEN[seat](req, cmap)):
            est = estimate_win_prob(req, placements, ROLLOUTS, policy=POLICY,
                                    seed_base=b * 100000 + j * 1000)
            H.append(h); WP.append(est.win_prob)
            w.writerow([b, round(h, 4), round(est.win_prob, 4), ROLLOUTS])
        out.flush()
        el = time.time() - t0
        print(f"[{seat.value}] board {b+1}/{BOARDS}  ({el:.0f}s, ~{el/(b+1)*(BOARDS-b-1):.0f}s left)",
              flush=True)
    out.close()
    H = np.array(H); WP = np.array(WP); n = np.full_like(H, ROLLOUTS)
    a, bcoef = fit_logistic(H, np.round(WP * ROLLOUTS), n)
    return {"a": round(a, 4), "b": round(bcoef, 4), "n_obs": len(H),
            "heuristic_range": [round(float(H.min()), 3), round(float(H.max()), 3)],
            "p50_heuristic": round(-a / bcoef, 3)}


def main():
    coeffs = {}
    # FIRST: reuse the existing study data
    rows = list(csv.DictReader(open(DOCS / "heuristic-eval-data.csv")))
    h = np.array([float(r["heuristic"]) for r in rows])
    wp = np.array([float(r["winprob"]) for r in rows])
    n = np.array([float(r["n"]) for r in rows])
    a, bcoef = fit_logistic(h, np.round(wp * n), n)
    coeffs["FIRST"] = {"a": round(a, 4), "b": round(bcoef, 4), "n_obs": len(h),
                       "heuristic_range": [round(float(h.min()), 3), round(float(h.max()), 3)],
                       "p50_heuristic": round(-a / bcoef, 3)}
    print("FIRST:", coeffs["FIRST"], flush=True)
    for seat in (DraftSeat.FIRST_FINAL, DraftSeat.SECOND):
        coeffs[seat.value] = run_seat(seat)
        print(seat.value, coeffs[seat.value], flush=True)
    (DOCS / "winprob-coeffs.json").write_text(json.dumps(coeffs, indent=2))
    print("\n==== COEFFS ====")
    print(json.dumps(coeffs, indent=2))


if __name__ == "__main__":
    main()
