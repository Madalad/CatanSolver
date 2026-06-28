"""Opening win-probability from the learned value model (Phase 5.2).

The opening win-% we shelved in Phase 4 was only calibratable against weak bots. Now we
have a position evaluator (the value model) and a calibration map, so we can give a
trustworthy — and honestly-labelled — number.

``opening_win_prob`` drives the snake draft to the user's decision, plays the candidate
placement(s), **finishes the draft** (the rest by a fast policy), and evaluates the
resulting first-PLAY position with the value model — averaged over several draft
completions and passed through the opening calibrator. This is *much* cheaper than the
old full-rollout estimate (one value eval per completion, no game played out), and the
calibration study (docs/opening-winprob.md) shows it is well-calibrated after recalibration
**vs a baseline-level opponent** — the label to display.
"""
from __future__ import annotations

import functools
import random
from statistics import mean
from typing import Callable, List, Optional, Tuple

from catanatron import Action, ActionType

from catansolver.engine.config import COLONIST_1V1, RulesConfig
from catansolver.io.schema import OpeningPlacementRequest
from catansolver.learn import extract_features

from .draft import PolicyFactory, _pick_road, drive_to_user_decision, rollout_policy
from .heuristic import node_score


def _isolated_rng(fn):
    """Run ``fn`` without leaking global-RNG state. These estimators drive games with fixed
    seeds (for a reproducible estimate), which pins Python's ``random``; restoring the state
    afterward keeps that from contaminating later callers — e.g. the random board generator,
    which would otherwise repeat the same board after each call (see docs / get_random_board)."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        state = random.getstate()
        try:
            return fn(*args, **kwargs)
        finally:
            random.setstate(state)

    return wrapper

Edge = Tuple[int, int]


@_isolated_rng
def opening_win_prob(
    request: OpeningPlacementRequest,
    user_placements: List[Tuple[int, Edge]],
    value_model,
    calibrator: Optional[Callable[[float], float]] = None,
    n_samples: int = 20,
    policy: PolicyFactory = rollout_policy,
    rules: RulesConfig = COLONIST_1V1,
    seed_base: int = 0,
) -> float:
    """Estimate P(user wins) for the opening ``user_placements`` (length 1 for
    FIRST/FIRST_FINAL, 2 for SECOND), via the value model at the post-draft position,
    averaged over ``n_samples`` draft completions and passed through ``calibrator``."""
    probs = []
    for i in range(n_samples):
        game, user = drive_to_user_decision(request, policy, seed=seed_base + i, rules=rules)
        for settlement, road in user_placements:
            game.execute(Action(user, ActionType.BUILD_SETTLEMENT, settlement))
            game.execute(_pick_road(game, road))
        # let the policy finish the remaining draft picks, then read the opening position
        while game.state.is_initial_build_phase and game.winning_color() is None:
            game.play_tick()
        p = value_model(extract_features(game, user))
        probs.append(calibrator(p) if calibrator else p)
    return float(mean(probs))


def _opening_strength(game, color) -> float:
    """Sum of the heuristic node score over ``color``'s initial settlements."""
    cmap = game.state.board.map
    nodes = game.state.buildings_by_color[color].get("SETTLEMENT", [])
    return sum(node_score(cmap, n) for n in nodes)


@_isolated_rng
def opening_win_prob_gap(
    request: OpeningPlacementRequest,
    user_placements: List[Tuple[int, Edge]],
    gap_model,
    n_samples: int = 20,
    policy: PolicyFactory = rollout_policy,
    rules: RulesConfig = COLONIST_1V1,
    seed_base: int = 0,
) -> float:
    """Estimate P(user wins) from the **heuristic opening-strength gap** (user − opponent),
    mapped through ``gap_model`` (a 1-feature logistic, ``docs/opening_gap_model.json``).

    Same scaffolding as :func:`opening_win_prob` — drive the draft, play the candidate,
    finish the draft over ``n_samples`` completions — but the leaf read is the production
    heuristic's gap rather than the learned value model. The gap is a *better* opening
    predictor (lower Brier; see docs/opening-winprob.md) because at the opening the
    purpose-built production score beats the general mid-game value model. Win-% is inherently
    relative, so it must be the *gap*: the same opening is dominant on a poor board and
    mediocre on a rich one, and differencing against the opponent cancels the board."""
    probs = []
    for i in range(n_samples):
        game, user = drive_to_user_decision(request, policy, seed=seed_base + i, rules=rules)
        for settlement, road in user_placements:
            game.execute(Action(user, ActionType.BUILD_SETTLEMENT, settlement))
            game.execute(_pick_road(game, road))
        while game.state.is_initial_build_phase and game.winning_color() is None:
            game.play_tick()
        opponent = next(c for c in game.state.colors if c != user)
        gap = _opening_strength(game, user) - _opening_strength(game, opponent)
        probs.append(float(gap_model.predict_proba([[gap]])[0]))
    return float(mean(probs))
