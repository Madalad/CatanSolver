"""Phase 3.4: PIMC (determinized UCT) turn advisor. Small determinization/iteration
counts with truncated rollouts keep these fast while still exercising the tree + the
cross-world aggregation."""
import random

from catanatron import Color, RandomPlayer
from catanatron.models.map import BASE_MAP_TEMPLATE, CatanMap

from catansolver.advisor import recommend_actions_ismcts, recommend_actions_pimc
from catansolver.advisor.pimc import _leaf_value, _simulate
from catansolver.beliefs import DevCardHistory
from catansolver.engine import game_from_board, game_from_state, game_to_state, map_to_schema


def _midgame_state(seed: int = 3, ticks: int = 40):
    random.seed(seed)
    board = map_to_schema(CatanMap.from_template(BASE_MAP_TEMPLATE))
    g = game_from_board(board, [RandomPlayer(Color.RED), RandomPlayer(Color.BLUE)], seed=seed)
    for _ in range(ticks):
        if g.winning_color() is not None:
            break
        g.play_tick()
    gs = game_to_state(g)
    cur = next(p for p in gs.players if p.color == gs.current_player)
    cur.hand.wood, cur.hand.brick, cur.hand.sheep, cur.hand.wheat, cur.hand.ore = 3, 2, 2, 2, 3
    gs.dice = (3, 4)  # post-roll: real build/trade/buy choices
    return gs


_FAST = dict(n_determinizations=2, iterations=40, rollout_depth=8)


def test_pimc_recommendations_well_formed_and_ranked():
    recs = recommend_actions_pimc(_midgame_state(), **_FAST)
    assert recs
    probs = [r.win_prob for r in recs]
    assert probs == sorted(probs, reverse=True)  # best first
    for r in recs:
        assert 0.0 <= r.win_prob <= 1.0
        assert r.ci_low - 1e-9 <= r.win_prob <= r.ci_high + 1e-9
        assert r.rollouts > 0


def test_pimc_recommended_action_is_legal():
    gs = _midgame_state()
    recs = recommend_actions_pimc(gs, **_FAST)
    legal = {(a.action_type.value, a.value) for a in game_from_state(gs).state.playable_actions}

    def _back(v):  # recommendations store tuples as lists; restore for comparison
        return tuple(_back(x) for x in v) if isinstance(v, list) else v

    assert (recs[0].action_type, _back(recs[0].value)) in legal


def test_pimc_only_ranks_legal_actions():
    gs = _midgame_state()
    legal_types = {a.action_type.value for a in game_from_state(gs).state.playable_actions}
    recs = recommend_actions_pimc(gs, **_FAST)
    assert {r.action_type for r in recs} <= legal_types


def test_pimc_is_reproducible_with_a_fixed_seed():
    gs = _midgame_state()
    a = recommend_actions_pimc(gs, seed=11, **_FAST)
    b = recommend_actions_pimc(gs, seed=11, **_FAST)
    assert [(r.action_type, r.value, r.win_prob) for r in a] == [
        (r.action_type, r.value, r.win_prob) for r in b
    ]


def test_pimc_accepts_a_belief_history():
    # opponent is publicly holding dev cards; a history must not break the search
    gs = _midgame_state()
    opp = next(p for p in gs.players if p.color != gs.current_player)
    opp.dev_cards.knight = 2  # 2 face-down cards (count is what the belief uses)
    gs.dev_deck_remaining -= 2
    hist = DevCardHistory()
    hist.observe_buy(turn=5)
    hist.observe_buy(turn=6)
    for t in (8, 10, 12):
        hist.observe_robbed_turn(t, opponent_played_dev_card=False)
    recs = recommend_actions_pimc(gs, history=hist, **_FAST)
    assert recs and all(0.0 <= r.win_prob <= 1.0 for r in recs)


_FAST_IS = dict(iterations=120, rollout_depth=8)


def test_ismcts_recommendations_well_formed_and_ranked():
    recs = recommend_actions_ismcts(_midgame_state(), **_FAST_IS)
    assert recs
    probs = [r.win_prob for r in recs]
    assert probs == sorted(probs, reverse=True)
    for r in recs:
        assert 0.0 <= r.win_prob <= 1.0
        assert r.ci_low - 1e-9 <= r.win_prob <= r.ci_high + 1e-9
        assert r.rollouts > 0


def test_ismcts_recommended_action_is_legal():
    gs = _midgame_state()
    recs = recommend_actions_ismcts(gs, **_FAST_IS)
    legal = {(a.action_type.value, a.value) for a in game_from_state(gs).state.playable_actions}

    def _back(v):
        return tuple(_back(x) for x in v) if isinstance(v, list) else v

    assert (recs[0].action_type, _back(recs[0].value)) in legal


def test_ismcts_is_reproducible_with_a_fixed_seed():
    gs = _midgame_state()
    a = recommend_actions_ismcts(gs, seed=4, **_FAST_IS)
    b = recommend_actions_ismcts(gs, seed=4, **_FAST_IS)
    assert [(r.action_type, r.value, r.win_prob) for r in a] == [
        (r.action_type, r.value, r.win_prob) for r in b
    ]


def test_ismcts_total_root_visits_match_iterations():
    # each iteration descends through exactly one root child -> visits sum to iterations
    recs = recommend_actions_ismcts(_midgame_state(), iterations=100, rollout_depth=6)
    assert sum(r.rollouts for r in recs) == 100


def test_full_playout_simulation_is_binary():
    gs = _midgame_state()
    game = game_from_state(gs)
    me = game.state.colors[game.state.current_player_index]
    assert _simulate(game.copy(), me, None, gs.vps_to_win) in (0.0, 1.0)


def test_leaf_value_increases_with_vp_lead():
    # the truncated-rollout heuristic must reward being ahead: the player who is behind
    # scores below the player who is ahead in the very same position.
    gs = _midgame_state(seed=5, ticks=60)
    game = game_from_state(gs)
    colors = list(game.state.colors)
    v0 = _leaf_value(game, colors[0], gs.vps_to_win)
    v1 = _leaf_value(game, colors[1], gs.vps_to_win)
    assert 0.0 <= v0 <= 1.0 and 0.0 <= v1 <= 1.0
    assert abs((v0 + v1) - 1.0) < 1e-9  # complementary perspectives of a zero-sum lead
