"""Approach B prototype — measure the real per-board cost (C_board) of a gold-standard
precomputed board: accurate advisor-self-play win-% for candidate opening placements.

Times the win-% for a few FIRST-seat candidates on one board via advisor self-play, then
extrapolates C_board for a full bank (K placements x G games x seats), serial and parallel.

Run:  .venv\\Scripts\\python.exe scripts\\board_bank_prototype.py [n_placements] [n_rollouts] [workers]
"""
import sys
import time
from functools import partial

from catanatron.models.map import BASE_MAP_TEMPLATE, CatanMap

from catansolver.engine import map_to_schema
from catansolver.eval import AdvisorPlayer
from catansolver.io.schema import DraftSeat, OpeningPlacementRequest
from catansolver.placement import estimate_win_prob, recommend_opening


def main():
    n_placements = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    n_rollouts = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 6

    board = map_to_schema(CatanMap.from_template(BASE_MAP_TEMPLATE))
    req = OpeningPlacementRequest(board=board, seat=DraftSeat.FIRST, user_color="P1")
    advisor = partial(AdvisorPlayer, value_model="docs/value_model.json",
                      n_determinizations=2, iterations=25, rollout_depth=0)

    candidates = recommend_opening(req, top_k=n_placements, n_rollouts=0)  # heuristic top-K
    print(f"timing accurate win-% for {n_placements} FIRST candidates, {n_rollouts} games each "
          f"(advisor self-play)\n")

    t0 = time.time()
    for rec in candidates:
        pl = [(rec.placements[0].settlement, tuple(rec.placements[0].road))]
        t = time.time()
        est = estimate_win_prob(req, pl, n_rollouts=n_rollouts, policy=advisor)
        print(f"  node {rec.placements[0].settlement:2d}: win {est.win_prob * 100:4.0f}%  "
              f"({time.time() - t:.0f}s for {n_rollouts} games)")
    total = time.time() - t0
    per_game = total / (n_placements * n_rollouts)
    print(f"\n~{per_game:.1f}s per self-play game (serial, measured)")

    # extrapolate C_board for a realistic bank
    K, G, seats = 15, 150, 3  # curated candidates/seat, games/candidate, seats
    c_serial = K * G * seats * per_game
    print(f"\nextrapolated C_board (K={K}/seat x G={G} games x {seats} seats):")
    print(f"  serial:        {c_serial / 3600:.1f} hr/board")
    print(f"  {workers} workers:     {c_serial / 3600 / workers:.1f} hr/board")
    print(f"  -> 40-board bank @ {workers} workers: {40 * c_serial / 3600 / workers:.0f} hr "
          f"({40 * c_serial / 3600 / workers / 24:.1f} days)")


if __name__ == "__main__":
    main()
