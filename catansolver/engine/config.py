"""Ruleset configuration for the engine.

Keeping the 1v1 deltas in one place means the rest of the codebase never
hard-codes them, and we could target a different ruleset by swapping this object.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RulesConfig:
    """Knobs that define the ruleset the engine plays under.

    Defaults are the Colonist.io 1v1 ruleset (see ``plan.md`` §3).
    """

    vps_to_win: int = 15
    discard_limit: int = 9  # discard on a 7 only when holding > discard_limit (i.e. >= 10)
    friendly_robber: bool = True
    friendly_robber_min_vp: int = 3  # may only steal from players with >= this many *visible* VP


#: The canonical Colonist.io 1v1 ruleset.
COLONIST_1V1 = RulesConfig()
