"""Recalibrate heuristic -> P(win) against the STRONGER VictoryPointPlayer opponent
(both players), in parallel. Mirrors the WeightedRandom study's design (same board
seeds) so the two are directly comparable.

Streams results to docs/winprob-vp-data.csv and fits a per-seat logistic; writes
docs/winprob-vp-coeffs.json. Parallelised across processes because VP is ~10x
slower per game than WeightedRandom.

Run from repo root with Anaconda PATH + PYTHONPATH set.
"""
from __future__ import annotations

import os

# Cap BLAS/OMP thread pools to 1 BEFORE numpy (and catanatron) import them. With a
# process pool, each worker otherwise spawns many MKL threads (Anaconda numpy), so
# 7 workers x N threads thrash 8 cores. Must be set at module top so spawned
# workers (which re-import this module) inherit the limit before importing numpy.
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import csv
import json
import math
import random
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from catanatron import Action, ActionType
from catanatron.models.map import BASE_MAP_TEMPLATE, CatanMap

from catansolver.engine.adapter import map_to_schema, schema_to_map
from catansolver.io.schema import DraftSeat
from catansolver.placement.practice import generate_puzzle
from catansolver.placement.draft import drive_to_user_decision, _pick_road, default_policy
from catansolver.placement.optimize import _legal_settlements
from catansolver.placement.heuristic import node_score, best_initial_road, pair_score
from catansolver.placement.rollout import estimate_win_prob

_SMOKE = bool(os.environ.get("CATAN_SMOKE"))  # tiny end-to-end test of the pipeline
# VP is ~2 s/game single-threaded (~3.5 games/s across the pool), so the design is
# trimmed vs the WeightedRandom study to land overnight (~84k games, ~7 h).
ROLLOUTS = int(os.environ.get("CATAN_ROLLOUTS", "4" if _SMOKE else "120"))
CANDIDATES = 4 if _SMOKE else 10
BOARDS = ({DraftSeat.FIRST: 2, DraftSeat.FIRST_FINAL: 2, DraftSeat.SECOND: 2} if _SMOKE
          else {DraftSeat.FIRST: 30, DraftSeat.FIRST_FINAL: 20, DraftSeat.SECOND: 20})
SEED_BASE = {DraftSeat.FIRST: 1000, DraftSeat.FIRST_FINAL: 2000, DraftSeat.SECOND: 2000}
WORKERS = max(1, (os.cpu_count() or 2) - 1)
DOCS = Path("docs")
DATA = DOCS / "winprob-vp-data.csv"
COEFFS = DOCS / "winprob-vp-coeffs.json"


def spaced(n, k):
    if n <= k:
        return list(range(n))
    return sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})


def candidates_single(req, cmap):
    game, _ = drive_to_user_decision(req, default_policy, seed=0)
    ranked = sorted(_legal_settlements(game), key=lambda n: node_score(cmap, n), reverse=True)
    return [(node_score(cmap, ranked[i]), [(ranked[i], best_initial_road(cmap, ranked[i]))])
            for i in spaced(len(ranked), CANDIDATES)]


def candidates_pair(req, cmap):
    game, user = drive_to_user_decision(req, default_policy, seed=0)
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
        for si in spaced(len(seconds), 3):
            second = seconds[si]
            pairs.append((pair_score(cmap, nscore, first, second),
                          [(first, road1), (second, best_initial_road(cmap, second))]))
    pairs.sort(key=lambda t: t[0])
    return [pairs[i] for i in spaced(len(pairs), CANDIDATES)]


GEN = {DraftSeat.FIRST: candidates_single, DraftSeat.FIRST_FINAL: candidates_single,
       DraftSeat.SECOND: candidates_pair}


def _eval(payload):
    """Worker: estimate one candidate's win-prob vs VictoryPointPlayer (both sides)."""
    seat_str, board, heuristic, request, placements, seed_base = payload
    est = estimate_win_prob(request, placements, ROLLOUTS, policy=default_policy, seed_base=seed_base)
    return seat_str, board, heuristic, round(est.win_prob, 4)


def build_jobs():
    jobs = []
    for seat, nb in BOARDS.items():
        for b in range(nb):
            random.seed(SEED_BASE[seat] + b)
            board = map_to_schema(CatanMap.from_template(BASE_MAP_TEMPLATE))
            req = generate_puzzle(board, seat, seed=b)
            cmap = schema_to_map(req.board)
            for j, (h, placements) in enumerate(GEN[seat](req, cmap)):
                jobs.append((seat.value, b, round(h, 4), req, placements, b * 100000 + j * 1000))
    return jobs


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


def main():
    DOCS.mkdir(exist_ok=True)
    print(f"building jobs (VP prior generation)…", flush=True)
    jobs = build_jobs()
    total = len(jobs)
    print(f"{total} candidates over {WORKERS} workers, {ROLLOUTS} rollouts each "
          f"(~{total * ROLLOUTS} games)", flush=True)

    rows = []
    t0 = time.time()
    with DATA.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["seat", "board", "heuristic", "winprob", "n"])
        with ProcessPoolExecutor(max_workers=WORKERS) as ex:
            futs = [ex.submit(_eval, p) for p in jobs]
            done = 0
            for fut in as_completed(futs):
                seat_str, board, heuristic, winprob = fut.result()
                w.writerow([seat_str, board, heuristic, winprob, ROLLOUTS])
                rows.append((seat_str, heuristic, winprob))
                done += 1
                if done % 10 == 0 or done == total:
                    fh.flush()
                    el = time.time() - t0
                    print(f"{done}/{total}  ({el:.0f}s, ~{el/done*(total-done):.0f}s left)", flush=True)

    coeffs = {}
    for seat in BOARDS:
        sub = [(h, wp) for s, h, wp in rows if s == seat.value]
        h = np.array([x[0] for x in sub]); wp = np.array([x[1] for x in sub])
        a, b = fit_logistic(h, np.round(wp * ROLLOUTS), np.full_like(h, ROLLOUTS))
        coeffs[seat.value] = {"a": round(a, 4), "b": round(b, 4), "n_obs": len(sub),
                              "p50_heuristic": round(-a / b, 3),
                              "mean_winprob": round(float(wp.mean()), 3)}
    COEFFS.write_text(json.dumps(coeffs, indent=2))
    print("\n==== VP COEFFS ====")
    print(json.dumps(coeffs, indent=2))


if __name__ == "__main__":
    main()
