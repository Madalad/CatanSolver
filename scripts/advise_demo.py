"""Tiny CLI demo of the Tier-2 turn advisor: build a mid-game position, then print
the ranked action recommendations with Monte-Carlo win estimates.

Run (repo root, Anaconda PATH + PYTHONPATH set):
    .\\.venv\\Scripts\\python.exe scripts\\advise_demo.py [seed] [ticks] [rollouts]
"""
import random
import sys

from catanatron import Color, RandomPlayer
from catanatron.models.map import BASE_MAP_TEMPLATE, CatanMap

from catansolver.advisor import recommend_actions
from catansolver.engine import game_from_board, game_to_state, map_to_schema

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 7
ticks = int(sys.argv[2]) if len(sys.argv) > 2 else 80
rollouts = int(sys.argv[3]) if len(sys.argv) > 3 else 60

random.seed(seed)
board = map_to_schema(CatanMap.from_template(BASE_MAP_TEMPLATE))
game = game_from_board(board, [RandomPlayer(Color.RED), RandomPlayer(Color.BLUE)], seed=seed)
for _ in range(ticks):
    if game.winning_color() is not None:
        break
    game.play_tick()

gs = game_to_state(game)
# show it as a post-roll decision with a buildable hand so there are real choices
cur = next(p for p in gs.players if p.color == gs.current_player)
cur.hand.wood, cur.hand.brick, cur.hand.sheep, cur.hand.wheat, cur.hand.ore = 4, 2, 2, 2, 3
gs.dice = (3, 4)
vps = {p.color: len(p.settlements) + 2 * len(p.cities) for p in gs.players}
print(f"seed={seed} ticks={ticks} rollouts={rollouts}")
print(f"current player: {gs.current_player}  | settlements+cities VP {vps}")
print(f"  hand: {cur.hand.model_dump()}")
print(f"\n{'action':<22}{'value':<20}{'win%':>6}  95% CI")
for r in recommend_actions(gs, n_rollouts=rollouts):
    ci = f"[{r.ci_low*100:.0f}-{r.ci_high*100:.0f}]"
    print(f"{r.action_type:<22}{str(r.value):<20}{r.win_prob*100:6.0f}  {ci}")
