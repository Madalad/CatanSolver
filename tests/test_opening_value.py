"""Phase 5.2: opening win-% from the learned value model (+ its calibration data)."""
import numpy as np
from catanatron.models.map import BASE_MAP_TEMPLATE, CatanMap

from catansolver.engine import RulesConfig, map_to_schema
from catansolver.io.schema import DraftSeat, OpeningPlacementRequest
from catansolver.learn import FEATURE_NAMES, collect_opening_samples, train_logistic
from catansolver.placement import opening_win_prob, opening_win_prob_gap, recommend_opening


def _board():
    return map_to_schema(CatanMap.from_template(BASE_MAP_TEMPLATE))


def _value_model(seed=0):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(120, len(FEATURE_NAMES)))
    return train_logistic(X, (X[:, 0] > 0).astype(float))  # depends on d_vp


def _first_placement(req):
    rec = recommend_opening(req, top_k=1, n_rollouts=0)[0]  # heuristic pick, legal
    return [(rec.placements[0].settlement, tuple(rec.placements[0].road))]


def test_opening_win_prob_is_a_probability():
    req = OpeningPlacementRequest(board=_board(), seat=DraftSeat.FIRST, user_color="P1")
    p = opening_win_prob(req, _first_placement(req), _value_model(), n_samples=5)
    assert 0.0 <= p <= 1.0


def test_opening_win_prob_applies_calibrator():
    req = OpeningPlacementRequest(board=_board(), seat=DraftSeat.FIRST, user_color="P1")
    placement = _first_placement(req)
    vm = _value_model()
    # a constant calibrator pins every per-completion prediction -> the mean is that value
    p = opening_win_prob(req, placement, vm, calibrator=lambda _x: 0.73, n_samples=4)
    assert abs(p - 0.73) < 1e-9


def test_opening_win_prob_gap_is_a_probability():
    req = OpeningPlacementRequest(board=_board(), seat=DraftSeat.FIRST, user_color="P1")
    # a 1-feature logistic on the opening-strength gap (the production-model artifact)
    rng = np.random.default_rng(0)
    g = rng.normal(size=(80, 1))
    gap_model = train_logistic(g, (g[:, 0] > 0).astype(float))
    p = opening_win_prob_gap(req, _first_placement(req), gap_model, n_samples=5)
    assert 0.0 <= p <= 1.0


def test_opening_win_prob_gap_favours_a_stronger_opening():
    # a gap model that rewards a positive (my-strength minus opp) gap should rate the best
    # heuristic opener above a deliberately weak one on the same board/seat.
    req = OpeningPlacementRequest(board=_board(), seat=DraftSeat.FIRST, user_color="P1")
    g = np.linspace(-1, 1, 200)[:, None]
    gap_model = train_logistic(g, (g[:, 0] > 0).astype(float))  # monotone increasing in gap
    recs = recommend_opening(req, top_k=30, n_rollouts=0)
    best = [(recs[0].placements[0].settlement, tuple(recs[0].placements[0].road))]
    worst = [(recs[-1].placements[0].settlement, tuple(recs[-1].placements[0].road))]
    p_best = opening_win_prob_gap(req, best, gap_model, n_samples=12)
    p_worst = opening_win_prob_gap(req, worst, gap_model, n_samples=12)
    assert p_best > p_worst


def test_collect_opening_samples_is_labelled():
    vm = _value_model()
    samples = collect_opening_samples(vm, n_games=4, rules=RulesConfig(vps_to_win=5), seed=1)
    assert all(0.0 <= p <= 1.0 and o in (0.0, 1.0) for p, o in samples)
    # one sample per colour per finished game -> even count
    assert len(samples) % 2 == 0
