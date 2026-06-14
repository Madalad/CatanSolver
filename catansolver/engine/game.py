"""Factory for a Colonist.io 1v1 Catanatron game with our ruleset applied."""

from typing import Iterable, List, Optional

from catanatron import Game, Player

from .config import COLONIST_1V1, RulesConfig
from .friendly_robber import patch_friendly_robber


def new_1v1_game(
    players: Iterable[Player],
    rules: RulesConfig = COLONIST_1V1,
    seed: Optional[int] = None,
    catan_map=None,
) -> Game:
    """Create a 2-player Catan game configured for the Colonist 1v1 ruleset.

    Sets ``vps_to_win`` and ``discard_limit`` from ``rules`` and (idempotently)
    installs the Friendly Robber patch when enabled.

    Note: the Friendly Robber patch is global to the Catanatron process once
    applied — intentional, since the whole tool targets the 1v1 ruleset.
    """
    player_list: List[Player] = list(players)
    if len(player_list) != 2:
        raise ValueError(f"1v1 requires exactly 2 players, got {len(player_list)}")

    if rules.friendly_robber:
        patch_friendly_robber()

    return Game(
        player_list,
        seed=seed,
        discard_limit=rules.discard_limit,
        vps_to_win=rules.vps_to_win,
        catan_map=catan_map,
    )
