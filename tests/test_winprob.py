"""Win-probability model: the logistic map is monotone and in-range, and
recommendations carry an instant model_win_prob for calibrated seats."""

import random

import pytest

from catanatron.models.map import BASE_MAP_TEMPLATE, CatanMap

from catansolver.engine.adapter import map_to_schema
from catansolver.io.schema import DraftSeat
from catansolver.placement import generate_puzzle, recommend_opening, win_prob_estimate


def test_estimate_monotone_and_in_range():
    prev = -1.0
    for h in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]:
        p = win_prob_estimate(DraftSeat.FIRST, h)
        assert 0.0 < p < 1.0
        assert p > prev  # strictly increasing in the heuristic
        prev = p
    # sanity against the fitted curve: ~50% near heuristic 0.28
    assert abs(win_prob_estimate(DraftSeat.FIRST, 0.277) - 0.5) < 0.02


def test_recommend_populates_model_win_prob_first_seat():
    random.seed(0)
    board = map_to_schema(CatanMap.from_template(BASE_MAP_TEMPLATE))
    req = generate_puzzle(board, DraftSeat.FIRST, seed=0)
    recs = recommend_opening(req, top_k=5, n_rollouts=0)
    assert all(r.model_win_prob is not None for r in recs)
    assert all(0.0 < r.model_win_prob < 1.0 for r in recs)
    # higher heuristic -> higher modeled win-prob (same monotone map)
    by_heur = sorted(recs, key=lambda r: r.heuristic_score)
    probs = [r.model_win_prob for r in by_heur]
    assert probs == sorted(probs)


def test_uncalibrated_seat_returns_none_gracefully(monkeypatch):
    from catansolver.placement import winprob_model
    monkeypatch.setitem(winprob_model._COEFFS, DraftSeat.SECOND, None)
    assert win_prob_estimate(DraftSeat.SECOND, 1.0) is None
