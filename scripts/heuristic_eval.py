"""Heuristic-accuracy study: compare opening-spot heuristic scores against
Monte-Carlo win probabilities (FIRST seat, single settlement).

For each random board we take the legal opening spots, pick CANDIDATES spaced
across the heuristic ranking (to span good->bad), and estimate each one's win
probability with ROLLOUTS games where both players use a fast WeightedRandom
policy. Results stream to a CSV; summary statistics print at the end.

Run (from repo root, with the Anaconda OpenSSL PATH + PYTHONPATH set):
    .\.venv\Scripts\python.exe scripts\heuristic_eval.py
"""
from __future__ import annotations

import csv
import json
import math
import random
import time
from pathlib import Path

import numpy as np
from catanatron import Color
from catanatron.players.weighted_random import WeightedRandomPlayer
from catanatron.models.map import BASE_MAP_TEMPLATE, CatanMap

from catansolver.engine.adapter import map_to_schema, schema_to_map
from catansolver.io.schema import DraftSeat
from catansolver.placement.practice import generate_puzzle
from catansolver.placement.draft import drive_to_user_decision
from catansolver.placement.optimize import _legal_settlements
from catansolver.placement.heuristic import node_score, best_initial_road
from catansolver.placement.rollout import estimate_win_prob

BOARDS = 40
CANDIDATES = 10          # spots per board, spaced across the heuristic ranking
ROLLOUTS = 200           # rollouts per candidate
POLICY = lambda c: WeightedRandomPlayer(c)  # noqa: E731

OUT = Path("docs/heuristic-eval-data.csv")
STATS = Path("docs/heuristic-eval-stats.json")


def spaced(n_sorted: int, k: int):
    """k indices evenly spaced over 0..n_sorted-1 (inclusive of both ends)."""
    if n_sorted <= k:
        return list(range(n_sorted))
    return sorted({round(i * (n_sorted - 1) / (k - 1)) for i in range(k)})


def run():
    OUT.parent.mkdir(exist_ok=True)
    rows = []
    t0 = time.time()
    with OUT.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["board", "node", "heuristic", "heur_rank", "winprob", "ci_low", "ci_high", "n"])
        for b in range(BOARDS):
            random.seed(1000 + b)
            board = map_to_schema(CatanMap.from_template(BASE_MAP_TEMPLATE))
            req = generate_puzzle(board, DraftSeat.FIRST, seed=b)
            cmap = schema_to_map(req.board)
            game, _ = drive_to_user_decision(req, POLICY, seed=0)
            legal = _legal_settlements(game)
            ranked = sorted(legal, key=lambda n: node_score(cmap, n), reverse=True)
            picks = [ranked[i] for i in spaced(len(ranked), CANDIDATES)]
            for j, node in enumerate(picks):
                h = node_score(cmap, node)
                road = best_initial_road(cmap, node)
                est = estimate_win_prob(
                    req, [(node, road)], ROLLOUTS, policy=POLICY,
                    seed_base=b * 100000 + j * 1000,
                )
                heur_rank = ranked.index(node) + 1
                row = [b, node, round(h, 4), heur_rank,
                       round(est.win_prob, 4), round(est.ci_low, 4), round(est.ci_high, 4), ROLLOUTS]
                w.writerow(row)
                rows.append(row)
            fh.flush()
            el = time.time() - t0
            print(f"board {b + 1}/{BOARDS} done  ({el:.0f}s elapsed, "
                  f"{el / (b + 1):.0f}s/board, ~{el / (b + 1) * (BOARDS - b - 1):.0f}s left)",
                  flush=True)
    analyse(rows, time.time() - t0)


def pearson(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    return float(np.corrcoef(x, y)[0, 1])


def spearman(x, y):
    rx = np.argsort(np.argsort(x))
    ry = np.argsort(np.argsort(y))
    return pearson(rx, ry)


def analyse(rows, secs):
    boards = sorted({r[0] for r in rows})
    H = [r[2] for r in rows]
    W = [r[4] for r in rows]

    pooled_p = pearson(H, W)
    pooled_s = spearman(H, W)

    # within-board rank correlation
    per_board_s, top1_hit, regrets = [], 0, []
    for b in boards:
        rs = [r for r in rows if r[0] == b]
        if len(rs) < 3:
            continue
        per_board_s.append(spearman([r[2] for r in rs], [r[4] for r in rs]))
        rs_by_heur = sorted(rs, key=lambda r: r[2], reverse=True)
        heur_top = rs_by_heur[0]
        best_w = max(r[4] for r in rs)
        if heur_top[4] >= best_w - 1e-9:
            top1_hit += 1
        regrets.append(best_w - heur_top[4])

    # decile-ish buckets by heuristic: mean winprob per bucket (monotone?)
    order = sorted(rows, key=lambda r: r[2])
    nb = 5
    buckets = []
    for i in range(nb):
        chunk = order[i * len(order) // nb:(i + 1) * len(order) // nb]
        buckets.append((
            round(sum(r[2] for r in chunk) / len(chunk), 3),
            round(sum(r[4] for r in chunk) / len(chunk), 3),
            len(chunk),
        ))

    # Fisher z 95% CI for pooled Pearson
    n = len(rows)
    z = math.atanh(pooled_p)
    se = 1 / math.sqrt(n - 3)
    lo, hi = math.tanh(z - 1.96 * se), math.tanh(z + 1.96 * se)

    stats = {
        "boards": len(boards),
        "candidates_per_board": CANDIDATES,
        "rollouts": ROLLOUTS,
        "observations": n,
        "runtime_min": round(secs / 60, 1),
        "pooled_pearson": round(pooled_p, 3),
        "pooled_pearson_ci": [round(lo, 3), round(hi, 3)],
        "pooled_spearman": round(pooled_s, 3),
        "within_board_spearman_mean": round(float(np.mean(per_board_s)), 3),
        "within_board_spearman_std": round(float(np.std(per_board_s)), 3),
        "top1_hit_rate": round(top1_hit / len(boards), 3),
        "top1_regret_mean": round(float(np.mean(regrets)), 3),
        "top1_regret_max": round(float(np.max(regrets)), 3),
        "buckets_heur_vs_winprob": buckets,
    }
    STATS.write_text(json.dumps(stats, indent=2))
    print("\n==== SUMMARY ====")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    run()
