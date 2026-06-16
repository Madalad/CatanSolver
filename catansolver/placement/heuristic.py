"""Heuristic scoring of opening settlement spots (plan.md §6.3).

Production-weighted (Wheat/Ore emphasised for the 15-VP game, per §3.8) plus
resource diversity and port synergy. Reuses Catanatron's precomputed
``map.node_production`` (node_id -> Counter({resource: dice-probability})).

Weights are hand-set for now and are intended to be tuned (Optuna) in Phase 4.
"""

from __future__ import annotations

from typing import Dict, Tuple

from catanatron.models.board import STATIC_GRAPH
from catanatron.models.enums import BRICK, ORE, SHEEP, WHEAT, WOOD

# Wheat/Ore dominate (cities, dev cards, knights); wood/brick keep real value for
# expansion + Longest Road; sheep slightly lower. See plan.md §3.8.
RESOURCE_WEIGHTS: Dict[str, float] = {
    WHEAT: 1.30,
    ORE: 1.20,
    BRICK: 1.05,
    WOOD: 1.00,
    SHEEP: 0.90,
}
DIVERSITY_BONUS = 0.04  # per distinct resource produced at the node
PORT_GENERIC_BONUS = 0.03  # 3:1 port
PORT_SPECIFIC_BONUS = 0.06  # 2:1 port (plus a kicker if we produce that resource)


def node_score(catan_map, node_id: int, weights: Dict[str, float] = RESOURCE_WEIGHTS) -> float:
    """Score a single settlement node: weighted expected production + diversity + ports."""
    production = catan_map.node_production.get(node_id, {})
    score = sum(weights.get(resource, 1.0) * prob for resource, prob in production.items())
    score += DIVERSITY_BONUS * len(production)
    score += _port_bonus(catan_map, node_id, production)
    return score


def _port_bonus(catan_map, node_id: int, production) -> float:
    bonus = 0.0
    for resource, nodes in catan_map.port_nodes.items():
        if node_id not in nodes:
            continue
        if resource is None:  # 3:1
            bonus += PORT_GENERIC_BONUS
        else:  # 2:1, more valuable if we actually produce that resource
            bonus += PORT_SPECIFIC_BONUS + 0.5 * production.get(resource, 0.0)
    return bonus


def best_initial_road(catan_map, node_id: int) -> Tuple[int, int]:
    """Suggest an initial road: the incident edge toward the highest-scoring
    neighbour node (a simple expansion-potential proxy)."""
    neighbors = [other for (_, other) in STATIC_GRAPH.edges(node_id)]
    best = max(neighbors, key=lambda n: node_score(catan_map, n))
    return tuple(sorted((node_id, best)))


PAIR_DIVERSITY_BONUS = 0.05  # reward pairs that cover more distinct resources together


def pair_score(catan_map, node_scores: Dict[int, float], s1: int, s2: int) -> float:
    """Heuristic for the second player's settlement *pair*: sum of node scores plus
    a bonus for the breadth of distinct resources covered across both spots."""
    resources = set(catan_map.node_production.get(s1, {})) | set(
        catan_map.node_production.get(s2, {})
    )
    return node_scores[s1] + node_scores[s2] + PAIR_DIVERSITY_BONUS * len(resources)
