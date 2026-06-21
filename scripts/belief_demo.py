"""Tiny CLI demo of the Phase 3.3 belief layer.

We know the opponent holds N face-down dev cards (public: cards bought minus cards
played) but not *which* — and they might be sitting on hidden Victory-Point cards
that put them closer to 15 than the board shows. The belief layer turns the public
counts into a distribution and samples concrete worlds (determinizations) from it;
PIMC (Phase 3.4) averages a search over those worlds.

This demo builds an illustrative mid-game position and prints several determinizations
of the opponent's hidden hand, showing that every *public* fact stays fixed while the
hidden composition varies.

Run (repo root, Anaconda PATH + PYTHONPATH set):
    .\\.venv\\Scripts\\python.exe scripts\\belief_demo.py [n_samples]
"""
import random
import sys
from collections import Counter

from catanatron.models.map import BASE_MAP_TEMPLATE, CatanMap

from catansolver.beliefs import DevCardHistory, dev_card_belief, sample_determinization
from catansolver.engine import map_to_schema
from catansolver.io.schema import DevCards, GameState, Hand, PlayerState


def vp_knight_rates(gs, history, n=2000):
    """Fraction of sampled worlds where the opponent's hand contains a VP / a knight."""
    vp = kn = 0
    for s in range(n):
        det = sample_determinization(gs, random.Random(s), history=history)
        opp = next(p for p in det.state.players if p.color != gs.current_player)
        vp += opp.dev_cards.victory_point > 0
        kn += opp.dev_cards.knight > 0
    return vp / n, kn / n

n_samples = int(sys.argv[1]) if len(sys.argv) > 1 else 8

board = map_to_schema(CatanMap.from_template(BASE_MAP_TEMPLATE))
# Public picture: it's our (RED) turn. We've played 2 knights; the opponent (BLUE)
# has played 1 knight and is holding 3 face-down dev cards. 6 cards have left the
# deck (our 2 + their 1 played, their 3 in hand), so 19 remain.
gs = GameState(
    board=board,
    players=[
        PlayerState(color="RED", dev_cards=DevCards(knight=1), played_knights=2,
                    hand=Hand(wheat=2, ore=3, sheep=1)),
        PlayerState(color="BLUE", dev_cards=DevCards(knight=3), played_knights=1,
                    hand=Hand(wood=1, brick=1, wheat=2)),
    ],
    dev_deck_remaining=19,
    current_player="RED",
)

belief = dev_card_belief(gs)
print(f"observer={belief.observer}  opponent={belief.opponent}")
print(f"opponent is holding {belief.opp_hand_size} face-down dev cards (composition hidden)")
print(f"deck remaining: {belief.deck_remaining}")
print(f"unseen pool (opp hand + deck) = {dict(belief.unseen)}  (total {belief.hidden_total})")
print(f"\n{n_samples} sampled worlds - opponent's hand varies, every public count holds:")
for i in range(n_samples):
    det = sample_determinization(gs, random.Random(i))
    opp = next(p for p in det.state.players if p.color == belief.opponent)
    hand = {k: v for k, v in opp.dev_cards.model_dump().items() if v}
    vp = opp.dev_cards.victory_point
    flag = f"  <-- {vp} hidden VP card(s)!" if vp else ""
    print(f"  [{i}] opp hand={str(hand):<45} deck={dict(Counter(det.dev_deck))}{flag}")

# --- behavioural sharpening: feed the public turn log to a DevCardHistory --------
print("\nP(opp holds VP) / P(opp holds knight) as the turn log accumulates:")
single = GameState(
    board=board,
    players=[
        PlayerState(color="RED", played_knights=2, hand=Hand(wheat=2, ore=3)),
        PlayerState(color="BLUE", dev_cards=DevCards(knight=1), played_knights=1,
                    hand=Hand(wood=1, brick=1)),
    ],
    dev_deck_remaining=21,
    current_player="RED",
)
uniform = vp_knight_rates(single, None)
print(f"  uniform (no history)               : VP {uniform[0]:.0%}   knight {uniform[1]:.0%}")

held = DevCardHistory()
held.observe_buy(turn=4)
held.current_turn = 18  # the one card has been sat on for ~14 turns
r = vp_knight_rates(single, held)
print(f"  held ~14 turns (3b)                : VP {r[0]:.0%}   knight {r[1]:.0%}")

robbed = DevCardHistory()
robbed.observe_buy(turn=4)
for t in (6, 8, 10):  # three turns: robber on their hex, didn't knight it off
    robbed.observe_robbed_turn(t, opponent_played_dev_card=False)
r = vp_knight_rates(single, robbed)
print(f"  + robbed & passed x3 (3a)          : VP {r[0]:.0%}   knight {r[1]:.0%}")
