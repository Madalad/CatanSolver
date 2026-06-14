"""Engine layer: a thin adapter over Catanatron configured for the Colonist 1v1 ruleset.

Catanatron supports two of the three 1v1 deltas natively (``vps_to_win`` and
``discard_limit`` are constructor params). The third — Friendly Robber — is
injected via :mod:`catansolver.engine.friendly_robber`.
"""

from .adapter import board_from_game, game_from_board, map_to_schema, schema_to_map
from .config import COLONIST_1V1, RulesConfig
from .friendly_robber import patch_friendly_robber, unpatch_friendly_robber
from .game import new_1v1_game

__all__ = [
    "RulesConfig",
    "COLONIST_1V1",
    "new_1v1_game",
    "patch_friendly_robber",
    "unpatch_friendly_robber",
    "map_to_schema",
    "schema_to_map",
    "game_from_board",
    "board_from_game",
]
