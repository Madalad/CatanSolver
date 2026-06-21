"""Drive Catanatron's initial-build phase to the user's decision point.

Given an ``OpeningPlacementRequest``, replays the placements already on the board
(the opponent's, and for ``FIRST_FINAL`` the user's own opener) in snake order,
then stops when it is the user's turn to make the placement(s) we will recommend.

Catanatron decides seating itself, so we don't try to control it: the *first*
player (whoever Catanatron seats first) places picks #1 and #4, the *second*
places #2 and #3. We map the request's logical colours onto first/second by seat,
and use absolute node ids, so the result is independent of the RED/BLUE seating.

Note: ``request.settlements[label][i]`` is assumed paired with
``request.roads[label][i]`` (settlement i was placed with road i). ``_pick_road``
falls back to any legal road if a given road doesn't match, so a misaligned
request degrades gracefully rather than crashing.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable, Dict, List, Optional, Tuple

from catanatron import Action, ActionType, Color
from catanatron.models.enums import ActionPrompt
from catanatron.players.search import VictoryPointPlayer
from catanatron.players.weighted_random import WeightedRandomPlayer

from catansolver.engine import game_from_board
from catansolver.engine.config import COLONIST_1V1, RulesConfig
from catansolver.io.schema import DraftSeat, OpeningPlacementRequest

Edge = Tuple[int, int]
PolicyFactory = Callable[[Color], object]

_MAX_DRAFT_PLIES = 16  # safety: a 2-player draft is 8 plies


def default_policy(color: Color):
    """Greedy victory-point policy: used to generate plausible opponent priors for
    practice puzzles (a competent opening), where speed is not critical."""
    return VictoryPointPlayer(color)


def rollout_policy(color: Color):
    """Fast, even-strength baseline for Monte-Carlo rollouts: ~7x quicker than the
    search player (so the win-% mode is usable) and the opponent the win-prob model
    is calibrated against. Both players use it, so win-rates are "vs an even
    baseline" — see docs/heuristic-accuracy.md."""
    return WeightedRandomPlayer(color)


def _pick_road(game, desired: Optional[Edge]) -> Action:
    """Return a legal initial-road action, preferring ``desired`` (matched by node
    set, orientation-independent) and falling back to any legal road."""
    legal = [a for a in game.state.playable_actions if a.action_type == ActionType.BUILD_ROAD]
    if desired is not None:
        target = set(desired)
        for action in legal:
            if set(action.value) == target:
                return action
    if legal:
        return legal[0]
    raise ValueError("no legal initial road available")


def drive_to_user_decision(
    request: OpeningPlacementRequest,
    policy: PolicyFactory,
    seed: Optional[int] = None,
    rules: RulesConfig = COLONIST_1V1,
) -> Tuple[object, Color]:
    """Build a game on the request's board and advance the draft until it is the
    user's turn to place their next (to-be-recommended) settlement.

    Returns the game (positioned at a ``BUILD_INITIAL_SETTLEMENT`` prompt for the
    user) and the user's Catanatron colour.
    """
    game = game_from_board(
        request.board, [policy(Color.RED), policy(Color.BLUE)], rules=rules, seed=seed
    )
    first = game.state.current_color()
    second = next(c for c in game.state.colors if c != first)

    user_label = request.user_color
    opponent_label = next((c for c in request.settlements if c != user_label), None)

    if request.seat == DraftSeat.SECOND:
        user_cat, opponent_cat = second, first  # user goes second
    else:  # FIRST, FIRST_FINAL -> user goes first
        user_cat, opponent_cat = first, second

    label_to_cat: Dict[str, Color] = {user_label: user_cat}
    if opponent_label is not None:
        label_to_cat[opponent_label] = opponent_cat

    given_settlements: Dict[Color, List[int]] = defaultdict(list)
    given_roads: Dict[Color, List[Edge]] = defaultdict(list)
    for label, nodes in request.settlements.items():
        given_settlements[label_to_cat[label]] = list(nodes)
    for label, edges in request.roads.items():
        given_roads[label_to_cat[label]] = [tuple(sorted(e)) for e in edges]

    ptr: Dict[Color, int] = defaultdict(int)
    for _ in range(_MAX_DRAFT_PLIES):
        color = game.state.current_color()
        prompt = game.state.current_prompt

        if prompt == ActionPrompt.BUILD_INITIAL_SETTLEMENT:
            placed = ptr[color]
            if placed >= len(given_settlements[color]):
                if color == user_cat:
                    return game, user_cat  # the user's decision point
                raise RuntimeError("ran out of given opponent placements before user's turn")
            game.execute(Action(color, ActionType.BUILD_SETTLEMENT, given_settlements[color][placed]))
        elif prompt == ActionPrompt.BUILD_INITIAL_ROAD:
            roads = given_roads[color]
            desired = roads[ptr[color]] if ptr[color] < len(roads) else None
            game.execute(_pick_road(game, desired))
            ptr[color] += 1
        else:
            raise RuntimeError(f"unexpected prompt {prompt} during initial draft")

    raise RuntimeError("draft driving did not reach the user's decision point")
