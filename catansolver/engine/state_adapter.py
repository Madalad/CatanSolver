"""Mid-game state import/export: our :class:`GameState` schema <-> a live Catanatron
game. The Phase-3 prerequisite that was deferred from Phase 1.

The board adapter (:mod:`catansolver.engine.adapter`) handles the static tiles/ports;
this handles the *dynamic* state — buildings, roads, hands, dev cards, the Longest
Road / Largest Army bonuses, the bank, the dev deck, and whose turn it is.

Import is the hard direction. Catanatron has no "set position" entry point, so we:
  * place each player's settlements/cities via ``board.build_settlement`` in
    *initial-build* mode (skips the connectivity check but keeps the distance rule,
    which any real position already satisfies) so the board's road-length /
    connected-component caches stay valid — then upgrade the cities;
  * place roads in connectivity order (a fixpoint: repeatedly lay any road that now
    touches its colour's network);
  * mirror the per-player counts/VPs with :mod:`catanatron.state_functions`;
  * recompute Longest Road / Largest Army from the finished board;
  * set hands, dev cards, the bank, the remaining dev deck, and the current player.

Hidden/known caveat: the schema tracks ``played_knights`` (needed for Largest Army)
but not other *played* dev cards, so the reconstructed dev deck matches the remaining
*count* but not necessarily its exact composition — a belief-tracking concern for a
later sub-phase, not for importing a position.
"""
from __future__ import annotations

from collections import Counter
from typing import List, Optional

from catanatron import Color, Game, Player, RandomPlayer
from catanatron.models.actions import generate_playable_actions
from catanatron.models.board import longest_acyclic_path
from catanatron.models.enums import ActionPrompt, DEVELOPMENT_CARDS, RESOURCES
from catanatron import state_functions as sf

from catansolver.engine.adapter import board_from_game, game_from_board
from catansolver.engine.config import COLONIST_1V1, RulesConfig
from catansolver.io.schema import DevCards, GameState, Hand, Phase, PlayerState

SETTLEMENT, CITY, ROAD = "SETTLEMENT", "CITY", "ROAD"
# Standard base-game development deck (25 cards).
DEV_DECK_FULL = Counter(
    {"KNIGHT": 14, "VICTORY_POINT": 5, "MONOPOLY": 2, "YEAR_OF_PLENTY": 2, "ROAD_BUILDING": 2}
)
_DEFAULT_COLORS = (Color.RED, Color.BLUE)


def _edge(e):
    return tuple(sorted(e))


def _force_build_road(board, color, edge) -> None:
    """Place a road bypassing ``board.build_road``'s buildable-edge gate, mirroring its
    connected-component + longest-road bookkeeping otherwise. Used only for roads the
    connectivity fixpoint can't reach — a legal historical road since *split off* by an
    enemy settlement on a connecting node. Such a severed segment forms its own
    component (per the rule that an enemy settlement breaks a road), so its length is
    still counted correctly toward Longest Road."""
    a, b = edge
    board.roads[(a, b)] = color
    board.roads[(b, a)] = color

    comps = board.connected_components[color]
    a_index = board._get_connected_component_index(a, color)
    b_index = board._get_connected_component_index(b, color)
    a_enemy = board.is_enemy_node(a, color)
    b_enemy = board.is_enemy_node(b, color)
    if a_index is None and b_index is None:  # seed a brand-new (severed) component
        comp = set()
        if not a_enemy:
            comp.add(a)
        if not b_enemy:
            comp.add(b)
        comps.append(comp)
        component = comp
    elif a_index is None:
        if not a_enemy:
            comps[b_index].add(a)
        component = comps[b_index]
    elif b_index is None:
        if not b_enemy:
            comps[a_index].add(b)
        component = comps[a_index]
    elif a_index != b_index:  # the road joins two components
        merged = comps[a_index].union(comps[b_index])
        for index in sorted([a_index, b_index], reverse=True):
            del comps[index]
        comps.append(merged)
        component = merged
    else:
        component = comps[a_index]

    candidate_length = len(longest_acyclic_path(board, component, color))
    board.road_lengths[color] = max(board.road_lengths[color], candidate_length)
    if candidate_length >= 5 and candidate_length > board.road_length:
        board.road_color = color
        board.road_length = candidate_length


def _force_place_pending_roads(state, pending) -> None:
    """Force-place every road the fixpoint left unreachable, growing components
    connected-first (and seeding a new component only when a road is truly isolated)
    so a multi-road severed segment is reconstructed as one component, not fragmented."""
    flat = [(color, e) for color, edges in pending.items() for e in edges]
    while flat:
        remaining, progress = [], False
        for color, e in flat:
            a, b = e
            touches = (
                state.board._get_connected_component_index(a, color) is not None
                or state.board._get_connected_component_index(b, color) is not None
            )
            if touches:
                _force_build_road(state.board, color, e)
                sf.build_road(state, color, e, is_free=True)
                progress = True
            else:
                remaining.append((color, e))
        if not progress:  # all isolated: seed one new component, then reconnect the rest
            color, e = remaining.pop(0)
            _force_build_road(state.board, color, e)
            sf.build_road(state, color, e, is_free=True)
        flat = remaining


def _label_to_color(gs: GameState, state) -> dict:
    """Map each schema player's colour *label* to a distinct Catanatron ``Color`` in
    ``state.colors`` — by enum value when the label is a real colour (the round-trip
    case), otherwise by seat order for arbitrary labels like ``"P1"``."""
    mapping, used = {}, set()
    for p in gs.players:
        try:
            c = Color(p.color)
        except ValueError:
            c = None
        if c is None or c not in state.colors or c in used:
            c = next(col for col in state.colors if col not in used)
        mapping[p.color] = c
        used.add(c)
    return mapping


# --------------------------------------------------------------------------- #
# Export: live game -> schema
# --------------------------------------------------------------------------- #
def game_to_state(game: Game, rules: RulesConfig = COLONIST_1V1) -> GameState:
    """Serialise a live Catanatron game to a :class:`GameState`."""
    s = game.state
    players: List[PlayerState] = []
    for i, color in enumerate(s.colors):
        key = f"P{i}"
        ps = s.player_state
        hand = Hand(**{r.lower(): ps[f"{key}_{r}_IN_HAND"] for r in RESOURCES})
        dev = DevCards(**{c.lower(): ps[f"{key}_{c}_IN_HAND"] for c in DEVELOPMENT_CARDS})
        bc = s.buildings_by_color[color]
        players.append(
            PlayerState(
                color=color.value,
                hand=hand,
                dev_cards=dev,
                played_knights=ps[f"{key}_PLAYED_KNIGHT"],
                played_monopoly=ps[f"{key}_PLAYED_MONOPOLY"],
                played_year_of_plenty=ps[f"{key}_PLAYED_YEAR_OF_PLENTY"],
                played_road_building=ps[f"{key}_PLAYED_ROAD_BUILDING"],
                settlements=sorted(bc.get(SETTLEMENT, [])),
                cities=sorted(bc.get(CITY, [])),
                roads=sorted(_edge(e) for e in bc.get(ROAD, [])),
                has_longest_road=bool(ps[f"{key}_HAS_ROAD"]),
                has_largest_army=bool(ps[f"{key}_HAS_ARMY"]),
            )
        )
    bank = Hand(**{r.lower(): s.resource_freqdeck[i] for i, r in enumerate(RESOURCES)})
    # Emit players in a canonical (colour-sorted) order, independent of Catanatron's
    # seed-dependent seating, so the schema round-trips. 1v1 turn order is captured
    # by `current_player` and just alternates, so list position carries no meaning.
    players.sort(key=lambda p: p.color)
    return GameState(
        board=board_from_game(game),
        players=players,
        bank=bank,
        dev_deck_remaining=len(s.development_listdeck),
        current_player=s.colors[s.current_player_index].value,
        phase=Phase.SETUP if s.is_initial_build_phase else Phase.PLAY,
        dice=None,
        has_rolled=(
            not s.is_initial_build_phase
            and bool(s.player_state[f"P{s.current_player_index}_HAS_ROLLED"])
        ),
        prompt=s.current_prompt.name,
        vps_to_win=rules.vps_to_win,
        discard_limit=rules.discard_limit,
        friendly_robber=rules.friendly_robber,
    )


# --------------------------------------------------------------------------- #
# Import: schema -> live game
# --------------------------------------------------------------------------- #
def game_from_state(
    gs: GameState,
    players: Optional[List[Player]] = None,
    rules: RulesConfig = COLONIST_1V1,
    dev_deck: Optional[List[str]] = None,
) -> Game:
    """Build a live Catanatron game realising the position in ``gs``.

    ``players`` (defaulting to two ``RandomPlayer``s) are seated in schema order;
    their policy is irrelevant for analysis — the search drives the game.

    ``dev_deck`` lets a caller pin the remaining dev-deck composition/order (e.g. a
    sampled determinization from :mod:`catansolver.beliefs`); when ``None`` a plausible
    deck of the right *length* is reconstructed from what's visible.
    """
    if players is None:
        players = [RandomPlayer(c) for c in _DEFAULT_COLORS]
    game = game_from_board(gs.board, players, rules=rules, seed=0)
    s = game.state
    s.is_initial_build_phase = gs.phase == Phase.SETUP

    # Catanatron decides its own seating, so map each schema player to a Catanatron
    # Color by *value* (falling back to seat order for non-standard labels) rather
    # than position. Keys come from color_to_index, never the loop index.
    color_of = _label_to_color(gs, s)
    key_of = {label: f"P{s.color_to_index[c]}" for label, c in color_of.items()}

    # 1) settlements + cities: seed every owned node as a settlement (graph caches),
    #    then upgrade the cities.
    for p in gs.players:
        color = color_of[p.color]
        for node in list(p.settlements) + list(p.cities):
            s.board.build_settlement(color, node, initial_build_phase=True)
            sf.build_settlement(s, color, node, is_free=True)
        for node in p.cities:
            s.board.build_city(color, node)
            sf.build_city(s, color, node)

    # 2) roads: connectivity-order fixpoint (each must touch its colour's network).
    pending = {color_of[p.color]: [_edge(e) for e in p.roads] for p in gs.players}
    while any(pending.values()):
        progress = False
        for color, edges in pending.items():
            buildable = {_edge(e) for e in s.board.buildable_edges(color)}
            keep = []
            for e in edges:
                if e in buildable:
                    s.board.build_road(color, e)
                    sf.build_road(s, color, e, is_free=True)
                    progress = True
                else:
                    keep.append(e)
            pending[color] = keep
        if not progress:
            # Whatever's left can't be reached by extending the network — it's a legal
            # road severed from its owner's settlements by an enemy build. Place those
            # directly (faithful board, correct broken-segment Longest Road) instead of
            # crashing the import.
            _force_place_pending_roads(s, pending)
            break

    # 3) hands, dev cards, played knights, hidden VP dev cards (-> ACTUAL only).
    for p in gs.players:
        key = key_of[p.color]
        for r in RESOURCES:
            s.player_state[f"{key}_{r}_IN_HAND"] = getattr(p.hand, r.lower())
        for c in DEVELOPMENT_CARDS:
            s.player_state[f"{key}_{c}_IN_HAND"] = getattr(p.dev_cards, c.lower())
        s.player_state[f"{key}_PLAYED_KNIGHT"] = p.played_knights
        s.player_state[f"{key}_PLAYED_MONOPOLY"] = p.played_monopoly
        s.player_state[f"{key}_PLAYED_YEAR_OF_PLENTY"] = p.played_year_of_plenty
        s.player_state[f"{key}_PLAYED_ROAD_BUILDING"] = p.played_road_building
        s.player_state[f"{key}_ACTUAL_VICTORY_POINTS"] += p.dev_cards.victory_point

    # 4) Longest Road (>=5) and Largest Army (>=3 knights), recomputed from the board.
    holder = s.board.road_color if s.board.road_length >= 5 else None
    sf.mantain_longest_road(s, None, holder, s.board.road_lengths)
    knights = {color_of[p.color]: p.played_knights for p in gs.players}
    leader = max(knights, key=knights.get)
    if knights[leader] >= 3:
        sf.mantain_largets_army(s, leader, None, 0)

    # 5) bank, dev deck (match the remaining count; composition is best-guess), turn.
    s.resource_freqdeck = [getattr(gs.bank, r.lower()) for r in RESOURCES]
    s.development_listdeck = list(dev_deck) if dev_deck is not None else _remaining_dev_deck(gs)
    s.current_player_index = s.color_to_index[color_of[gs.current_player]]
    # generate_playable_actions branches on current_prompt, not is_initial_build_phase:
    # a mid-game turn is PLAY_TURN (ROLL offered until rolled), MOVE_ROBBER after a 7 /
    # knight, or DISCARD. Restore the captured sub-prompt + roll flag so the reconstructed
    # action set matches the live one (dice non-None kept as a legacy "rolled" marker).
    if gs.phase == Phase.PLAY:
        s.current_prompt = ActionPrompt[gs.prompt]
        s.player_state[f"P{s.current_player_index}_HAS_ROLLED"] = gs.has_rolled or gs.dice is not None

    s.playable_actions = generate_playable_actions(s)
    return game


def _remaining_dev_deck(gs: GameState) -> List[str]:
    """A plausible remaining dev deck of length ``gs.dev_deck_remaining``: the full
    deck minus what is visible (in hand + played knights), truncated/padded to fit."""
    seen = Counter()
    for p in gs.players:
        seen["KNIGHT"] += p.dev_cards.knight + p.played_knights
        seen["YEAR_OF_PLENTY"] += p.dev_cards.year_of_plenty + p.played_year_of_plenty
        seen["MONOPOLY"] += p.dev_cards.monopoly + p.played_monopoly
        seen["ROAD_BUILDING"] += p.dev_cards.road_building + p.played_road_building
        seen["VICTORY_POINT"] += p.dev_cards.victory_point
    pool: List[str] = []
    for card, total in DEV_DECK_FULL.items():
        pool += [card] * max(0, total - seen[card])
    n = gs.dev_deck_remaining
    if len(pool) >= n:
        return pool[:n]
    return pool + ["KNIGHT"] * (n - len(pool))
