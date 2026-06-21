"""Opening-placement optimizer — Tier 1 / MVP (plan.md §6.3).

Pipeline: drive the draft to the user's decision point -> enumerate legal
placements -> heuristic pre-score -> prune to top-k -> Monte-Carlo rollouts ->
rank by estimated win probability.

Handles all three draft seats:
  * FIRST / FIRST_FINAL: a single settlement + road.
  * SECOND: a *joint* settlement pair (the second player commits both at once).
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from catanatron import Action, ActionType

from catansolver.engine.adapter import schema_to_map
from catansolver.engine.config import COLONIST_1V1, RulesConfig
from catansolver.io.schema import (
    DraftSeat,
    OpeningPlacementRequest,
    Placement,
    Recommendation,
)

from .draft import PolicyFactory, _pick_road, drive_to_user_decision, rollout_policy
from .heuristic import best_initial_road, node_score, pair_score
from .rollout import WinEstimate, estimate_win_prob
from .winprob_model import win_prob_estimate

Edge = Tuple[int, int]


def recommend_opening(
    request: OpeningPlacementRequest,
    *,
    top_k: int = 8,
    n_rollouts: int = 50,
    policy: PolicyFactory = rollout_policy,
    rules: RulesConfig = COLONIST_1V1,
    pair_top_first: int = 12,
    pair_top_second: int = 4,
) -> List[Recommendation]:
    """Rank opening placements for the user, best first.

    With ``n_rollouts > 0`` results are ranked by Monte-Carlo win probability
    (heuristic breaks ties); with ``n_rollouts == 0`` it is a fast heuristic-only
    ranking. Every recommendation also carries an instant ``model_win_prob``
    (logistic estimate from the heuristic). ``pair_top_*`` bound the SECOND search.
    """
    catan_map = schema_to_map(request.board)
    node_scores: Dict[int, float] = {n: node_score(catan_map, n) for n in catan_map.land_nodes}

    if request.seat == DraftSeat.SECOND:
        recs = _recommend_pair(
            request, catan_map, node_scores, top_k, n_rollouts, policy, rules,
            pair_top_first, pair_top_second,
        )
    else:
        recs = _recommend_single(request, catan_map, node_scores, top_k, n_rollouts, policy, rules)

    for r in recs:
        r.model_win_prob = win_prob_estimate(request.seat, r.heuristic_score)
    return recs


def _legal_settlements(game) -> List[int]:
    return [
        a.value
        for a in game.state.playable_actions
        if a.action_type == ActionType.BUILD_SETTLEMENT
    ]


def _recommend_single(
    request, catan_map, node_scores, top_k, n_rollouts, policy, rules
) -> List[Recommendation]:
    base_game, _user = drive_to_user_decision(request, policy, seed=0, rules=rules)
    candidates = sorted(_legal_settlements(base_game), key=node_scores.get, reverse=True)[:top_k]

    recs = []
    for node in candidates:
        road = best_initial_road(catan_map, node)
        est = (
            estimate_win_prob(request, [(node, road)], n_rollouts, policy, rules)
            if n_rollouts > 0
            else None
        )
        recs.append(_make_rec([(node, road)], node_scores[node], est))
    return _ranked(recs)


def _recommend_pair(
    request, catan_map, node_scores, top_k, n_rollouts, policy, rules, top_first, top_second
) -> List[Recommendation]:
    base_game, user = drive_to_user_decision(request, policy, seed=0, rules=rules)
    firsts = sorted(_legal_settlements(base_game), key=node_scores.get, reverse=True)[:top_first]

    scored_pairs = []
    for first in firsts:
        game = base_game.copy()
        road1 = best_initial_road(catan_map, first)
        game.execute(Action(user, ActionType.BUILD_SETTLEMENT, first))
        game.execute(_pick_road(game, road1))
        seconds = sorted(_legal_settlements(game), key=node_scores.get, reverse=True)[:top_second]
        for second in seconds:
            road2 = best_initial_road(catan_map, second)
            scored_pairs.append(
                (pair_score(catan_map, node_scores, first, second), first, road1, second, road2)
            )

    scored_pairs.sort(key=lambda t: t[0], reverse=True)

    recs, seen = [], set()
    for score, first, road1, second, road2 in scored_pairs:
        key = frozenset((first, second))  # the two orderings are the same pair
        if key in seen:
            continue
        seen.add(key)
        placements = [(first, road1), (second, road2)]
        est = (
            estimate_win_prob(request, placements, n_rollouts, policy, rules)
            if n_rollouts > 0
            else None
        )
        recs.append(_make_rec(placements, score, est))
        if len(recs) >= top_k:
            break
    return _ranked(recs)


def _make_rec(placements: List[Tuple[int, Edge]], heuristic: float, est: WinEstimate | None) -> Recommendation:
    return Recommendation(
        placements=[Placement(settlement=s, road=r) for s, r in placements],
        heuristic_score=round(heuristic, 4),
        win_prob=round(est.win_prob, 4) if est else None,
        ci_low=round(est.ci_low, 4) if est else None,
        ci_high=round(est.ci_high, 4) if est else None,
        rollouts=est.rollouts if est else 0,
    )


def _ranked(recs: List[Recommendation]) -> List[Recommendation]:
    recs.sort(
        key=lambda r: r.win_prob if r.win_prob is not None else r.heuristic_score,
        reverse=True,
    )
    return recs
