"""Baseline mid-game turn advisor (Phase 3.2).

Determinized **flat Monte-Carlo**: import the position, then for each legal action
play the candidate move and roll the game out to completion N times with a fast
policy for both players, scoring the current player's win rate. Actions are ranked
by that rate (Wilson 95% CI for the uncertainty).

"Determinized" only in the weak sense for now — the given ``GameState`` is treated
as fully observed (opponent hand known). Sampling hidden information from a belief
state is Phase 3.3; replacing flat MC with ISMCTS is Phase 3.4. This module is the
``state -> ranked actions`` baseline that those will be measured against.

Caveat (same as the opening win-%): the rate is *vs the baseline rollout opponent*,
so treat it as a relative ranking signal, not a real-match probability.
"""
from __future__ import annotations

import random
from typing import Callable, List

from catanatron import Color, Player

from catansolver.engine import COLONIST_1V1, RulesConfig, game_from_state
from catansolver.io.schema import ActionRecommendation, GameState
from catansolver.placement.draft import rollout_policy
from catansolver.placement.rollout import wilson_interval

PolicyFactory = Callable[[Color], Player]
_COLORS = (Color.RED, Color.BLUE)


def _jsonable(value):
    """Catanatron action values are JSON-friendly already; normalise tuples to lists
    (and nested tuples) so the recommendation serialises cleanly."""
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    return value


def recommend_actions(
    gs: GameState,
    n_rollouts: int = 50,
    policy: PolicyFactory = rollout_policy,
    rules: RulesConfig = COLONIST_1V1,
    seed: int = 0,
) -> List[ActionRecommendation]:
    """Rank the current player's legal actions by Monte-Carlo win rate, best first.

    Each candidate is played on a fresh copy of the imported position and rolled out
    ``n_rollouts`` times. The RNG is reseeded to ``seed`` before each candidate's
    rollouts so all candidates face the same dice/opponent stream (common random
    numbers — a paired comparison that sharpens the ranking).
    """
    base = game_from_state(gs, players=[policy(c) for c in _COLORS], rules=rules)
    me = base.state.colors[base.state.current_player_index]
    actions = list(base.state.playable_actions)

    recs: List[ActionRecommendation] = []
    for action in actions:
        wins = 0
        random.seed(seed)
        for _ in range(n_rollouts):
            game = base.copy()
            game.execute(action)
            if game.play() == me:
                wins += 1
        win_prob = wins / n_rollouts if n_rollouts else 0.0
        lo, hi = wilson_interval(wins, n_rollouts)
        recs.append(
            ActionRecommendation(
                action_type=action.action_type.value,
                value=_jsonable(action.value),
                win_prob=round(win_prob, 4),
                ci_low=round(lo, 4),
                ci_high=round(hi, 4),
                rollouts=n_rollouts,
            )
        )
    recs.sort(key=lambda r: r.win_prob, reverse=True)
    return recs
