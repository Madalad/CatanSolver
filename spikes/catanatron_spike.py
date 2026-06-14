"""Throwaway Phase-0 spike: empirically validate Catanatron for 1v1 Catan.

Confirms: 2-player support, vps_to_win=15 + discard_limit=9 config, board size,
snake-draft order, copy() independence, and the state/action API surface.
"""
import catanatron
from catanatron import Game, Color, RandomPlayer

print("VERSION:", getattr(catanatron, "__version__", "?"))
print("FILE   :", catanatron.__file__)

# --- Board size ---------------------------------------------------------
g = Game([RandomPlayer(Color.RED), RandomPlayer(Color.BLUE)],
         vps_to_win=15, discard_limit=9, seed=42)
land = g.state.board.map.land_tiles
nodes, edges = set(), set()
for coord, tile in land.items():
    for _, nid in tile.nodes.items():
        nodes.add(nid)
    try:
        for _, e in tile.edges.items():
            edges.add(tuple(sorted(e)))
    except Exception as ex:
        print("  (edge introspection failed:", ex, ")")
print("BOARD: land_tiles=%d nodes=%d edges=%d" % (len(land), len(nodes), len(edges)))
print("CONFIG: vps_to_win=%s discard_limit=%s" % (g.vps_to_win, g.state.discard_limit))

# --- Snake-draft order --------------------------------------------------
g2 = Game([RandomPlayer(Color.RED), RandomPlayer(Color.BLUE)],
          vps_to_win=15, discard_limit=9, seed=7)
print("START prompt:", g2.state.current_prompt,
      "| #playable:", len(g2.state.playable_actions))
print("START actions sample:", g2.state.playable_actions[:3])
seq = []
for _ in range(12):
    st = g2.state
    if st.current_prompt.value not in ("BUILD_INITIAL_SETTLEMENT", "BUILD_INITIAL_ROAD"):
        break
    color = st.colors[st.current_player_index]
    action = st.current_player().decide(g2, st.playable_actions)
    seq.append("%s:%s" % (color.value, st.current_prompt.value.replace("BUILD_INITIAL_", "")))
    g2.execute(action)
print("DRAFT ORDER:", " -> ".join(seq))

# --- copy() independence ------------------------------------------------
g3 = Game([RandomPlayer(Color.RED), RandomPlayer(Color.BLUE)], seed=1)
snapshot = g3.copy()
before = len(snapshot.state.playable_actions)
for _ in range(5):
    g3.play_tick()
print("COPY INDEPENDENT:", len(snapshot.state.playable_actions) == before,
      "(snapshot unchanged while original advanced)")

# --- Full game to a real winner (greedy VP bots) ------------------------
try:
    from catanatron.players.search import VictoryPointPlayer
    bots = [VictoryPointPlayer(Color.RED), VictoryPointPlayer(Color.BLUE)]
except Exception as ex:
    print("  (VictoryPointPlayer unavailable: %s; using RandomPlayer)" % ex)
    bots = [RandomPlayer(Color.RED), RandomPlayer(Color.BLUE)]
g4 = Game(bots, vps_to_win=15, discard_limit=9, seed=123)
winner = g4.play()
from catanatron.state_functions import get_actual_victory_points
print("FULL GAME: winner=%s num_turns=%s" % (winner, g4.state.num_turns))
print("FINAL VPs:", {c.value: get_actual_victory_points(g4.state, c) for c in g4.state.colors})

# --- player_state shape -------------------------------------------------
p0keys = [k for k in g4.state.player_state if k.startswith("P0_")]
print("PLAYER_STATE P0 keys (%d):" % len(p0keys), p0keys)
