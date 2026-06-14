"""Adapter between our pydantic schema and Catanatron's board model.

The hard direction is **import** (our ``BoardState`` -> a Catanatron ``CatanMap``),
because Catanatron normally generates a *random* board. The seam is
``initialize_tiles(template, numbers, port_resources, tile_resources)``: when given
explicit lists it uses them instead of shuffling, consuming each list with
``list.pop()`` — i.e. **back to front**. Catanatron assigns ``tile.id`` (and
``port.id``) in topology order starting at 0, so:

  * tile id ``i`` consumes ``tile_resources[-1 - i]``  -> pass ``reversed(by_id)``
  * non-desert tiles consume ``numbers`` in id order, back-to-front
  * port id ``k`` consumes ``port_resources[-1 - k]``  -> pass ``reversed(by_port_id)``

Node ids, tile ids, port positions/directions and edges are fixed by the topology
(independent of the random resource assignment), so we read those once from a
canonical base map and treat them as the shared coordinate system for our schema
(hex ids 0..18, node ids 0..53) and the future UI.
"""

from __future__ import annotations

import functools
from typing import Dict, Iterable, List, Optional, Tuple

from catanatron import Game, Player
from catanatron.models.map import (
    BASE_MAP_TEMPLATE,
    PORT_DIRECTION_TO_NODEREFS,
    CatanMap,
    initialize_tiles,
)

from catansolver.io.schema import BoardState, Hex, HexResource, Port, PortType

from .config import COLONIST_1V1, RulesConfig
from .game import new_1v1_game

Coordinate = Tuple[int, int, int]
NodePair = Tuple[int, int]

NUM_TILES = 19
NUM_PORTS = 9


# --------------------------------------------------------------------------- #
# Canonical (resource-independent) topology, read once from a base map.
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=1)
def _canonical_map() -> CatanMap:
    # Only the *structure* (ids, coordinates, node/port positions) is used; the
    # random resource assignment of this instance is irrelevant.
    return CatanMap.from_template(BASE_MAP_TEMPLATE)


@functools.lru_cache(maxsize=1)
def canonical_tile_coordinates() -> Dict[int, Coordinate]:
    """hex id (0..18) -> Catanatron cube coordinate."""
    return {tile.id: coord for coord, tile in _canonical_map().land_tiles.items()}


def _port_trading_nodes(port) -> NodePair:
    a_ref, b_ref = PORT_DIRECTION_TO_NODEREFS[port.direction]
    return tuple(sorted((port.nodes[a_ref], port.nodes[b_ref])))  # type: ignore[return-value]


@functools.lru_cache(maxsize=1)
def canonical_port_slots() -> List[NodePair]:
    """The 9 fixed port node-pairs, indexed by port id (0..8)."""
    cmap = _canonical_map()
    return [_port_trading_nodes(cmap.ports_by_id[pid]) for pid in sorted(cmap.ports_by_id)]


# --------------------------------------------------------------------------- #
# Resource <-> string helpers (Catanatron uses None for desert / 3:1 port).
# --------------------------------------------------------------------------- #
def _hexres_to_catan(resource: HexResource) -> Optional[str]:
    return None if resource == HexResource.DESERT else resource.value


def _catan_to_hexres(resource: Optional[str]) -> HexResource:
    return HexResource.DESERT if resource is None else HexResource(resource)


def _porttype_to_catan(port_type: PortType) -> Optional[str]:
    return None if port_type == PortType.GENERIC else port_type.value


def _catan_to_porttype(resource: Optional[str]) -> PortType:
    return PortType.GENERIC if resource is None else PortType(resource)


# --------------------------------------------------------------------------- #
# Export: Catanatron -> schema
# --------------------------------------------------------------------------- #
def map_to_schema(catan_map: CatanMap, robber_coordinate: Optional[Coordinate] = None) -> BoardState:
    """Convert a Catanatron ``CatanMap`` to our ``BoardState``."""
    hexes = [
        Hex(
            id=tile_id,
            resource=_catan_to_hexres(catan_map.tiles_by_id[tile_id].resource),
            number=catan_map.tiles_by_id[tile_id].number,
        )
        for tile_id in sorted(catan_map.tiles_by_id)
    ]
    ports = [
        Port(
            type=_catan_to_porttype(catan_map.ports_by_id[pid].resource),
            nodes=_port_trading_nodes(catan_map.ports_by_id[pid]),
        )
        for pid in sorted(catan_map.ports_by_id)
    ]
    if robber_coordinate is not None:
        robber_hex = catan_map.land_tiles[robber_coordinate].id
    else:  # default: desert tile
        robber_hex = next(t.id for t in catan_map.tiles_by_id.values() if t.resource is None)
    return BoardState(hexes=hexes, ports=ports, robber_hex=robber_hex)


def board_from_game(game: Game) -> BoardState:
    """Export the board (incl. current robber position) of a live game."""
    return map_to_schema(game.state.board.map, game.state.board.robber_coordinate)


# --------------------------------------------------------------------------- #
# Import: schema -> Catanatron
# --------------------------------------------------------------------------- #
def schema_to_map(board: BoardState) -> CatanMap:
    """Build a Catanatron ``CatanMap`` realising the exact layout in ``board``."""
    by_id: Dict[int, Hex] = {h.id: h for h in board.hexes}

    resources_by_id = [_hexres_to_catan(by_id[i].resource) for i in range(NUM_TILES)]
    numbers_in_id_order = [
        by_id[i].number for i in range(NUM_TILES) if by_id[i].resource != HexResource.DESERT
    ]

    port_by_nodes: Dict[NodePair, Port] = {tuple(sorted(p.nodes)): p for p in board.ports}
    resources_by_port_id: List[Optional[str]] = []
    for nodes in canonical_port_slots():  # already in port-id order 0..8
        port = port_by_nodes.get(nodes)
        if port is None:
            raise ValueError(f"board is missing a port at canonical position {nodes}")
        resources_by_port_id.append(_porttype_to_catan(port.type))

    # Reverse, because initialize_tiles consumes each list with pop() (back to front).
    tiles = initialize_tiles(
        BASE_MAP_TEMPLATE,
        list(reversed(numbers_in_id_order)),
        list(reversed(resources_by_port_id)),
        list(reversed(resources_by_id)),
    )
    return CatanMap.from_tiles(tiles)


def game_from_board(
    board: BoardState,
    players: Iterable[Player],
    rules: RulesConfig = COLONIST_1V1,
    seed: Optional[int] = None,
) -> Game:
    """Construct a 1v1 game on the exact ``board`` layout.

    The robber starts on the desert (Catanatron's default); if ``board.robber_hex``
    points elsewhere (a mid-game board) it is moved to match.
    """
    catan_map = schema_to_map(board)
    game = new_1v1_game(players, rules=rules, seed=seed, catan_map=catan_map)

    desert_id = next(h.id for h in board.hexes if h.resource == HexResource.DESERT)
    if board.robber_hex != desert_id:
        game.state.board.robber_coordinate = canonical_tile_coordinates()[board.robber_hex]
    return game
