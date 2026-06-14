"""Tests for the Friendly Robber injection — the one custom 1v1 rule.

These call ``friendly_robber_possibilities`` directly on a crafted state so we
can control victim VP without playing a full game.
"""

from catanatron import Color, Game, RandomPlayer
from catanatron.models.enums import SETTLEMENT
from catanatron.state_functions import player_key

from catansolver.engine import new_1v1_game
from catansolver.engine.friendly_robber import (
    friendly_robber_possibilities,
    patch_friendly_robber,
    unpatch_friendly_robber,
)


def _fresh_state():
    game = Game([RandomPlayer(Color.RED), RandomPlayer(Color.BLUE)], seed=1)
    return game.state


def _place_victim_on_a_tile(state, victim_color):
    """Place ``victim_color``'s settlement on a node of some non-robber tile and
    give them a resource card. Returns nothing; mutates ``state``."""
    robber_coord = state.board.robber_coordinate
    _, tile = next(
        (coord, t) for coord, t in state.board.map.land_tiles.items() if coord != robber_coord
    )
    node_id = next(iter(tile.nodes.values()))
    state.board.buildings[node_id] = (victim_color, SETTLEMENT)
    state.player_state[f"{player_key(state, victim_color)}_WOOD_IN_HAND"] = 1


def test_low_vp_victim_cannot_be_stolen_from():
    state = _fresh_state()
    mover, victim = list(state.colors)
    _place_victim_on_a_tile(state, victim)

    state.player_state[f"{player_key(state, victim)}_VICTORY_POINTS"] = 2  # protected
    actions = friendly_robber_possibilities(state, mover)
    assert actions, "robber must always have somewhere to move"
    assert not any(a.value[1] == victim for a in actions)


def test_victim_at_three_vp_can_be_stolen_from():
    state = _fresh_state()
    mover, victim = list(state.colors)
    _place_victim_on_a_tile(state, victim)

    state.player_state[f"{player_key(state, victim)}_VICTORY_POINTS"] = 3  # now fair game
    actions = friendly_robber_possibilities(state, mover)
    assert any(a.value[1] == victim for a in actions)


def test_patch_is_idempotent_and_reversible():
    import catanatron.models.actions as actions_mod

    # The patch is process-global, so other tests may have applied it already.
    # Normalize to a clean baseline first, then capture the true original.
    unpatch_friendly_robber()
    original = actions_mod.robber_possibilities
    assert original is not friendly_robber_possibilities

    patch_friendly_robber()
    assert actions_mod.robber_possibilities is friendly_robber_possibilities
    patch_friendly_robber()  # idempotent
    assert actions_mod.robber_possibilities is friendly_robber_possibilities

    unpatch_friendly_robber()
    assert actions_mod.robber_possibilities is original


def test_new_1v1_game_applies_config():
    game = new_1v1_game([RandomPlayer(Color.RED), RandomPlayer(Color.BLUE)], seed=7)
    assert game.vps_to_win == 15
    assert game.state.discard_limit == 9


def test_new_1v1_game_rejects_wrong_player_count():
    import pytest

    with pytest.raises(ValueError):
        new_1v1_game([RandomPlayer(Color.RED)])
