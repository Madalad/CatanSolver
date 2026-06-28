"""Phase 5.1: learned value function — features + numpy logistic model."""
import random

import numpy as np
from catanatron import Color, RandomPlayer

from catansolver.engine import RulesConfig, new_1v1_game
from catansolver.learn import (
    FEATURE_NAMES,
    ValueModel,
    extract_features,
    generate_dataset,
    train_logistic,
)


def _midgame(seed=2, ticks=60):
    random.seed(seed)
    g = new_1v1_game([RandomPlayer(Color.RED), RandomPlayer(Color.BLUE)], seed=seed)
    for _ in range(ticks):
        if g.winning_color() is not None:
            break
        g.play_tick()
    return g


def test_features_length_matches_names():
    g = _midgame()
    f = extract_features(g, g.state.colors[0])
    assert len(f) == len(FEATURE_NAMES)
    assert np.isfinite(f).all()


def test_features_are_perspective_antisymmetric():
    g = _midgame()
    me = g.state.colors[g.state.current_player_index]
    opp = next(c for c in g.state.colors if c != me)
    fm, fo = extract_features(g, me), extract_features(g, opp)
    # the 15 difference features negate when you swap perspective
    assert np.allclose(fm[:15], -fo[:15])
    # max_vp is symmetric; to_move flips (exactly one side is to-move)
    assert fm[FEATURE_NAMES.index("max_vp")] == fo[FEATURE_NAMES.index("max_vp")]
    assert fm[FEATURE_NAMES.index("to_move_is_me")] + fo[FEATURE_NAMES.index("to_move_is_me")] == 1.0


def test_logistic_recovers_signal_and_outputs_probabilities():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(600, 3))
    logits = 2.0 * X[:, 0] - 1.5 * X[:, 1]  # feat0 helps, feat1 hurts, feat2 irrelevant
    y = (rng.random(600) < 1.0 / (1.0 + np.exp(-logits))).astype(float)
    model = train_logistic(X, y, l2=0.1)
    assert model.coef[0] > 0 and model.coef[1] < 0
    assert abs(model.coef[2]) < abs(model.coef[0])  # irrelevant feature shrinks
    p = model.predict_proba(X)
    assert ((p >= 0) & (p <= 1)).all()


def test_logistic_separable_data_is_confident():
    X = np.array([[-2.0], [-1.0], [1.0], [2.0]])
    y = np.array([0.0, 0.0, 1.0, 1.0])
    model = train_logistic(X, y, l2=0.01)
    assert model(np.array([3.0])) > 0.8
    assert model(np.array([-3.0])) < 0.2


def test_generate_dataset_is_shaped_and_labelled():
    rules = RulesConfig(vps_to_win=5)  # short games so a few finish quickly
    X, y = generate_dataset(4, rules=rules, seed=1, sample_every=2, min_tick=6, max_ticks=400)
    assert X.shape[1] == len(FEATURE_NAMES)
    assert len(X) == len(y)
    assert set(np.unique(y)).issubset({0.0, 1.0})


def test_value_model_json_round_trip(tmp_path):
    rng = np.random.default_rng(1)
    X = rng.normal(size=(100, 4))
    y = (rng.random(100) < 0.5).astype(float)
    model = train_logistic(X, y)
    path = tmp_path / "v.json"
    model.save(path)
    loaded = ValueModel.load(path)
    assert np.allclose(model.predict_proba(X), loaded.predict_proba(X))
