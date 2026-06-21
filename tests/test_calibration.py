"""Phase 4.2: win-prob calibration. The scoring math is checked deterministically on
synthetic samples; a tiny live run checks the collection path."""
from functools import partial

from catansolver.engine import RulesConfig
from catansolver.eval import AdvisorPlayer, collect_samples, reliability


def test_reliability_rewards_perfect_predictions():
    samples = [(1.0, 1.0)] * 50 + [(0.0, 0.0)] * 50
    r = reliability(samples)
    assert r.n == 100
    assert r.brier == 0.0
    assert r.ece == 0.0
    assert abs(r.base_rate - 0.5) < 1e-9


def test_reliability_calibrated_but_uncertain_has_low_ece():
    # says 70%, wins 70% -> well calibrated even though uncertain
    samples = [(0.7, 1.0)] * 70 + [(0.7, 0.0)] * 30
    r = reliability(samples)
    assert abs(r.brier - 0.21) < 1e-9
    assert r.ece < 1e-9
    assert len(r.bins) == 1
    mp, of, count = r.bins[0]
    assert abs(mp - 0.7) < 1e-9 and abs(of - 0.7) < 1e-9 and count == 100


def test_reliability_detects_overconfidence():
    # says 90%, wins only 50% -> ECE ~ 0.4
    samples = [(0.9, 1.0)] * 50 + [(0.9, 0.0)] * 50
    r = reliability(samples)
    assert abs(r.ece - 0.4) < 1e-9
    assert r.brier > 0.2


def test_reliability_handles_empty():
    r = reliability([])
    assert r.n == 0 and r.brier == 0.0 and r.bins == []


def test_collect_samples_labels_predictions():
    rules = RulesConfig(vps_to_win=4)  # short games
    advisor = partial(AdvisorPlayer, n_determinizations=1, iterations=6, rollout_depth=6, rules=rules)
    samples = collect_samples(advisor, n_games=2, rules=rules, seed=3)
    assert all(0.0 <= p <= 1.0 and o in (0.0, 1.0) for p, o in samples)
