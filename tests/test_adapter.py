"""Adapter tests: our schema <-> Catanatron's board model.

The key correctness check is that **import reproduces the exact tile/port
assignment** of a real Catanatron map (across several random seeds), and that a
game constructed on an imported board is fully playable.
"""

import random

import pytest
from catanatron import Color, RandomPlayer
from catanatron.models.map import BASE_MAP_TEMPLATE, CatanMap

from catansolver.engine.adapter import (
    board_from_game,
    canonical_port_slots,
    game_from_board,
    map_to_schema,
    schema_to_map,
)
from catansolver.io.schema import BoardState

SEEDS = [0, 1, 2, 7, 42, 123, 999]


def _base_map(seed: int) -> CatanMap:
    random.seed(seed)
    return CatanMap.from_template(BASE_MAP_TEMPLATE)


@pytest.mark.parametrize("seed", SEEDS)
def test_export_produces_valid_boardstate(seed):
    board = map_to_schema(_base_map(seed))
    assert isinstance(board, BoardState)  # passing construction means it validated
    assert len(board.hexes) == 19
    assert len(board.ports) == 9


@pytest.mark.parametrize("seed", SEEDS)
def test_import_reproduces_exact_assignment(seed):
    m1 = _base_map(seed)
    m2 = schema_to_map(map_to_schema(m1))
    for tile_id in range(19):
        t1, t2 = m1.tiles_by_id[tile_id], m2.tiles_by_id[tile_id]
        assert t1.resource == t2.resource
        assert t1.number == t2.number
        # node topology is fixed and must be preserved
        assert set(t1.nodes.values()) == set(t2.nodes.values())
    for port_id in range(9):
        assert m1.ports_by_id[port_id].resource == m2.ports_by_id[port_id].resource


@pytest.mark.parametrize("seed", SEEDS)
def test_schema_roundtrip_is_identity(seed):
    board1 = map_to_schema(_base_map(seed))
    board2 = map_to_schema(schema_to_map(board1))
    assert board1 == board2


def test_exported_ports_use_canonical_positions():
    board = map_to_schema(_base_map(0))
    assert {tuple(sorted(p.nodes)) for p in board.ports} == set(canonical_port_slots())


def test_game_from_board_preserves_board_and_is_playable():
    board = map_to_schema(_base_map(7))
    game = game_from_board(
        board, [RandomPlayer(Color.RED), RandomPlayer(Color.BLUE)], seed=7
    )
    # the imported layout survives construction (robber on desert at start)
    assert board_from_game(game) == board
    # opening: every node is available for the first settlement
    assert len(game.state.playable_actions) == 54
    # legal actions apply cleanly on the imported board (draft + a few turns)
    for _ in range(50):
        if game.winning_color() is not None:
            break
        game.play_tick()
