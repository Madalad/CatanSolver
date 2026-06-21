"""CLI demo of the Phase 3.4 PIMC turn advisor: build a mid-game position, then print
the ranked actions with per-action win-prob, aggregated over determinized UCT searches.

Run (repo root, Anaconda PATH + PYTHONPATH set):
    .\\.venv\\Scripts\\python.exe scripts\\pimc_demo.py [seed] [ticks] [determinizations] [iterations]
"""
import random
import sys
import time

from catanatron import Color, RandomPlayer
from catanatron.models.map import BASE_MAP_TEMPLATE, CatanMap

from catansolver.advisor import recommend_actions_pimc
from catansolver.engine import game_from_board, game_to_state, map_to_schema

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 3
ticks = int(sys.argv[2]) if len(sys.argv) > 2 else 40
dets = int(sys.argv[3]) if len(sys.argv) > 3 else 8
iters = int(sys.argv[4]) if len(sys.argv) > 4 else 150

random.seed(seed)
board = map_to_schema(CatanMap.from_template(BASE_MAP_TEMPLATE))
game = game_from_board(board, [RandomPlayer(Color.RED), RandomPlayer(Color.BLUE)], seed=seed)
for _ in range(ticks):
    if game.winning_color() is not None:
        break
    game.play_tick()

gs = game_to_state(game)
cur = next(p for p in gs.players if p.color == gs.current_player)
cur.hand.wood, cur.hand.brick, cur.hand.sheep, cur.hand.wheat, cur.hand.ore = 3, 2, 2, 2, 3
gs.dice = (3, 4)  # a post-roll decision with a buildable hand
vps = {p.color: len(p.settlements) + 2 * len(p.cities) for p in gs.players}

print(f"seed={seed} ticks={ticks}  determinizations={dets} x iterations={iters} (UCT)")
print(f"current player: {gs.current_player}   building VP {vps}")
t = time.time()
recs = recommend_actions_pimc(gs, n_determinizations=dets, iterations=iters, rollout_depth=12)
print(f"search took {time.time() - t:.1f}s\n")
print(f"{'action':<22}{'value':<20}{'win%':>5}  visits  95% CI")
for r in recs:
    ci = f"[{r.ci_low * 100:.0f}-{r.ci_high * 100:.0f}]"
    print(f"{r.action_type:<22}{str(r.value):<20}{r.win_prob * 100:5.0f}  {r.rollouts:>6}  {ci}")
