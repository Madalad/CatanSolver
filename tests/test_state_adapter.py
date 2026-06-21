"""Mid-game state import/export round-trip.

The strong check is **round-trip stability**: export a played position to a
GameState, import it back, re-export, and require the two GameStates to be equal.
Since VPs are *derived* from buildings + bonuses + dev cards (all captured in the
schema), equality there implies the engine position was faithfully reconstructed —
including the recomputed Longest Road / Largest Army. We also confirm the imported
game is legal to keep playing.
"""
import random

import pytest
from catanatron import Color, RandomPlayer
from catanatron.models.map import BASE_MAP_TEMPLATE, CatanMap
from catanatron.players.weighted_random import WeightedRandomPlayer

from catansolver.engine import new_1v1_game
from catansolver.engine.adapter import game_from_board, map_to_schema
from catansolver.engine.state_adapter import SETTLEMENT, CITY, ROAD, game_from_state, game_to_state

SEEDS = [0, 1, 2, 7, 42, 123]


def _midgame(seed: int, ticks: int = 80):
    random.seed(seed)
    board = map_to_schema(CatanMap.from_template(BASE_MAP_TEMPLATE))
    game = game_from_board(board, [RandomPlayer(Color.RED), RandomPlayer(Color.BLUE)], seed=seed)
    for _ in range(ticks):
        if game.winning_color() is not None:
            break
        game.play_tick()
    return game


@pytest.mark.parametrize("seed", SEEDS)
def test_state_roundtrip_is_stable(seed):
    game = _midgame(seed)
    assert game.winning_color() is None  # still mid-game
    gs = game_to_state(game)
    gs2 = game_to_state(game_from_state(gs))
    assert gs == gs2


def test_deep_games_with_enemy_severed_roads_import_without_crashing():
    """Regression: long games produce roads severed from their owner's network by an
    enemy settlement. The connectivity fixpoint can't re-reach those, so the import
    force-places them rather than raising. Round-trip many deep positions and require
    every road to survive (and no exception)."""
    seen_positions = 0
    for seed in range(12):
        random.seed(seed)
        game = new_1v1_game(
            [WeightedRandomPlayer(Color.RED), WeightedRandomPlayer(Color.BLUE)], seed=seed
        )
        for t in range(220):
            if game.winning_color() is not None:
                break
            game.play_tick()
            if t >= 90 and t % 9 == 0:  # deep positions, where severing happens
                s1 = game.state
                s2 = game_from_state(game_to_state(game)).state  # must not raise
                for color in s1.colors:
                    r1 = {tuple(sorted(e)) for e in s1.buildings_by_color[color].get(ROAD, [])}
                    r2 = {tuple(sorted(e)) for e in s2.buildings_by_color[color].get(ROAD, [])}
                    assert r1 == r2  # all roads reproduced, severed ones included
                seen_positions += 1
    assert seen_positions > 0


def test_move_robber_prompt_round_trips():
    """The MOVE_ROBBER sub-prompt (and its action set) survives export/import, so the
    advisor can drive robber placement instead of falling back."""
    from catanatron.models.enums import ActionPrompt

    for seed in range(12):
        random.seed(seed)
        game = new_1v1_game(
            [WeightedRandomPlayer(Color.RED), WeightedRandomPlayer(Color.BLUE)], seed=seed
        )
        for _ in range(400):
            if game.winning_color() is not None:
                break
            if game.state.current_prompt == ActionPrompt.MOVE_ROBBER and len(game.state.playable_actions) > 1:
                gs = game_to_state(game)
                assert gs.prompt == "MOVE_ROBBER" and gs.has_rolled
                rebuilt = game_from_state(gs).state
                assert rebuilt.current_prompt == ActionPrompt.MOVE_ROBBER
                live = {a.action_type.name for a in game.state.playable_actions}
                assert {a.action_type.name for a in rebuilt.playable_actions} == live == {"MOVE_ROBBER"}
                return
            game.play_tick()
    pytest.skip("no multi-option MOVE_ROBBER state encountered")


@pytest.mark.parametrize("seed", SEEDS)
def test_import_reproduces_buildings_hands_bank(seed):
    game = _midgame(seed)
    s1 = game.state
    s2 = game_from_state(game_to_state(game)).state
    for color in s1.colors:
        b1, b2 = s1.buildings_by_color[color], s2.buildings_by_color[color]
        assert set(b1.get(SETTLEMENT, [])) == set(b2.get(SETTLEMENT, []))
        assert set(b1.get(CITY, [])) == set(b2.get(CITY, []))
        assert {tuple(sorted(e)) for e in b1.get(ROAD, [])} == {tuple(sorted(e)) for e in b2.get(ROAD, [])}
        # seating (color index) can differ between the games; key off each one's own
        k1, k2 = f"P{s1.color_to_index[color]}", f"P{s2.color_to_index[color]}"
        for r in ("WOOD", "BRICK", "SHEEP", "WHEAT", "ORE"):
            assert s1.player_state[f"{k1}_{r}_IN_HAND"] == s2.player_state[f"{k2}_{r}_IN_HAND"]
    assert s1.resource_freqdeck == s2.resource_freqdeck


def test_imported_game_is_playable():
    game2 = game_from_state(game_to_state(_midgame(7)))
    assert len(game2.state.playable_actions) > 0
    played = 0
    for _ in range(40):
        if game2.winning_color() is not None:
            break
        game2.play_tick()
        played += 1
    assert played > 0  # legal actions applied cleanly on the imported position


def test_victory_points_preserved():
    """VP is derived; check the engine agrees after a round-trip (catches Longest
    Road / Largest Army recompute bugs)."""
    from catanatron.state_functions import get_actual_victory_points
    game = _midgame(42)
    g2 = game_from_state(game_to_state(game))
    for color in game.state.colors:
        assert get_actual_victory_points(game.state, color) == get_actual_victory_points(g2.state, color)
