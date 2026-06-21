"""Baseline turn advisor (Phase 3.2): ranks the current player's legal actions by
flat Monte-Carlo win rate. Small rollout counts keep these fast."""
import random

from catanatron import Color, RandomPlayer
from catanatron.models.map import BASE_MAP_TEMPLATE, CatanMap

from catansolver.advisor import recommend_actions
from catansolver.engine import game_from_board, game_from_state, game_to_state, map_to_schema


def _midgame_state(seed: int = 7, ticks: int = 80):
    random.seed(seed)
    board = map_to_schema(CatanMap.from_template(BASE_MAP_TEMPLATE))
    g = game_from_board(board, [RandomPlayer(Color.RED), RandomPlayer(Color.BLUE)], seed=seed)
    for _ in range(ticks):
        if g.winning_color() is not None:
            break
        g.play_tick()
    return game_to_state(g)


def test_recommendations_are_well_formed_and_ranked():
    recs = recommend_actions(_midgame_state(), n_rollouts=8)
    assert recs
    probs = [r.win_prob for r in recs]
    assert probs == sorted(probs, reverse=True)  # best first
    for r in recs:
        assert 0.0 <= r.win_prob <= 1.0
        assert r.ci_low - 1e-9 <= r.win_prob <= r.ci_high + 1e-9
        assert r.rollouts == 8


def test_recommended_action_is_actually_legal():
    gs = _midgame_state()
    recs = recommend_actions(gs, n_rollouts=4)
    legal = {a.action_type.value for a in game_from_state(gs).state.playable_actions}
    assert recs[0].action_type in legal


def test_postroll_position_offers_multiple_choices():
    gs = _midgame_state()
    cur = next(p for p in gs.players if p.color == gs.current_player)
    cur.hand.wood += 1  # enough for a road -> BUILD_ROAD option(s) appear
    cur.hand.brick += 1
    gs.dice = (3, 4)  # mark the turn as already rolled
    recs = recommend_actions(gs, n_rollouts=4)
    kinds = {r.action_type for r in recs}
    assert len(recs) >= 2
    assert "END_TURN" in kinds  # ending the turn is always an option once rolled
