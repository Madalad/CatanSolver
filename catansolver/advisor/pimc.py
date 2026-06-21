"""PIMC turn advisor (Phase 3.4): determinized UCT search over hidden information.

This upgrades the Phase-3.2 flat Monte-Carlo baseline (:func:`recommend_actions`) two
ways:

1. **Hidden information (PIMC).** Instead of trusting the opponent's recorded hand, we
   sample many *determinizations* of the hidden dev cards from the belief
   (:mod:`catansolver.beliefs`) and search each one, aggregating the per-action
   statistics. This is **Perfect-Information Monte Carlo** — the standard first attack
   on imperfect-information games (plan.md §6.4).
2. **Lookahead (UCT).** Within each determinized (now fully-observable) world we run a
   **UCT** tree search rather than evaluating a single ply, so the value of an action
   accounts for the opponent's replies and our follow-ups, not just the immediate
   rollout.

**Chance handling.** Catanatron samples dice (and dev-card draws / robber steals) inside
``game.execute``. We use *open-loop* UCT: a tree node is keyed by the action path and the
concrete state is realised fresh — by replaying the actions on a copy of the determinized
game — on every iteration, so stochastic transitions are sampled rather than enumerated.
This is unbiased (just higher variance than explicit expectiminimax chance nodes, a noted
future refinement). The common advisor query is a *post-roll* decision, so the root and
first plies are deterministic and chance only enters deeper, where the rollout absorbs it.

**Known limit (the motivation for the ISMCTS upgrade).** PIMC searches each determinized
world with full knowledge of the sampled hidden cards, so it can't represent "play to
gain information" and is prone to *strategy fusion*. ISMCTS (one tree over information
sets, re-determinized per iteration) fixes this and is the next step. The win-rates are
also still *vs the baseline rollout opponent* — a relative ranking signal (see
docs/heuristic-accuracy.md), pending the Phase-3.5 evaluation.
"""
from __future__ import annotations

import math
import random
from typing import Callable, Dict, List, Optional, Tuple

from catanatron import Color, Player
from catanatron.state_functions import get_actual_victory_points

from catansolver.beliefs import (
    DEV_TYPES,
    DevCardHistory,
    dev_card_belief,
    sample_determinization,
    sample_dev_cards,
)
from catansolver.engine import COLONIST_1V1, RulesConfig, game_from_state
from catansolver.io.schema import ActionRecommendation, DevCards, GameState
from catansolver.placement.draft import rollout_policy
from catansolver.placement.rollout import wilson_interval

PolicyFactory = Callable[[Color], Player]
_COLORS = (Color.RED, Color.BLUE)
_DEFAULT_UCB_C = math.sqrt(2)
#: logistic slope for the truncated-rollout VP-lead leaf value (≈1 VP lead -> .60)
_LEAF_VP_SCALE = 0.4


def _leaf_value(game, root_player: Color, vps_to_win: int) -> float:
    """A cheap [0,1] win-prob proxy for a non-terminal position cut short by a depth
    limit: a logistic on the actual-VP lead, steepened as the leader nears the goal."""
    me = get_actual_victory_points(game.state, root_player)
    opp = max(
        get_actual_victory_points(game.state, c) for c in game.state.colors if c != root_player
    )
    lead = me - opp
    # closer to the finish, each VP of lead is worth more
    urgency = 1.0 + max(me, opp) / vps_to_win
    return 1.0 / (1.0 + math.exp(-_LEAF_VP_SCALE * urgency * lead))


def _simulate(game, root_player: Color, rollout_depth: Optional[int], vps_to_win: int) -> float:
    """Score a leaf for ``root_player`` in [0,1]. ``rollout_depth=None`` plays to a
    terminal (true win/loss, unbiased); an int truncates the playout at that many ticks
    and falls back to the :func:`_leaf_value` heuristic — far cheaper, mildly biased."""
    if rollout_depth is None:
        winner = game.play() if game.winning_color() is None else game.winning_color()
        return 1.0 if winner == root_player else 0.0
    ticks = 0
    while game.winning_color() is None and ticks < rollout_depth:
        game.play_tick()
        ticks += 1
    if game.winning_color() is not None:
        return 1.0 if game.winning_color() == root_player else 0.0
    return _leaf_value(game, root_player, vps_to_win)


def _jsonable(value):
    """Normalise Catanatron action values (tuples) to lists so they serialise cleanly."""
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    return value


class _Node:
    """An open-loop UCT node. Stores only statistics + discovered children (keyed by
    action); the concrete game state is realised by replaying actions each iteration.

    ``wins_root`` counts wins for the *root* player (the one we advise), so a node's
    exploitation value is read from the perspective of whichever player chooses at it.
    """

    __slots__ = ("to_move", "parent", "children", "visits", "wins_root", "avail")

    def __init__(self, to_move: Optional[Color], parent: Optional["_Node"]):
        self.to_move = to_move
        self.parent = parent
        self.children: Dict[object, "_Node"] = {}
        self.visits = 0
        self.wins_root = 0.0
        self.avail = 0  # ISMCTS: times this child was *available* during selection


def _recs_from_children(rows) -> List[ActionRecommendation]:
    """Build sorted recommendations from ``(action_type, value, visits, wins)`` rows."""
    recs: List[ActionRecommendation] = []
    for action_type, value, visits, wins in rows:
        win_prob = wins / visits if visits else 0.0
        lo, hi = wilson_interval(int(round(wins)), visits)
        recs.append(
            ActionRecommendation(
                action_type=action_type,
                value=_jsonable(value),
                win_prob=round(win_prob, 4),
                ci_low=round(lo, 4),
                ci_high=round(hi, 4),
                rollouts=visits,
            )
        )
    recs.sort(key=lambda r: r.win_prob, reverse=True)
    return recs


def _ucb(node: _Node, child: _Node, root_player: Color, c: float) -> float:
    """UCB1 score of ``child`` from the perspective of ``node``'s mover (adversarial:
    the opponent maximises *their* win rate, i.e. minimises the root player's)."""
    exploit = child.wins_root / child.visits
    if node.to_move != root_player:
        exploit = 1.0 - exploit
    return exploit + c * math.sqrt(math.log(node.visits) / child.visits)


def _uct_search(root_game, root_player: Color, iterations: int, rng: random.Random,
                c: float, max_depth: int, rollout_depth: Optional[int],
                vps_to_win: int) -> _Node:
    """Run ``iterations`` of open-loop UCT from ``root_game`` (a fully-determinized,
    playable game) and return the root node with per-action statistics."""
    root = _Node(to_move=root_game.state.colors[root_game.state.current_player_index],
                 parent=None)

    for _ in range(iterations):
        game = root_game.copy()
        node = root
        depth = 0

        # --- selection + expansion (open-loop: actions realised on a live copy) ---
        while game.winning_color() is None and depth < max_depth:
            legal = list(game.state.playable_actions)
            if not legal:
                break
            untried = [a for a in legal if a not in node.children]
            if untried:  # expand one new child
                action = rng.choice(untried)
                game.execute(action)
                child = _Node(
                    to_move=game.state.colors[game.state.current_player_index], parent=node
                )
                node.children[action] = child
                node = child
                depth += 1
                break
            # fully expanded: descend the best UCB child among the currently-legal set
            action = max(legal, key=lambda a: _ucb(node, node.children[a], root_player, c))
            game.execute(action)
            node = node.children[action]
            depth += 1

        # --- simulation: roll out (full or depth-truncated) and score for root ---
        reward = _simulate(game, root_player, rollout_depth, vps_to_win)

        # --- backpropagation ---
        while node is not None:
            node.visits += 1
            node.wins_root += reward
            node = node.parent

    return root


def recommend_actions_pimc(
    gs: GameState,
    n_determinizations: int = 20,
    iterations: int = 200,
    history: Optional[DevCardHistory] = None,
    policy: PolicyFactory = rollout_policy,
    rules: RulesConfig = COLONIST_1V1,
    seed: int = 0,
    ucb_c: float = _DEFAULT_UCB_C,
    max_depth: int = 40,
    rollout_depth: Optional[int] = None,
) -> List[ActionRecommendation]:
    """Rank the current player's legal actions by PIMC win rate, best first.

    Samples ``n_determinizations`` worlds from the belief (optionally sharpened by a
    :class:`DevCardHistory`), runs ``iterations`` of UCT in each, and aggregates the
    root-action visit/win statistics across worlds into a per-action win-probability.

    ``rollout_depth=None`` evaluates leaves by a full playout (true win/loss); an int
    truncates each rollout to that many ticks and finishes with a VP-lead heuristic —
    much cheaper, so far more ``iterations`` fit in the same time, at the cost of a
    mildly biased value (UCT needs iterations ≫ the branching factor to build a real
    tree, which full playouts make expensive)."""
    random.seed(seed)  # the engine samples dice via global random; pin for reproducibility
    rng = random.Random(seed)
    observer = gs.current_player

    # action identity must be stable across worlds; the root player's legal actions do
    # not depend on the opponent's hidden cards, so they coincide across determinizations.
    agg: Dict[Tuple[str, object], List] = {}  # (type, value) -> [visits, wins, action_value]
    for d in range(n_determinizations):
        det = sample_determinization(gs, random.Random(seed * 100003 + d),
                                     observer=observer, history=history)
        game = game_from_state(det.state, players=[policy(c) for c in _COLORS],
                               dev_deck=det.dev_deck)
        me = game.state.colors[game.state.current_player_index]
        root = _uct_search(game, me, iterations, rng, ucb_c, max_depth,
                           rollout_depth, gs.vps_to_win)
        for action, child in root.children.items():
            key = (action.action_type.value, action.value)  # raw value is hashable
            entry = agg.setdefault(key, [0, 0.0])
            entry[0] += child.visits
            entry[1] += child.wins_root

    return _recs_from_children(
        (action_type, value, visits, wins)
        for (action_type, value), (visits, wins) in agg.items()
    )


# --------------------------------------------------------------------------- #
# ISMCTS — one tree over information sets, re-determinized every iteration
# --------------------------------------------------------------------------- #
def _ismcts_ucb(node: _Node, child: _Node, root_player: Color, c: float) -> float:
    """ISMCTS UCB: exploration uses the child's *availability* count (how often it was
    legal during selection), not the parent's visit count — correcting for the fact
    that, across re-determinizations, some moves are legal less often than others."""
    exploit = child.wins_root / child.visits
    if node.to_move != root_player:
        exploit = 1.0 - exploit
    return exploit + c * math.sqrt(math.log(child.avail) / child.visits)


def _ismcts_iteration(root, game, root_player, rng, c, max_depth, rollout_depth, vps):
    """One ISMCTS pass over the shared ``root`` tree, realised in this iteration's
    determinization ``game``: select (restricted to the moves legal in this world),
    expand, roll out, and back up along the visited path."""
    node, depth, path = root, 0, [root]
    while game.winning_color() is None and depth < max_depth:
        legal = list(game.state.playable_actions)
        if not legal:
            break
        untried = [a for a in legal if a not in node.children]
        if untried:  # expand one move legal in this world
            action = rng.choice(untried)
            game.execute(action)
            child = _Node(to_move=game.state.colors[game.state.current_player_index], parent=node)
            node.children[action] = child
            node, depth = child, depth + 1
            path.append(node)
            break
        for a in legal:  # every currently-legal child became available this visit
            node.children[a].avail += 1
        action = max(legal, key=lambda a: _ismcts_ucb(node, node.children[a], root_player, c))
        game.execute(action)
        node, depth = node.children[action], depth + 1
        path.append(node)

    reward = _simulate(game, root_player, rollout_depth, vps)
    for n in path:
        n.visits += 1
        n.wins_root += reward


def _inject_determinization(game, opp_color, hand, deck) -> None:
    """Set a sampled hidden opponent hand + deck onto a *copy* of the base game in place.
    The base game is built with the opponent's dev cards cleared, so we add the sampled
    hand's IN_HAND counts, fold its hidden VP cards into the opponent's actual VP, and
    pin the deck. Far cheaper than rebuilding the board each iteration."""
    key = f"P{game.state.color_to_index[opp_color]}"
    for t in DEV_TYPES:
        game.state.player_state[f"{key}_{t}_IN_HAND"] = hand[t]
    game.state.player_state[f"{key}_ACTUAL_VICTORY_POINTS"] += hand["VICTORY_POINT"]
    game.state.development_listdeck = list(deck)


def recommend_actions_ismcts(
    gs: GameState,
    iterations: int = 600,
    history: Optional[DevCardHistory] = None,
    policy: PolicyFactory = rollout_policy,
    rules: RulesConfig = COLONIST_1V1,
    seed: int = 0,
    ucb_c: float = _DEFAULT_UCB_C,
    max_depth: int = 40,
    rollout_depth: Optional[int] = None,
) -> List[ActionRecommendation]:
    """Rank the current player's legal actions by ISMCTS, best first.

    Unlike :func:`recommend_actions_pimc` (which determinizes once per tree and so
    "knows" the hidden cards inside each search — strategy fusion), ISMCTS keeps **one**
    tree and **re-samples** a determinization every iteration, only ever selecting moves
    legal in that world. Statistics therefore pool over all worlds consistent with the
    observer's information, forcing a move that is good *before* the hidden cards are
    known — as in the real game.

    The board is reconstructed once (with the opponent's dev cards cleared); each
    iteration copies that base and injects a fresh dev-card sample, so re-determinizing
    every iteration stays cheap.
    """
    random.seed(seed)  # engine samples dice via global random; pin for reproducibility
    rng = random.Random(seed)
    observer = gs.current_player
    belief = dev_card_belief(gs, observer)
    slot_meta = history.slot_metadata() if history is not None else None

    # base game with the opponent's hidden dev cards removed (added back per iteration)
    base_gs = gs.model_copy(deep=True)
    for p in base_gs.players:
        if p.color == belief.opponent:
            p.dev_cards = DevCards()
    base = game_from_state(base_gs, players=[policy(c) for c in _COLORS])
    root_player = base.state.colors[base.state.current_player_index]
    opp_color = next(c for c in base.state.colors if c != root_player)

    root = _Node(to_move=root_player, parent=None)
    for it in range(iterations):
        hand, deck = sample_dev_cards(belief, random.Random(seed * 100003 + it), slot_meta=slot_meta)
        game = base.copy()
        _inject_determinization(game, opp_color, hand, deck)
        _ismcts_iteration(root, game, root_player, rng, ucb_c, max_depth,
                          rollout_depth, gs.vps_to_win)

    return _recs_from_children(
        (action.action_type.value, action.value, child.visits, child.wins_root)
        for action, child in root.children.items()
    )
