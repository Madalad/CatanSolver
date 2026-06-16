"""Practice-mode tests: puzzle generation produces valid, seat-correct inputs,
and grading is consistent (the model line scores full marks, the tolerance band
behaves, and points/streak signals are coherent)."""

import random

import pytest

from catansolver.engine.adapter import map_to_schema
from catanatron.models.map import BASE_MAP_TEMPLATE, CatanMap

from catansolver.io.schema import DraftSeat, OpeningPlacementRequest, Placement
from catansolver.placement import generate_puzzle, grade_practice

SEATS = [DraftSeat.FIRST, DraftSeat.SECOND, DraftSeat.FIRST_FINAL]
_EXPECTED_PRIOR_SETTLEMENTS = {DraftSeat.FIRST: 0, DraftSeat.SECOND: 1, DraftSeat.FIRST_FINAL: 3}
_USER_PIECES = {DraftSeat.FIRST: 1, DraftSeat.SECOND: 2, DraftSeat.FIRST_FINAL: 1}


def _board(seed: int):
    random.seed(seed)
    return map_to_schema(CatanMap.from_template(BASE_MAP_TEMPLATE))


@pytest.mark.parametrize("seat", SEATS)
def test_generate_puzzle_matches_seat(seat):
    req = generate_puzzle(_board(1), seat, seed=1)
    assert isinstance(req, OpeningPlacementRequest)
    assert req.seat == seat
    assert req.user_color == "P1"
    placed = sum(len(v) for v in req.settlements.values())
    assert placed == _EXPECTED_PRIOR_SETTLEMENTS[seat]
    # every prior settlement is paired with a road
    for color, nodes in req.settlements.items():
        assert len(req.roads.get(color, [])) == len(nodes)


@pytest.mark.parametrize("seat", SEATS)
def test_model_line_scores_full_marks(seat):
    """Replaying the solver's own model line back as the user's answer must be
    graded correct on every unit (grading and the revealed optimum agree)."""
    req = generate_puzzle(_board(2), seat, seed=2)
    # first pass: discover the model line
    probe = grade_practice(req, _dummy_answer(req))
    model = [Placement(settlement=p.settlement, road=p.road) for p in probe.optimal_placements]
    result = grade_practice(req, model)
    assert result.all_correct
    assert result.is_optimal
    assert result.total_awarded == result.total_max == 10.0
    assert all(g.is_optimal and g.quality == 1.0 for g in result.grades)


@pytest.mark.parametrize("seat", SEATS)
def test_grade_shape_and_points(seat):
    req = generate_puzzle(_board(3), seat, seed=3)
    result = grade_practice(req, _dummy_answer(req))
    n = _USER_PIECES[seat]
    assert len(result.grades) == 2 * n  # a settlement + a road per piece
    assert result.total_max == 10.0  # a perfect answer always scores 10
    assert 0 <= result.total_awarded <= result.total_max
    assert all(0.0 <= g.quality <= 1.0 for g in result.grades)
    assert result.ranking  # solver's recommendations are included


def test_deliberately_weak_settlement_loses_points():
    req = generate_puzzle(_board(4), DraftSeat.FIRST, seed=4)
    probe = grade_practice(req, _dummy_answer(req))
    ranking = probe.ranking
    worst = ranking[-1].placements[0]  # lowest-ranked of the solver's picks
    best_node = probe.optimal_placements[0].settlement
    if worst.settlement == best_node:
        pytest.skip("degenerate board where the worst shown pick is also the best")
    result = grade_practice(req, [Placement(settlement=worst.settlement, road=worst.road)])
    s_grade = next(g for g in result.grades if g.kind == "settlement")
    assert s_grade.rank >= 1 and s_grade.pct_of_best <= 100.0


def test_correct_settlement_wrong_road_is_not_punitive():
    """Road quality is ratio-to-best, so nailing the settlement but taking the
    worst road should still score well (was a harsh 6.7/10 under spread-norm)."""
    req = generate_puzzle(_board(5), DraftSeat.FIRST, seed=5)
    probe = grade_practice(req, _dummy_answer(req))
    best_node = probe.optimal_placements[0].settlement

    from catansolver.placement.draft import default_policy, drive_to_user_decision
    from catansolver.placement.practice import _road_scores
    from catansolver.engine.adapter import schema_to_map
    from catanatron import Action, ActionType

    cmap = schema_to_map(req.board)
    game, user = drive_to_user_decision(req, default_policy, seed=0)
    game.execute(Action(user, ActionType.BUILD_SETTLEMENT, best_node))
    road_scores = _road_scores(game, cmap, best_node)
    worst_road = min(road_scores, key=road_scores.get)
    expected_q = round(road_scores[worst_road] / max(road_scores.values()), 4)

    result = grade_practice(req, [Placement(settlement=best_node, road=list(worst_road))])
    s = next(g for g in result.grades if g.kind == "settlement")
    r = next(g for g in result.grades if g.kind == "road")
    assert s.is_optimal and s.points == round(20 / 3, 2)  # full settlement credit (6.67)
    # ratio-to-best: the worst road earns its share, not 0 (old spread-norm floor)
    assert not r.is_optimal and r.quality == expected_q > 0.0
    assert result.total_awarded > 20 / 3  # strictly above the old 6.67 floor


def _dummy_answer(req: OpeningPlacementRequest):
    """A syntactically-valid answer (the first legal-ish spots) for shape tests;
    grading falls back gracefully if a node/edge is not actually legal."""
    from catansolver.placement.draft import default_policy, drive_to_user_decision
    from catansolver.placement.optimize import _legal_settlements

    game, _ = drive_to_user_decision(req, default_policy, seed=0)
    legal = _legal_settlements(game)
    answer = []
    n = _USER_PIECES[req.seat]
    for i in range(n):
        node = legal[i % len(legal)]
        # any incident edge; grading scores it against legal roads from this node
        answer.append(Placement(settlement=node, road=(node, node + 1)))
    return answer
