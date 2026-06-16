"""Board geometry for the UI: pixel positions for hexes, nodes, edges, and ports.

Derived from Catanatron's fixed topology (resource-independent). Hex centres come
from cube coordinates in a pointy-top layout; node positions are hex-corner offsets
*averaged* over the hexes that share each node, so shared corners coincide exactly
and clicks map straight to Catanatron node ids (0..53).
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

from catanatron.models.map import NodeRef

from catansolver.engine.adapter import (
    _canonical_map,
    canonical_hex_adjacency,
    canonical_port_slots,
)

SQRT3 = math.sqrt(3.0)

# Pointy-top hex corner offsets in screen coordinates (y points down), in units of
# the hex circumradius (`size`).
_CORNER: Dict[NodeRef, Tuple[float, float]] = {
    NodeRef.NORTH: (0.0, -1.0),
    NodeRef.NORTHEAST: (SQRT3 / 2, -0.5),
    NodeRef.SOUTHEAST: (SQRT3 / 2, 0.5),
    NodeRef.SOUTH: (0.0, 1.0),
    NodeRef.SOUTHWEST: (-SQRT3 / 2, 0.5),
    NodeRef.NORTHWEST: (-SQRT3 / 2, -0.5),
}


def _hex_center(cube: Tuple[int, int, int], size: float) -> Tuple[float, float]:
    x, _y, z = cube  # cube coords satisfy x + y + z == 0; axial q=x, r=z
    return (size * SQRT3 * (x + z / 2.0), size * 1.5 * z)


def board_geometry(size: float = 56.0, padding: float = 46.0) -> dict:
    """Compute a renderable layout. All coordinates are translated into a padded
    viewport of the returned ``width`` x ``height``."""
    cmap = _canonical_map()

    raw_hex: Dict[int, Tuple[float, float]] = {}
    node_acc: Dict[int, List[Tuple[float, float]]] = {}
    node_hexes: Dict[int, List[int]] = {}
    for coord, tile in cmap.land_tiles.items():
        cx, cy = _hex_center(coord, size)
        raw_hex[tile.id] = (cx, cy)
        for noderef, node_id in tile.nodes.items():
            ox, oy = _CORNER[noderef]
            node_acc.setdefault(node_id, []).append((cx + ox * size, cy + oy * size))
            node_hexes.setdefault(node_id, []).append(tile.id)

    raw_node = {
        nid: (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        for nid, pts in node_acc.items()
    }

    centroid_x = sum(p[0] for p in raw_node.values()) / len(raw_node)
    centroid_y = sum(p[1] for p in raw_node.values()) / len(raw_node)

    raw_port: List[Tuple[int, int, float, float]] = []
    for a, b in canonical_port_slots():
        ax, ay = raw_node[a]
        bx, by = raw_node[b]
        mx, my = (ax + bx) / 2, (ay + by) / 2
        dx, dy = mx - centroid_x, my - centroid_y
        dist = math.hypot(dx, dy) or 1.0
        raw_port.append((a, b, mx + dx / dist * size * 0.55, my + dy / dist * size * 0.55))

    xs = [p[0] for p in raw_node.values()] + [p[2] for p in raw_port]
    ys = [p[1] for p in raw_node.values()] + [p[3] for p in raw_port]
    minx, miny = min(xs), min(ys)

    def tx(x: float) -> float:
        return round(x - minx + padding, 2)

    def ty(y: float) -> float:
        return round(y - miny + padding, 2)

    edges = sorted({tuple(sorted(e)) for t in cmap.land_tiles.values() for e in t.edges.values()})

    return {
        "size": size,
        "width": round(max(xs) - minx + 2 * padding, 1),
        "height": round(max(ys) - miny + 2 * padding, 1),
        "hexes": [{"id": hid, "x": tx(x), "y": ty(y)} for hid, (x, y) in sorted(raw_hex.items())],
        "nodes": [{"id": nid, "x": tx(x), "y": ty(y)} for nid, (x, y) in sorted(raw_node.items())],
        "edges": [
            {
                "a": a,
                "b": b,
                "x1": tx(raw_node[a][0]),
                "y1": ty(raw_node[a][1]),
                "x2": tx(raw_node[b][0]),
                "y2": ty(raw_node[b][1]),
            }
            for a, b in edges
        ],
        "ports": [{"a": a, "b": b, "x": tx(px), "y": ty(py)} for (a, b, px, py) in raw_port],
        "hex_adjacency": [
            [a, b] for a, nbrs in canonical_hex_adjacency().items() for b in nbrs if a < b
        ],
        # node id -> the hex ids touching it (for describing a spot by its numbers)
        "node_hexes": {nid: sorted(hids) for nid, hids in sorted(node_hexes.items())},
    }
