import random
from collections import defaultdict

from catanatron import Color
from catanatron.models.board import STATIC_GRAPH
from catanatron.models.enums import ActionPrompt
from catanatron.models.map import BASE_MAP_TEMPLATE, CatanMap
from catanatron.players.search import VictoryPointPlayer

from catansolver.engine import game_from_board
from catansolver.engine.adapter import map_to_schema
from catansolver.io.schema import DraftSeat, OpeningPlacementRequest
from catansolver.placement import (
    best_initial_road,
    default_policy,
    drive_to_user_decision,
    node_score,
    recommend_opening,
    wilson_interval,
)


def _map(seed: int = 7) -> CatanMap:
    random.seed(seed)
    return CatanMap.from_template(BASE_MAP_TEMPLATE)


def _board(seed: int = 7):
    return map_to_schema(_map(seed))


def _draft_request(seat: DraftSeat, seed: int) -> OpeningPlacementRequest:
    """Generate a valid, aligned request by playing a partial draft in Catanatron."""
    board = _board(seed)
    game = game_from_board(
        board, [VictoryPointPlayer(Color.RED), VictoryPointPlayer(Color.BLUE)], seed=seed
    )
    first = game.state.current_color()
    second = next(c for c in game.state.colors if c != first)
    plies = {DraftSeat.SECOND: 2, DraftSeat.FIRST_FINAL: 6}[seat]
    for _ in range(plies):
        game.play_tick()

    cat_to_label = {first: "P1", second: "P2"}
    user = "P2" if seat == DraftSeat.SECOND else "P1"

    settlements_by_color = defaultdict(list)
    for node, (color, _bt) in game.state.board.buildings.items():
        settlements_by_color[color].append(node)
    roads_by_color = defaultdict(set)
    for edge, color in game.state.board.roads.items():
        roads_by_color[color].add(tuple(sorted(edge)))

    settlements, roads = {}, {}
    for color, nodes in settlements_by_color.items():
        paired_s, paired_r = [], []
        for s in nodes:
            incident = [r for r in roads_by_color[color] if s in r]
            paired_s.append(s)
            paired_r.append(incident[0])
        settlements[cat_to_label[color]] = paired_s
        roads[cat_to_label[color]] = paired_r

    return OpeningPlacementRequest(
        board=board, seat=seat, user_color=user, settlements=settlements, roads=roads
    )


# --- heuristic / stats ------------------------------------------------------
def test_wilson_interval_basic():
    lo, hi = wilson_interval(5, 10)
    assert 0.0 <= lo < 0.5 < hi <= 1.0
    assert wilson_interval(0, 10)[0] == 0.0
    assert wilson_interval(10, 10)[1] == 1.0
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_node_score_positive_and_discriminating():
    m = _map()
    scores = {n: node_score(m, n) for n in m.land_nodes}
    assert all(s >= 0 for s in scores.values())
    assert max(scores.values()) > min(scores.values()) + 0.05


def test_best_initial_road_is_incident_edge():
    m = _map()
    node = next(iter(m.land_nodes))
    road = best_initial_road(m, node)
    assert node in road and tuple(sorted(road)) == road
    other = road[0] if road[1] == node else road[1]
    assert other in [v for (_, v) in STATIC_GRAPH.edges(node)]


# --- draft driving ----------------------------------------------------------
def test_drive_second_seat_stops_at_user():
    req = _draft_request(DraftSeat.SECOND, seed=3)
    game, user = drive_to_user_decision(req, default_policy, seed=3)
    assert game.state.current_color() == user
    assert game.state.current_prompt == ActionPrompt.BUILD_INITIAL_SETTLEMENT
    assert len(game.state.board.buildings) == 1  # only the opponent's settlement


def test_drive_first_final_stops_at_user():
    req = _draft_request(DraftSeat.FIRST_FINAL, seed=4)
    game, user = drive_to_user_decision(req, default_policy, seed=4)
    assert game.state.current_color() == user
    assert game.state.current_prompt == ActionPrompt.BUILD_INITIAL_SETTLEMENT
    assert len(game.state.board.buildings) == 3


# --- recommendations --------------------------------------------------------
def test_recommend_first_seat():
    req = OpeningPlacementRequest(board=_board(), seat=DraftSeat.FIRST, user_color="P1")
    recs = recommend_opening(req, top_k=3, n_rollouts=6)
    assert len(recs) == 3
    probs = [r.win_prob for r in recs]
    assert probs == sorted(probs, reverse=True)
    for r in recs:
        assert len(r.placements) == 1
        p = r.placements[0]
        assert 0 <= p.settlement <= 53 and p.settlement in p.road
        assert 0.0 <= r.win_prob <= 1.0
        assert r.ci_low - 1e-6 <= r.win_prob <= r.ci_high + 1e-6


def test_recommend_first_seat_heuristic_only():
    req = OpeningPlacementRequest(board=_board(), seat=DraftSeat.FIRST, user_color="P1")
    recs = recommend_opening(req, top_k=5, n_rollouts=0)
    assert len(recs) == 5
    assert all(r.win_prob is None for r in recs)
    scores = [r.heuristic_score for r in recs]
    assert scores == sorted(scores, reverse=True)


def test_recommend_second_seat_returns_pairs():
    req = _draft_request(DraftSeat.SECOND, seed=3)
    recs = recommend_opening(req, top_k=3, n_rollouts=4, pair_top_first=6, pair_top_second=3)
    assert len(recs) == 3
    seen_pairs = set()
    for r in recs:
        assert len(r.placements) == 2
        s1, s2 = r.placements[0].settlement, r.placements[1].settlement
        assert s1 != s2
        assert s2 not in [v for (_, v) in STATIC_GRAPH.edges(s1)]  # distance rule
        assert 0.0 <= r.win_prob <= 1.0
        seen_pairs.add(frozenset((s1, s2)))
    assert len(seen_pairs) == 3  # no duplicate unordered pairs


def test_recommend_first_final_seat():
    req = _draft_request(DraftSeat.FIRST_FINAL, seed=4)
    recs = recommend_opening(req, top_k=3, n_rollouts=4)
    assert len(recs) == 3
    for r in recs:
        assert len(r.placements) == 1
        assert 0.0 <= r.win_prob <= 1.0
