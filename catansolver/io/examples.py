"""Example states for tests and demos.

``example_board`` returns a *composition-valid* board (correct resource and
number-token multisets). It is not a realistic adjacency layout — node/edge
geometry is the engine adapter's concern (Phase 1) — but it is sufficient to
exercise the schema and validators.
"""

from .schema import BoardState, Hex, HexResource, Port, PortType


def example_board() -> BoardState:
    resources = (
        [HexResource.WOOD] * 4
        + [HexResource.SHEEP] * 4
        + [HexResource.WHEAT] * 4
        + [HexResource.BRICK] * 3
        + [HexResource.ORE] * 3
        + [HexResource.DESERT]  # 19th hex
    )
    tokens = [2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12]  # 18 tokens

    hexes = []
    token_iter = iter(tokens)
    for hex_id, resource in enumerate(resources):
        number = None if resource == HexResource.DESERT else next(token_iter)
        hexes.append(Hex(id=hex_id, resource=resource, number=number))

    ports = [
        Port(type=PortType.GENERIC, nodes=(0, 1)),
        Port(type=PortType.GENERIC, nodes=(2, 3)),
        Port(type=PortType.GENERIC, nodes=(4, 5)),
        Port(type=PortType.GENERIC, nodes=(6, 7)),
        Port(type=PortType.WOOD, nodes=(8, 9)),
        Port(type=PortType.BRICK, nodes=(10, 11)),
        Port(type=PortType.SHEEP, nodes=(12, 13)),
        Port(type=PortType.WHEAT, nodes=(14, 15)),
        Port(type=PortType.ORE, nodes=(16, 17)),
    ]

    desert_id = next(h.id for h in hexes if h.resource == HexResource.DESERT)
    return BoardState(hexes=hexes, ports=ports, robber_hex=desert_id)
