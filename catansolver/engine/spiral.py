"""Spiral number-token layout (matches the physical game / Colonist).

Catan's number tokens are not placed at random: they follow a fixed canonical sequence
(the lettered A–R chits) laid out in a **spiral** over the land hexes, skipping the desert.
The sequence is designed so the high-pip reds (6 & 8) stay spread apart.

We keep that fixed sequence but **randomise where the spiral starts** (any outer hex) and its
direction, so the number *geography* still varies board-to-board while the pattern stays
balanced. Terrain (resources + desert) is shuffled independently; the desert hex gets no
token and the sequence simply continues on the next hex.
"""

from __future__ import annotations

import math
import random

from catansolver.engine.adapter import canonical_tile_coordinates
from catansolver.io.schema import BoardState, HexResource

# Canonical token order (A→R): exactly one 2 and one 12, two of every other value (18 total).
SPIRAL_NUMBERS = [5, 2, 6, 3, 8, 10, 9, 12, 11, 4, 8, 10, 9, 4, 5, 6, 3, 11]


def _rings_and_angles():
    """Group the 19 canonical hex ids into rings (0 centre, 1 middle, 2 outer) and record
    each hex's angle about the board centre, so we can walk a ring in angular order."""
    coords = canonical_tile_coordinates()
    rings = {0: [], 1: [], 2: []}
    angle = {}
    for hid, (x, y, z) in coords.items():
        rings[(abs(x) + abs(y) + abs(z)) // 2].append(hid)
        angle[hid] = math.degrees(math.atan2(1.5 * z, math.sqrt(3) * (x + z / 2))) % 360.0
    for hids in rings.values():
        hids.sort(key=lambda h: angle[h])
    return rings, angle


_RINGS, _ANGLE = _rings_and_angles()
_OUTER, _MIDDLE, _CENTER = _RINGS[2], _RINGS[1], _RINGS[0][0]


def spiral_order(start: int, direction: int) -> list:
    """Hex-id order for an inward spiral that starts at outer hex ``start`` and turns
    ``direction`` (+1 = increasing angle, -1 = decreasing): the full outer ring, then the
    middle ring (entered alongside the start), then the centre."""
    oi = _OUTER.index(start)
    outer = [_OUTER[(oi + direction * k) % len(_OUTER)] for k in range(len(_OUTER))]
    sa = _ANGLE[start]
    mstart = min(_MIDDLE, key=lambda m: min((_ANGLE[m] - sa) % 360, (sa - _ANGLE[m]) % 360))
    mi = _MIDDLE.index(mstart)
    middle = [_MIDDLE[(mi + direction * k) % len(_MIDDLE)] for k in range(len(_MIDDLE))]
    return outer + middle + [_CENTER]


def apply_spiral_numbers(board: BoardState, rng=random) -> BoardState:
    """Re-lay ``board``'s number tokens as the canonical spiral, with a randomly chosen outer
    starting hex + direction, skipping the desert. Mutates and returns ``board``."""
    desert_id = next(h.id for h in board.hexes if h.resource == HexResource.DESERT)
    order = spiral_order(rng.choice(_OUTER), rng.choice((1, -1)))
    by_id = {h.id: h for h in board.hexes}
    seq = iter(SPIRAL_NUMBERS)
    for hid in order:
        by_id[hid].number = None if hid == desert_id else next(seq)
    return board
