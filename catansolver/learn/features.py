"""Position features for the learned value function (Phase 5.1).

Engineers a fixed-length vector describing a position **from a given player's
perspective** — mostly ``me - opponent`` differences (VP, production, roads, army, hand,
dev cards) plus a couple of absolutes for game stage. Designed to be a strictly richer
superset of the hand-tuned VP-lead leaf heuristic it will replace, and cheap to compute
(a few dict lookups + the precomputed ``map.node_production``).
"""
from __future__ import annotations

from typing import List

import numpy as np
from catanatron.models.enums import DEVELOPMENT_CARDS, RESOURCES
from catanatron.state_functions import get_actual_victory_points, player_key

# stable resource order for the production features
_RES = list(RESOURCES)  # ['WOOD','BRICK','SHEEP','WHEAT','ORE']

FEATURE_NAMES: List[str] = (
    ["d_vp", "d_settlements", "d_cities"]
    + [f"d_prod_{r.lower()}" for r in _RES]
    + ["d_total_prod", "d_road_len", "d_longest_road", "d_knights", "d_largest_army",
       "d_hand", "d_dev"]
    + ["me_vp", "max_vp", "to_move_is_me"]
)


def _player_stats(state, color) -> dict:
    key = player_key(state, color)
    ps = state.player_state
    buildings = state.buildings_by_color[color]
    settlements = buildings.get("SETTLEMENT", [])
    cities = buildings.get("CITY", [])

    node_production = state.board.map.node_production
    prod = {r: 0.0 for r in _RES}
    for node in settlements:
        for r, p in node_production.get(node, {}).items():
            prod[r] += p
    for node in cities:  # a city produces double
        for r, p in node_production.get(node, {}).items():
            prod[r] += 2.0 * p

    return {
        "vp": get_actual_victory_points(state, color),
        "n_set": len(settlements),
        "n_city": len(cities),
        "prod": prod,
        "total_prod": sum(prod.values()),
        "road_len": state.board.road_lengths.get(color, 0),
        "longest": 1.0 if ps[f"{key}_HAS_ROAD"] else 0.0,
        "knights": ps[f"{key}_PLAYED_KNIGHT"],
        "army": 1.0 if ps[f"{key}_HAS_ARMY"] else 0.0,
        "hand": sum(ps[f"{key}_{r}_IN_HAND"] for r in RESOURCES),
        "dev": sum(ps[f"{key}_{c}_IN_HAND"] for c in DEVELOPMENT_CARDS),
    }


def extract_features(game, color) -> np.ndarray:
    """Feature vector (``len(FEATURE_NAMES)``) for ``color`` in ``game``'s position."""
    state = game.state
    me = _player_stats(state, color)
    opp = _player_stats(state, next(c for c in state.colors if c != color))

    feats = [
        me["vp"] - opp["vp"],
        me["n_set"] - opp["n_set"],
        me["n_city"] - opp["n_city"],
        *[me["prod"][r] - opp["prod"][r] for r in _RES],
        me["total_prod"] - opp["total_prod"],
        me["road_len"] - opp["road_len"],
        me["longest"] - opp["longest"],
        me["knights"] - opp["knights"],
        me["army"] - opp["army"],
        me["hand"] - opp["hand"],
        me["dev"] - opp["dev"],
        float(me["vp"]),  # absolute proximity to the goal
        float(max(me["vp"], opp["vp"])),  # game stage
        1.0 if state.colors[state.current_player_index] == color else 0.0,
    ]
    return np.asarray(feats, dtype=float)
