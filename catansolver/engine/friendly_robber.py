"""Friendly Robber rule (Colonist.io 1v1).

A player may only be blocked/stolen from once they *openly* hold >= 3 victory
points. This is the one 1v1 delta Catanatron does not support natively.

Catanatron generates robber moves in ``catanatron.models.actions.robber_possibilities``,
which builds, per tile, the set of colors that can be stolen from. We replace that
function with one that additionally filters the steal-target set by visible VP.
The action dispatcher (``generate_playable_actions``) calls it as a module-level
name, so monkeypatching the module attribute is sufficient.

"Visible" (not "actual") VP is used deliberately: hidden Victory-Point dev cards
do not count toward the threshold, matching "openly have more than 2 Points".
"""

from typing import List, Optional

from catanatron.models.enums import Action, ActionType
from catanatron.state_functions import (
    get_visible_victory_points,
    player_num_resource_cards,
)

DEFAULT_MIN_VP = 3


def friendly_robber_possibilities(state, color, min_vp: int = DEFAULT_MIN_VP) -> List[Action]:
    """Like ``catanatron.models.actions.robber_possibilities`` but enforcing the
    Friendly Robber rule: a player is only a valid steal target once they hold
    >= ``min_vp`` *visible* victory points.

    Tiles whose only occupants are protected (low-VP) players still yield a
    "move-but-can't-steal" action, so the robber can always be moved.
    """
    actions: List[Action] = []
    for coordinate, tile in state.board.map.land_tiles.items():
        if coordinate == state.board.robber_coordinate:
            continue  # must actually move the robber

        to_steal_from = set()
        for _, node_id in tile.nodes.items():
            building = state.board.buildings.get(node_id, None)
            if building is None:
                continue
            candidate_color = building[0]
            if (
                candidate_color != color
                and player_num_resource_cards(state, candidate_color) >= 1
                and get_visible_victory_points(state, candidate_color) >= min_vp
            ):
                to_steal_from.add(candidate_color)

        if len(to_steal_from) == 0:
            actions.append(Action(color, ActionType.MOVE_ROBBER, (coordinate, None, None)))
        else:
            for enemy_color in to_steal_from:
                actions.append(
                    Action(color, ActionType.MOVE_ROBBER, (coordinate, enemy_color, None))
                )
    return actions


_original: Optional[object] = None


def patch_friendly_robber() -> None:
    """Monkeypatch Catanatron to use the Friendly Robber rule. Idempotent."""
    import catanatron.models.actions as actions_mod

    global _original
    if _original is None:
        _original = actions_mod.robber_possibilities
    actions_mod.robber_possibilities = friendly_robber_possibilities


def unpatch_friendly_robber() -> None:
    """Restore Catanatron's stock robber rule (useful for tests)."""
    import catanatron.models.actions as actions_mod

    global _original
    if _original is not None:
        actions_mod.robber_possibilities = _original
        _original = None
