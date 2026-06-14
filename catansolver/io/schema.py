"""Pydantic schema for a Colonist.io 1v1 Catan game state.

Conventions (aligned with Catanatron's board indexing):
  * hex ids are 0..18, node ids are 0..53, edges are unordered ``(lo, hi)`` node pairs.
  * resource/dev-card/port names match Catanatron's string enums.

The schema validates *board legality* (the standard base-game composition) so the
UI can never submit a malformed board. It does not yet validate placement legality
(distance rule, connectivity) — that is the engine adapter's job in Phase 1.
"""

from __future__ import annotations

from collections import Counter
from enum import Enum
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator, model_validator

# A road/port edge: an unordered pair of node ids, stored sorted.
Edge = Tuple[int, int]

MAX_NODE_ID = 53


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class Resource(str, Enum):
    WOOD = "WOOD"
    BRICK = "BRICK"
    SHEEP = "SHEEP"
    WHEAT = "WHEAT"
    ORE = "ORE"


class HexResource(str, Enum):
    WOOD = "WOOD"
    BRICK = "BRICK"
    SHEEP = "SHEEP"
    WHEAT = "WHEAT"
    ORE = "ORE"
    DESERT = "DESERT"


class PortType(str, Enum):
    GENERIC = "3:1"  # 3:1 any-resource port
    WOOD = "WOOD"
    BRICK = "BRICK"
    SHEEP = "SHEEP"
    WHEAT = "WHEAT"
    ORE = "ORE"


class DraftSeat(str, Enum):
    """Which opening decision the user faces (see plan.md §6.3)."""

    FIRST = "FIRST"  # P1 opener: empty board -> recommend 1 placement
    SECOND = "SECOND"  # P2: opponent's 1st down -> recommend BOTH placements (jointly)
    FIRST_FINAL = "FIRST_FINAL"  # P1 final: 3 settlements down -> recommend 1 placement


class Phase(str, Enum):
    SETUP = "SETUP"
    PLAY = "PLAY"


# Standard base-game composition (also the Colonist 1v1 board).
HEX_RESOURCE_COUNTS: Dict[HexResource, int] = {
    HexResource.WOOD: 4,
    HexResource.SHEEP: 4,
    HexResource.WHEAT: 4,
    HexResource.BRICK: 3,
    HexResource.ORE: 3,
    HexResource.DESERT: 1,
}
NUMBER_TOKEN_COUNTS: Dict[int, int] = {2: 1, 3: 2, 4: 2, 5: 2, 6: 2, 8: 2, 9: 2, 10: 2, 11: 2, 12: 1}
PORT_TYPE_COUNTS: Dict[PortType, int] = {
    PortType.GENERIC: 4,
    PortType.WOOD: 1,
    PortType.BRICK: 1,
    PortType.SHEEP: 1,
    PortType.WHEAT: 1,
    PortType.ORE: 1,
}


# --------------------------------------------------------------------------- #
# Board
# --------------------------------------------------------------------------- #
class Hex(BaseModel):
    id: int = Field(ge=0, le=18)
    resource: HexResource
    number: Optional[int] = Field(default=None, ge=2, le=12)

    @model_validator(mode="after")
    def _desert_number_consistency(self) -> "Hex":
        if self.resource == HexResource.DESERT:
            if self.number is not None:
                raise ValueError(f"desert hex {self.id} must not carry a number token")
        else:
            if self.number is None:
                raise ValueError(f"non-desert hex {self.id} needs a number token")
            if self.number == 7:
                raise ValueError("7 is never a hex number token")
        return self


class Port(BaseModel):
    type: PortType
    nodes: Edge  # the two node ids that can use this port

    @field_validator("nodes")
    @classmethod
    def _two_distinct_sorted(cls, v: Edge) -> Edge:
        if len(v) != 2 or v[0] == v[1]:
            raise ValueError("a port must attach to two distinct nodes")
        if not all(0 <= n <= MAX_NODE_ID for n in v):
            raise ValueError(f"port node ids must be in 0..{MAX_NODE_ID}")
        return tuple(sorted(v))


class BoardState(BaseModel):
    hexes: List[Hex]
    ports: List[Port]
    robber_hex: int = Field(ge=0, le=18)

    @field_validator("hexes")
    @classmethod
    def _check_hex_composition(cls, hexes: List[Hex]) -> List[Hex]:
        if len(hexes) != 19:
            raise ValueError(f"board needs exactly 19 hexes, got {len(hexes)}")
        if sorted(h.id for h in hexes) != list(range(19)):
            raise ValueError("hex ids must be exactly 0..18 with no duplicates")
        resources = Counter(h.resource for h in hexes)
        if dict(resources) != HEX_RESOURCE_COUNTS:
            raise ValueError(f"bad hex resource composition: {dict(resources)}")
        tokens = Counter(h.number for h in hexes if h.number is not None)
        if dict(tokens) != NUMBER_TOKEN_COUNTS:
            raise ValueError(f"bad number-token composition: {dict(tokens)}")
        return hexes

    @field_validator("ports")
    @classmethod
    def _check_port_composition(cls, ports: List[Port]) -> List[Port]:
        if len(ports) != 9:
            raise ValueError(f"board needs exactly 9 ports, got {len(ports)}")
        composition = Counter(p.type for p in ports)
        if dict(composition) != PORT_TYPE_COUNTS:
            raise ValueError(f"bad port composition: {dict(composition)}")
        return ports

    @model_validator(mode="after")
    def _robber_on_existing_hex(self) -> "BoardState":
        if self.robber_hex not in {h.id for h in self.hexes}:
            raise ValueError("robber_hex must reference an existing hex id")
        return self


# --------------------------------------------------------------------------- #
# Players + game
# --------------------------------------------------------------------------- #
class Hand(BaseModel):
    wood: int = Field(default=0, ge=0)
    brick: int = Field(default=0, ge=0)
    sheep: int = Field(default=0, ge=0)
    wheat: int = Field(default=0, ge=0)
    ore: int = Field(default=0, ge=0)

    @property
    def total(self) -> int:
        return self.wood + self.brick + self.sheep + self.wheat + self.ore


class DevCards(BaseModel):
    """Development cards held in hand (face down)."""

    knight: int = Field(default=0, ge=0)
    year_of_plenty: int = Field(default=0, ge=0)
    monopoly: int = Field(default=0, ge=0)
    road_building: int = Field(default=0, ge=0)
    victory_point: int = Field(default=0, ge=0)


class PlayerState(BaseModel):
    color: str  # stable id, e.g. "P1"/"P2" or a Catanatron color name
    hand: Hand = Field(default_factory=Hand)
    dev_cards: DevCards = Field(default_factory=DevCards)
    played_knights: int = Field(default=0, ge=0)
    settlements: List[int] = Field(default_factory=list)  # node ids
    cities: List[int] = Field(default_factory=list)  # node ids
    roads: List[Edge] = Field(default_factory=list)
    has_longest_road: bool = False
    has_largest_army: bool = False

    @field_validator("settlements", "cities")
    @classmethod
    def _nodes_in_range(cls, v: List[int]) -> List[int]:
        for n in v:
            if not (0 <= n <= MAX_NODE_ID):
                raise ValueError(f"node id {n} out of range 0..{MAX_NODE_ID}")
        return v


class GameState(BaseModel):
    board: BoardState
    players: List[PlayerState]
    bank: Hand = Field(default_factory=lambda: Hand(wood=19, brick=19, sheep=19, wheat=19, ore=19))
    dev_deck_remaining: int = Field(default=25, ge=0, le=25)
    current_player: str
    phase: Phase = Phase.PLAY
    dice: Optional[Tuple[int, int]] = None
    # ruleset (mirrors RulesConfig; lets a state be self-describing)
    vps_to_win: int = 15
    discard_limit: int = 9
    friendly_robber: bool = True

    @field_validator("players")
    @classmethod
    def _exactly_two_players(cls, v: List[PlayerState]) -> List[PlayerState]:
        if len(v) != 2:
            raise ValueError(f"1v1 needs exactly 2 players, got {len(v)}")
        if len({p.color for p in v}) != 2:
            raise ValueError("the two players must have distinct colors")
        return v

    @model_validator(mode="after")
    def _current_player_is_a_player(self) -> "GameState":
        colors = {p.color for p in self.players}
        if self.current_player not in colors:
            raise ValueError(f"current_player {self.current_player!r} is not one of {colors}")
        return self


# --------------------------------------------------------------------------- #
# MVP request: opening-placement query
# --------------------------------------------------------------------------- #
class OpeningPlacementRequest(BaseModel):
    """The MVP's input: a board plus the draft situation, asking for the user's
    best opening placement(s). The three :class:`DraftSeat` values encode the
    three scenarios from plan.md §6.3, and the validator enforces that the number
    of settlements already on the board matches the seat.
    """

    board: BoardState
    seat: DraftSeat
    user_color: str = "P1"
    settlements: Dict[str, List[int]] = Field(default_factory=dict)  # color -> node ids
    roads: Dict[str, List[Edge]] = Field(default_factory=dict)  # color -> edges

    #: settlements expected already on the board for each seat
    _EXPECTED_PLACED = {DraftSeat.FIRST: 0, DraftSeat.SECOND: 1, DraftSeat.FIRST_FINAL: 3}

    @model_validator(mode="after")
    def _placements_match_seat(self) -> "OpeningPlacementRequest":
        placed = sum(len(v) for v in self.settlements.values())
        expected = self._EXPECTED_PLACED[self.seat]
        if placed != expected:
            raise ValueError(
                f"seat {self.seat.value} expects {expected} settlement(s) already on the "
                f"board, found {placed}"
            )
        return self
