"""Spiral number-token layout (catansolver/engine/spiral.py)."""
from collections import Counter

from catansolver.engine.adapter import adjacent_red_pairs, map_to_schema
from catansolver.engine.spiral import SPIRAL_NUMBERS, _OUTER, apply_spiral_numbers, spiral_order
from catansolver.io.schema import NUMBER_TOKEN_COUNTS, HexResource

from catanatron.models.map import BASE_MAP_TEMPLATE, CatanMap


def _board():
    return map_to_schema(CatanMap.from_template(BASE_MAP_TEMPLATE))


def _reads_as_spiral(board) -> bool:
    """True if, for some start hex + direction, the non-desert numbers along the spiral
    equal the canonical sequence."""
    by_id = {h.id: h for h in board.hexes}
    desert = next(h.id for h in board.hexes if h.resource == HexResource.DESERT)
    for start in _OUTER:
        for d in (1, -1):
            if [by_id[h].number for h in spiral_order(start, d) if h != desert] == SPIRAL_NUMBERS:
                return True
    return False


def test_canonical_sequence_distribution():
    assert dict(Counter(SPIRAL_NUMBERS)) == NUMBER_TOKEN_COUNTS  # one 2/12, two of the rest


def test_spiral_order_covers_all_hexes():
    order = spiral_order(_OUTER[0], 1)
    assert sorted(order) == list(range(19))  # 19 distinct hexes, centre last
    assert order[-1] == 0
    assert order[0] == _OUTER[0]


def test_apply_spiral_numbers_lays_the_sequence():
    board = apply_spiral_numbers(_board())
    desert = [h for h in board.hexes if h.resource == HexResource.DESERT]
    assert len(desert) == 1 and desert[0].number is None  # no token on the desert
    assert dict(Counter(h.number for h in board.hexes if h.number is not None)) == NUMBER_TOKEN_COUNTS
    assert _reads_as_spiral(board)


def test_first_number_lands_on_an_outer_hex():
    # the chosen start is always an outer hex (unless it is the desert, then the sequence
    # simply starts on the next hex) — the canonical '5' sits on an outer hex on a clear board.
    import random
    random.seed(0)
    for _ in range(20):
        board = apply_spiral_numbers(_board())
        assert _reads_as_spiral(board)
