"""Demo: print ranked opening placements for a random board (FIRST seat).

Run: .\.venv\Scripts\python.exe scripts\recommend_demo.py
"""

import random

from catanatron.models.map import BASE_MAP_TEMPLATE, CatanMap

from catansolver.engine.adapter import map_to_schema
from catansolver.io.schema import DraftSeat, OpeningPlacementRequest
from catansolver.placement import recommend_opening


def main() -> None:
    random.seed(7)
    board = map_to_schema(CatanMap.from_template(BASE_MAP_TEMPLATE))
    request = OpeningPlacementRequest(board=board, seat=DraftSeat.FIRST, user_color="P1")

    recs = recommend_opening(request, top_k=5, n_rollouts=20)

    print("Top opening placements (going first):")
    for i, r in enumerate(recs, 1):
        spots = "  ".join(f"S@{p.settlement} R{tuple(p.road)}" for p in r.placements)
        print(
            f" #{i}  {spots}  win={r.win_prob:.0%} "
            f"[{r.ci_low:.0%}, {r.ci_high:.0%}]  h={r.heuristic_score:.3f}"
        )


if __name__ == "__main__":
    main()
