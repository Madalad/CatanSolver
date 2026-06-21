"""Monte-Carlo win-probability estimation for opening placements (plan.md §6.3).

For a candidate opening we drive the draft to the user's decision point, fix the
user's placement(s), then play to completion with a rollout policy for *both*
players (symmetric — "win prob vs an equally strong opponent"). Win rate over N
rollouts gives the estimate; a Wilson interval gives the CI.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

from catanatron import Action, ActionType

from catansolver.engine.config import COLONIST_1V1, RulesConfig
from catansolver.io.schema import OpeningPlacementRequest

from .draft import PolicyFactory, _pick_road, drive_to_user_decision, rollout_policy

Edge = Tuple[int, int]
Z_95 = 1.96


def wilson_interval(wins: int, n: int, z: float = Z_95) -> Tuple[float, float]:
    """Wilson score interval for a binomial proportion (always contains wins/n)."""
    if n == 0:
        return (0.0, 1.0)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


@dataclass
class WinEstimate:
    win_prob: float
    ci_low: float
    ci_high: float
    rollouts: int


def estimate_win_prob(
    request: OpeningPlacementRequest,
    user_placements: List[Tuple[int, Edge]],
    n_rollouts: int,
    policy: PolicyFactory = rollout_policy,
    rules: RulesConfig = COLONIST_1V1,
    seed_base: int = 0,
) -> WinEstimate:
    """Estimate P(user wins) given the user's opening ``user_placements`` (a list of
    (settlement, road); length 1 for FIRST/FIRST_FINAL, 2 for SECOND)."""
    wins = 0
    for i in range(n_rollouts):
        game, user = drive_to_user_decision(request, policy, seed=seed_base + i, rules=rules)
        for settlement, road in user_placements:
            game.execute(Action(user, ActionType.BUILD_SETTLEMENT, settlement))
            game.execute(_pick_road(game, road))
        if game.play() == user:
            wins += 1
    win_prob = wins / n_rollouts if n_rollouts else 0.0
    lo, hi = wilson_interval(wins, n_rollouts)
    return WinEstimate(win_prob, lo, hi, n_rollouts)
