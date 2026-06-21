"""Phase 3.3: belief tracking + determinization sampling over hidden info.

Covers the multivariate-hypergeometric primitive, the dev-card belief derived from a
state, the determinization sampler, and the 1v1 resource-hand determinacy result.
"""
import random
from collections import Counter

from catanatron import Color, RandomPlayer
from catanatron.models.map import BASE_MAP_TEMPLATE, CatanMap

from catansolver.beliefs import (
    DevCardBelief,
    DevCardHistory,
    dev_card_belief,
    multivariate_hypergeometric,
    resource_hand_residual,
    sample_determinization,
    sample_dev_cards,
    sample_opponent_hand,
    weighted_hand_draw,
)
from catansolver.beliefs.determinize import DEV_TYPES, _dev_total
from catansolver.engine import game_from_board, game_from_state, game_to_state, map_to_schema
from catansolver.engine.state_adapter import DEV_DECK_FULL
from catansolver.io.schema import (
    BoardState,
    DevCards,
    GameState,
    Hand,
    PlayerState,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _empty_board() -> BoardState:
    return map_to_schema(CatanMap.from_template(BASE_MAP_TEMPLATE))


def _state(*, p0_dev=None, p1_dev=None, p0_knights=0, p1_knights=0, deck=25, p1_played=None) -> GameState:
    """A minimal, fully-controlled 1v1 state for exact belief arithmetic.

    ``p1_played`` optionally sets the opponent's played non-knight dev cards as a dict,
    e.g. ``{"played_monopoly": 1}``."""
    return GameState(
        board=_empty_board(),
        players=[
            PlayerState(color="RED", dev_cards=p0_dev or DevCards(), played_knights=p0_knights),
            PlayerState(
                color="BLUE",
                dev_cards=p1_dev or DevCards(),
                played_knights=p1_knights,
                **(p1_played or {}),
            ),
        ],
        bank=Hand(wood=19, brick=19, sheep=19, wheat=19, ore=19),
        dev_deck_remaining=deck,
        current_player="RED",
    )


def _midgame_state(seed: int = 7, ticks: int = 80) -> GameState:
    random.seed(seed)
    board = _empty_board()
    g = game_from_board(board, [RandomPlayer(Color.RED), RandomPlayer(Color.BLUE)], seed=seed)
    for _ in range(ticks):
        if g.winning_color() is not None:
            break
        g.play_tick()
    return game_to_state(g)


# --------------------------------------------------------------------------- #
# multivariate hypergeometric
# --------------------------------------------------------------------------- #
def test_hypergeometric_draws_exactly_k_within_pool():
    pool = Counter({"KNIGHT": 14, "VICTORY_POINT": 5, "MONOPOLY": 2})
    rng = random.Random(0)
    for k in (0, 1, 7, 21):
        draw = multivariate_hypergeometric(pool, k, rng)
        assert sum(draw.values()) == k
        for card, n in draw.items():
            assert n <= pool[card]  # never draws more than exist


def test_hypergeometric_full_pool_returns_pool():
    pool = Counter({"KNIGHT": 14, "VICTORY_POINT": 5})
    draw = multivariate_hypergeometric(pool, sum(pool.values()), random.Random(1))
    assert draw == pool


def test_hypergeometric_is_seed_deterministic():
    pool = Counter({"KNIGHT": 14, "VICTORY_POINT": 5, "MONOPOLY": 2, "YEAR_OF_PLENTY": 2})
    a = multivariate_hypergeometric(pool, 6, random.Random(42))
    b = multivariate_hypergeometric(pool, 6, random.Random(42))
    assert a == b


def test_hypergeometric_rejects_oversized_draw():
    import pytest

    with pytest.raises(ValueError):
        multivariate_hypergeometric(Counter({"KNIGHT": 2}), 3, random.Random(0))


# --------------------------------------------------------------------------- #
# dev-card belief
# --------------------------------------------------------------------------- #
def test_belief_unseen_is_full_deck_when_nothing_known():
    belief = dev_card_belief(_state())
    assert belief.unseen == Counter(DEV_DECK_FULL)
    assert belief.hidden_total == 25


def test_belief_subtracts_our_hand_and_all_played_knights():
    gs = _state(
        p0_dev=DevCards(knight=1, victory_point=1),  # observer (RED) holds these
        p0_knights=2,
        p1_knights=3,  # opponent's played knights are public
        deck=25 - 7,
    )
    belief = dev_card_belief(gs)
    # 14 knights - (1 in our hand + 2 ours played + 3 theirs played) = 8 unseen knights
    assert belief.unseen["KNIGHT"] == 14 - 1 - 2 - 3
    assert belief.unseen["VICTORY_POINT"] == 5 - 1
    # the opponent's hand-size is public; its composition is NOT used
    assert belief.opponent == "BLUE"
    assert belief.opp_hand_size == 0


def test_belief_ignores_opponent_hand_composition():
    """Two states differing only in the opponent's hidden composition (same count)
    must yield identical beliefs — we must not peek at the truth."""
    a = _state(p1_dev=DevCards(knight=2))
    b = _state(p1_dev=DevCards(victory_point=2))
    ba, bb = dev_card_belief(a), dev_card_belief(b)
    assert ba.unseen == bb.unseen
    assert ba.opp_hand_size == bb.opp_hand_size == 2


def test_belief_consistency_unseen_splits_into_hand_and_deck():
    # opponent holds 3 dev cards, 10 left in deck; nothing else revealed
    gs = _state(p1_dev=DevCards(knight=3), deck=22)
    belief = dev_card_belief(gs)
    assert belief.hidden_total == belief.opp_hand_size + belief.deck_remaining == 25


# --------------------------------------------------------------------------- #
# sample_dev_cards
# --------------------------------------------------------------------------- #
def test_sample_dev_cards_respects_size_and_pool():
    gs = _state(p1_dev=DevCards(knight=4), deck=21)  # opp holds 4, 21 in deck
    belief = dev_card_belief(gs)
    rng = random.Random(3)
    hand, deck = sample_dev_cards(belief, rng)
    assert sum(hand.values()) == belief.opp_hand_size == 4
    assert len(deck) == belief.deck_remaining == 21
    # hand + deck composition is exactly the unseen pool (consistent state)
    assert hand + Counter(deck) == belief.unseen


def test_sample_dev_cards_varies_across_seeds():
    gs = _state(p1_dev=DevCards(knight=5), deck=20)
    belief = dev_card_belief(gs)
    draws = {tuple(sorted(sample_dev_cards(belief, random.Random(s))[0].items())) for s in range(30)}
    assert len(draws) > 1  # genuine sampling, not a fixed answer


# --------------------------------------------------------------------------- #
# resource-hand determinacy (1v1)
# --------------------------------------------------------------------------- #
def test_resource_hand_is_determined_in_1v1():
    gs = _midgame_state()
    residual = resource_hand_residual(gs)  # opponent of current player
    opp = next(p for p in gs.players if p.color != gs.current_player)
    assert residual.model_dump() == opp.hand.model_dump()


def test_sample_opponent_hand_matches_residual_size_and_pool():
    bank = Hand(wood=10, brick=12, sheep=11, wheat=9, ore=13)
    own = Hand(wood=2, brick=1, sheep=3, wheat=4, ore=0)
    size = 6
    hand = sample_opponent_hand(bank, own, size, random.Random(5))
    assert hand.total == size
    for r in ("wood", "brick", "sheep", "wheat", "ore"):
        assert getattr(hand, r) <= 19 - getattr(bank, r) - getattr(own, r)


# --------------------------------------------------------------------------- #
# determinization
# --------------------------------------------------------------------------- #
def test_determinization_preserves_observer_and_resource_hands():
    gs = _midgame_state()
    det = sample_determinization(gs, random.Random(1))
    obs = gs.current_player
    me_before = next(p for p in gs.players if p.color == obs)
    me_after = next(p for p in det.state.players if p.color == obs)
    # observer's own dev cards untouched; both resource hands untouched
    assert me_after.dev_cards.model_dump() == me_before.dev_cards.model_dump()
    for p_before in gs.players:
        p_after = next(p for p in det.state.players if p.color == p_before.color)
        assert p_after.hand.model_dump() == p_before.hand.model_dump()


def test_determinization_preserves_opponent_dev_count():
    gs = _state(p1_dev=DevCards(knight=2, victory_point=1), deck=22)  # opp holds 3
    det = sample_determinization(gs, random.Random(0), observer="RED")
    opp_after = next(p for p in det.state.players if p.color == "BLUE")
    assert _dev_total(opp_after.dev_cards) == 3
    assert len(det.dev_deck) == 22


def test_determinizations_vary_and_stay_legal():
    gs = _state(p1_dev=DevCards(knight=4), deck=21)
    seen = set()
    for s in range(25):
        det = sample_determinization(gs, random.Random(s), observer="RED")
        opp = next(p for p in det.state.players if p.color == "BLUE")
        seen.add(tuple(opp.dev_cards.model_dump().items()))
        assert _dev_total(opp.dev_cards) == 4  # always a valid count
    assert len(seen) > 1  # the opponent's sampled composition genuinely varies


def test_determinization_imports_into_a_playable_game():
    gs = _midgame_state()
    det = sample_determinization(gs, random.Random(2))
    game = game_from_state(det.state, dev_deck=det.dev_deck)
    assert game.state.playable_actions  # the determinized position is playable
    # the deck we pinned is the one the engine will draw from
    assert list(game.state.development_listdeck) == list(det.dev_deck)


# --------------------------------------------------------------------------- #
# (2) played non-knight dev cards: exact pool + round-trip
# --------------------------------------------------------------------------- #
def test_belief_subtracts_played_nonknight_devs():
    # opponent has played 1 monopoly + 1 road-building (public, out of the deck)
    gs = _state(p1_played={"played_monopoly": 1, "played_road_building": 1}, deck=23)
    belief = dev_card_belief(gs)
    assert belief.unseen["MONOPOLY"] == 2 - 1
    assert belief.unseen["ROAD_BUILDING"] == 2 - 1
    # pool is now exact: nothing in hand, so it's entirely the deck
    assert belief.hidden_total == belief.deck_remaining == 23


def test_played_nonknight_devs_round_trip_through_adapter():
    gs = _state(p1_played={"played_year_of_plenty": 1, "played_monopoly": 1}, deck=23)
    gs2 = game_to_state(game_from_state(gs))
    opp = next(p for p in gs2.players if p.color == "BLUE")
    assert opp.played_year_of_plenty == 1
    assert opp.played_monopoly == 1


# --------------------------------------------------------------------------- #
# (3b) held-duration -> Victory Point weighting
# --------------------------------------------------------------------------- #
def _sampled_type_frequencies(slot_meta, pool, n=400):
    counts = Counter()
    for s in range(n):
        hand, _ = weighted_hand_draw(pool, slot_meta, random.Random(s))
        counts += hand
    return counts


def test_long_held_card_skews_toward_victory_point():
    # a balanced pool of one VP and one of each playable type
    pool = Counter({"KNIGHT": 1, "MONOPOLY": 1, "YEAR_OF_PLENTY": 1, "VICTORY_POINT": 1})
    fresh = _sampled_type_frequencies([(0, 0)], pool)
    aged = _sampled_type_frequencies([(15, 0)], pool)
    # held 15 turns: VP should dominate the fresh-draw VP rate and beat any playable
    assert aged["VICTORY_POINT"] > fresh["VICTORY_POINT"]
    assert aged["VICTORY_POINT"] > aged["KNIGHT"]


# --------------------------------------------------------------------------- #
# (3a) robbed-and-passed -> not a Knight
# --------------------------------------------------------------------------- #
def test_robbed_passes_suppress_knight_in_draw():
    pool = Counter({"KNIGHT": 3, "VICTORY_POINT": 1})  # knight-heavy pool
    no_evidence = _sampled_type_frequencies([(0, 0)], pool)
    suppressed = _sampled_type_frequencies([(0, 3)], pool)  # 3 robbed-and-passed turns
    assert no_evidence["KNIGHT"] > suppressed["KNIGHT"]
    # after 3 passes the 0.1**3 factor makes a knight draw essentially vanish
    assert suppressed["KNIGHT"] <= 2  # out of 400 samples


def test_robbed_pass_factor_pushes_knights_into_deck():
    gs = _state(p1_dev=DevCards(knight=1, victory_point=0), deck=24)  # opp holds 1 card
    hist = DevCardHistory()
    hist.observe_buy(turn=1)
    for t in (2, 3, 4):
        hist.observe_robbed_turn(t, opponent_played_dev_card=False)
    knight_hands = 0
    for s in range(200):
        det = sample_determinization(gs, random.Random(s), observer="RED", history=hist)
        opp = next(p for p in det.state.players if p.color == "BLUE")
        knight_hands += opp.dev_cards.knight
    assert knight_hands == 0  # the held card is almost never believed a knight now


# --------------------------------------------------------------------------- #
# DevCardHistory event semantics (refinements 1 & 2)
# --------------------------------------------------------------------------- #
def test_history_buy_turn_is_not_counted_as_a_pass():
    # refinement 2: a card can't be played the turn it's bought
    hist = DevCardHistory()
    hist.observe_buy(turn=5)
    hist.observe_robbed_turn(turn=5, opponent_played_dev_card=False)
    assert hist.slot_metadata() == [(0, 0)]  # no robbed_pass credited on the buy turn


def test_history_pass_credited_on_later_turn_per_card_epoch():
    hist = DevCardHistory()
    hist.observe_buy(turn=2)  # old card
    hist.observe_robbed_turn(turn=4, opponent_played_dev_card=False)
    hist.observe_buy(turn=4)  # new card, same turn as the pass
    meta = dict(  # map age -> robbed_passes via acquisition; oldest first
        zip(("old", "new"), [m[1] for m in hist.slot_metadata()])
    )
    # only the card acquired before turn 4 gets the pass
    assert sorted(m[1] for m in hist.slot_metadata()) == [0, 1]


def test_history_already_played_dev_is_not_a_pass():
    # refinement 1: if they already played a dev card that turn, declining a knight
    # carries no information
    hist = DevCardHistory()
    hist.observe_buy(turn=1)
    hist.observe_robbed_turn(turn=3, opponent_played_dev_card=True)
    assert hist.slot_metadata() == [(2, 0)]  # age 2, no pass credited


def test_history_play_drops_a_held_slot():
    hist = DevCardHistory()
    hist.observe_buy(turn=1)
    hist.observe_buy(turn=2)
    hist.observe_play(turn=3)
    assert len(hist.slot_metadata()) == 1  # one card left after a play


def test_determinization_without_history_matches_uniform_path():
    # no history -> identical to the plain hypergeometric draw (back-compat)
    gs = _state(p1_dev=DevCards(knight=3), deck=22)
    a = sample_determinization(gs, random.Random(7), observer="RED")
    b = sample_determinization(gs, random.Random(7), observer="RED", history=None)
    opp_a = next(p for p in a.state.players if p.color == "BLUE")
    opp_b = next(p for p in b.state.players if p.color == "BLUE")
    assert opp_a.dev_cards.model_dump() == opp_b.dev_cards.model_dump()
