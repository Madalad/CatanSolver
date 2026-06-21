"""Belief tracking + determinization sampling over hidden information (Phase 3.3).

In 1v1 Catan most "hidden" information is actually pinned down by public counts:

* **Opponent resource hand — *determined*.** Each resource has 19 cards in the game,
  so with the bank and our own hand both known, the opponent's hand follows exactly:
  ``opp[r] = 19 - bank[r] - our[r]``. There is nothing to sample (see
  :func:`resource_hand_residual`). For the general / log-only case where only the
  opponent's *hand size* is known, :func:`sample_opponent_hand` draws a composition.

* **Dev cards — *genuinely hidden*.** The opponent's face-down dev cards and the
  remaining deck are drawn, without replacement, from the **unseen pool** = the full
  25-card deck minus everything that has left it visibly: our own dev cards (we know
  our hand) plus every *played* card of both players (knights, monopolies,
  year-of-plenty, road-building — all public). A determinization draws the opponent's
  hand from that pool, with the remainder forming the deck.

The bare draw is a **multivariate hypergeometric** (uniform over the unseen pool given
the counts). On top of that we model two behavioural tells, both of which need a
per-card view of *how long each face-down card has been held* — supplied by the
stateful :class:`DevCardHistory`, fed the public turn log:

* **(3b) Held-duration → Victory Point.** Victory-Point cards are the only type never
  actively played (they're just revealed on the win); every other type is normally
  cashed within a few turns. So the longer a card is held, the less likely it is an
  actively-playable type — :data:`PLAYABLE_HELD_DECAY` per turn down-weights
  KNIGHT/MONOPOLY/YEAR_OF_PLENTY/ROAD_BUILDING, leaving VP relatively more probable.

* **(3a) Robbed-and-passed → not a Knight.** Each turn the robber sits on one of the
  opponent's hexes and they *could* have played a knight but didn't, the chance any
  held card is a knight is cut by 90% (:data:`KNIGHT_ROBBED_PASS_FACTOR` = 0.1) — so a
  couple of such turns drive it to ~0. Two guards keep it honest: it only counts when a
  knight play was actually possible (they had not already played a dev card that turn),
  and it only attaches to cards acquired *before* that turn (you can't play a card the
  turn you buy it). Both guards live in :meth:`DevCardHistory.observe_robbed_turn`.

A :class:`Determinization` pairs a fully-concrete :class:`GameState` (opponent dev
hand filled in) with the matching dev-deck list, ready to feed
``game_from_state(state, dev_deck=...)``. Averaging a search/rollout over many
determinizations is PIMC (Phase 3.4).

Without a :class:`DevCardHistory` the sampler degrades to the plain uniform draw, so a
single captured ``GameState`` (which has no turn history) still works. The history is
the seam through which Phase-6 live capture sharpens the belief.
"""
from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from catanatron.models.enums import RESOURCES

from catansolver.engine.state_adapter import DEV_DECK_FULL
from catansolver.io.schema import DevCards, GameState, Hand, PlayerState

#: dev-card type labels (Catanatron's string enum)
DEV_TYPES = ("KNIGHT", "VICTORY_POINT", "MONOPOLY", "YEAR_OF_PLENTY", "ROAD_BUILDING")
#: types a player actively *plays* (and so normally doesn't sit on) — all but VP
PLAYABLE_TYPES = frozenset({"KNIGHT", "MONOPOLY", "YEAR_OF_PLENTY", "ROAD_BUILDING"})
#: number of cards of each resource in the base game
RESOURCE_TOTAL = 19

#: (3b) per-turn-held multiplier on actively-playable types (VP is left at 1.0)
PLAYABLE_HELD_DECAY = 0.9
#: (3a) multiplier on KNIGHT per qualifying "robbed and didn't knight" turn (-90%)
KNIGHT_ROBBED_PASS_FACTOR = 0.1


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _player(gs: GameState, color: str) -> PlayerState:
    return next(p for p in gs.players if p.color == color)


def _opponent(gs: GameState, color: str) -> PlayerState:
    return next(p for p in gs.players if p.color != color)


def _dev_counter(dev: DevCards) -> Counter:
    return Counter(
        {
            "KNIGHT": dev.knight,
            "VICTORY_POINT": dev.victory_point,
            "MONOPOLY": dev.monopoly,
            "YEAR_OF_PLENTY": dev.year_of_plenty,
            "ROAD_BUILDING": dev.road_building,
        }
    )


def _dev_total(dev: DevCards) -> int:
    return dev.knight + dev.victory_point + dev.monopoly + dev.year_of_plenty + dev.road_building


# --------------------------------------------------------------------------- #
# Core statistical primitive
# --------------------------------------------------------------------------- #
def multivariate_hypergeometric(pool: Counter, k: int, rng: random.Random) -> Counter:
    """Draw ``k`` items without replacement from ``pool`` (item -> count), returning
    the drawn multiset as a ``Counter``.

    Equivalent to shuffling the multiset and taking the first ``k`` — the exact model
    of dealing dev cards / stealing a resource (sampling without replacement)."""
    bag: List[str] = []
    for item, count in pool.items():
        bag.extend([item] * count)
    if k > len(bag):
        raise ValueError(f"cannot draw {k} items from a pool of {len(bag)}")
    rng.shuffle(bag)
    return Counter(bag[:k])


# --------------------------------------------------------------------------- #
# Resource hand: determined in 1v1
# --------------------------------------------------------------------------- #
def resource_hand_residual(gs: GameState, observer: Optional[str] = None) -> Hand:
    """The opponent's resource hand implied by conservation: ``19 - bank[r] - our[r]``
    per resource. In a consistent 1v1 state this equals the opponent's recorded hand,
    which is why there is no opponent-resource uncertainty to determinize here."""
    observer = observer or gs.current_player
    me = _player(gs, observer)
    residual = {}
    for r in RESOURCES:
        key = r.lower()
        residual[key] = RESOURCE_TOTAL - getattr(gs.bank, key) - getattr(me.hand, key)
    return Hand(**residual)


def sample_opponent_hand(
    bank: Hand, own_hand: Hand, hand_size: int, rng: random.Random
) -> Hand:
    """Sample an opponent resource hand of ``hand_size`` cards from the pool the
    opponent could be holding — the cards in neither the bank nor our hand
    (``19 - bank[r] - own[r]`` of each resource) — by multivariate hypergeometric.

    Provided for the general / log-only case (only the opponent's *count* is known).
    In a fully-captured 1v1 ``GameState`` this is unnecessary because the residual
    above already pins the composition exactly."""
    pool = Counter()
    for r in RESOURCES:
        key = r.lower()
        pool[key] = max(0, RESOURCE_TOTAL - getattr(bank, key) - getattr(own_hand, key))
    drawn = multivariate_hypergeometric(pool, hand_size, rng)
    return Hand(**{k: drawn[k] for k in ("wood", "brick", "sheep", "wheat", "ore")})


# --------------------------------------------------------------------------- #
# Per-card history: the behavioural belief over the opponent's *held* cards
# --------------------------------------------------------------------------- #
@dataclass
class CardSlot:
    """One face-down dev card the opponent is believed to hold, tagged with the turn
    it was bought and how many qualifying "robbed and didn't knight" turns it has
    since survived."""

    acquired_turn: int
    robbed_passes: int = 0


@dataclass
class DevCardHistory:
    """Stateful belief over the opponent's *held* dev cards, fed the public turn log.

    Each held card is a :class:`CardSlot`. :meth:`slot_metadata` projects the slots to
    the ``(age_in_turns, robbed_passes)`` pairs the sampler turns into per-card weights.
    Construct one empty and drive it with the observed events; with no history the
    sampler falls back to a uniform draw.
    """

    slots: List[CardSlot] = field(default_factory=list)
    current_turn: int = 0

    def _advance(self, turn: int) -> None:
        self.current_turn = max(self.current_turn, turn)

    def observe_buy(self, turn: int) -> None:
        """Opponent bought a dev card on ``turn`` -> a fresh held slot."""
        self._advance(turn)
        self.slots.append(CardSlot(acquired_turn=turn))

    def observe_play(self, turn: int) -> None:
        """Opponent played a dev card on ``turn`` -> one fewer held card. We don't know
        which physical card it was; drop the oldest slot (players tend to cash older
        cards first, and it keeps the remaining ages conservative)."""
        self._advance(turn)
        if self.slots:
            self.slots.sort(key=lambda s: s.acquired_turn)
            self.slots.pop(0)

    def observe_robbed_turn(self, turn: int, *, opponent_played_dev_card: bool) -> None:
        """Record a turn where the robber sat on one of the opponent's hexes.

        Counts as "declined to knight" evidence only when a knight play was actually
        possible — i.e. they did **not** already play a dev card this turn (refinement
        1) — and the evidence attaches only to cards acquired **before** this turn,
        since a card can't be played the turn it's bought (refinement 2)."""
        self._advance(turn)
        if opponent_played_dev_card:
            return  # used their one dev play; "didn't knight" carries no information
        for s in self.slots:
            if s.acquired_turn < turn:
                s.robbed_passes += 1

    def slot_metadata(self) -> List[Tuple[int, int]]:
        """``(age_in_turns, robbed_passes)`` per held card, oldest first."""
        return [
            (self.current_turn - s.acquired_turn, s.robbed_passes)
            for s in sorted(self.slots, key=lambda s: s.acquired_turn)
        ]


def _type_weight(card_type: str, age: int, robbed_passes: int) -> float:
    """Sampling weight for a single held card being ``card_type``, given how long it
    has been held (3b) and how many robbed-and-passed turns it survived (3a)."""
    weight = 1.0
    if card_type in PLAYABLE_TYPES:
        weight *= PLAYABLE_HELD_DECAY ** age
    if card_type == "KNIGHT":
        weight *= KNIGHT_ROBBED_PASS_FACTOR ** robbed_passes
    return weight


def weighted_hand_draw(
    pool: Counter, slot_meta: Sequence[Tuple[int, int]], rng: random.Random
) -> Tuple[Counter, Counter]:
    """Assign a card type to each held slot, sampling without replacement from ``pool``
    with probability proportional to ``count[type] * _type_weight(type, *slot)``.

    Returns ``(hand, remaining_pool)``. Slot order matters only via each slot's own
    ``(age, robbed_passes)``; pass them oldest-first for readability."""
    pool = Counter(pool)
    hand: Counter = Counter()
    for age, robbed_passes in slot_meta:
        weights = {
            t: c * _type_weight(t, age, robbed_passes) for t, c in pool.items() if c > 0
        }
        total = sum(weights.values())
        if total <= 0.0:
            # every remaining type is fully suppressed (e.g. only knights left after
            # several robbed passes) — it must still be one of them; fall back to the
            # plain hypergeometric over what's left.
            pick = rng.choice(list(pool.elements()))
        else:
            threshold = rng.random() * total
            cumulative = 0.0
            pick = next(iter(weights))
            for t, w in weights.items():
                cumulative += w
                if threshold <= cumulative:
                    pick = t
                    break
        hand[pick] += 1
        pool[pick] -= 1
        if pool[pick] == 0:
            del pool[pick]
    return hand, pool


# --------------------------------------------------------------------------- #
# Dev-card belief
# --------------------------------------------------------------------------- #
@dataclass
class DevCardBelief:
    """The observer's belief over the dev cards they cannot see.

    ``unseen`` is the composition of *all* dev cards outside the observer's knowledge
    — the opponent's face-down hand plus the undrawn deck — from which both are
    sampled. ``opp_hand_size`` and ``deck_remaining`` are the public counts that split
    it.
    """

    observer: str
    opponent: str
    opp_hand_size: int
    deck_remaining: int
    unseen: Counter

    @property
    def hidden_total(self) -> int:
        return sum(self.unseen.values())


def dev_card_belief(gs: GameState, observer: Optional[str] = None) -> DevCardBelief:
    """Build the observer's dev-card belief from a captured ``GameState``.

    Only *public* facts about the opponent are used (their hand *size* and every played
    card) — never the recorded composition of their face-down hand. With played
    non-knight cards now tracked, the unseen pool is exact: ``hidden_total ==
    opp_hand_size + deck_remaining``."""
    observer = observer or gs.current_player
    me = _player(gs, observer)
    opp = _opponent(gs, observer)

    seen = _dev_counter(me.dev_cards)  # our own face-down cards are known to us
    for p in (me, opp):  # every *played* card is public and out of the deck
        seen["KNIGHT"] += p.played_knights
        seen["MONOPOLY"] += p.played_monopoly
        seen["YEAR_OF_PLENTY"] += p.played_year_of_plenty
        seen["ROAD_BUILDING"] += p.played_road_building

    unseen = Counter({t: max(0, DEV_DECK_FULL[t] - seen[t]) for t in DEV_TYPES})
    return DevCardBelief(
        observer=observer,
        opponent=opp.color,
        opp_hand_size=_dev_total(opp.dev_cards),
        deck_remaining=gs.dev_deck_remaining,
        unseen=unseen,
    )


def sample_dev_cards(
    belief: DevCardBelief,
    rng: random.Random,
    slot_meta: Optional[Sequence[Tuple[int, int]]] = None,
) -> Tuple[Counter, List[str]]:
    """Sample a concrete ``(opponent hand, remaining deck)`` consistent with ``belief``.

    With ``slot_meta`` (one ``(age, robbed_passes)`` per held card, from a
    :class:`DevCardHistory`) the opponent's hand is drawn with the behavioural weights;
    without it, a plain multivariate hypergeometric. The remainder, shuffled, is the
    deck — truncated/padded to the known ``deck_remaining``."""
    pool = Counter(belief.unseen)
    k = min(belief.opp_hand_size, sum(pool.values()))

    if slot_meta is None:
        hand = multivariate_hypergeometric(pool, k, rng)
        remainder = pool - hand
    else:
        meta = list(slot_meta)[:k]
        meta += [(0, 0)] * (k - len(meta))  # pad missing slots as freshly-acquired
        hand, remainder = weighted_hand_draw(pool, meta, rng)

    deck = list(remainder.elements())
    rng.shuffle(deck)
    n = belief.deck_remaining
    if len(deck) > n:
        deck = deck[:n]
    elif len(deck) < n:
        deck += ["KNIGHT"] * (n - len(deck))
    return hand, deck


# --------------------------------------------------------------------------- #
# Determinization
# --------------------------------------------------------------------------- #
@dataclass
class Determinization:
    """A fully-concrete world consistent with the observer's belief: a ``GameState``
    with the opponent's hidden dev hand filled in, plus the matching dev deck to feed
    ``game_from_state(state, dev_deck=deck)``."""

    state: GameState
    dev_deck: List[str]


def sample_determinization(
    gs: GameState,
    rng: Optional[random.Random] = None,
    observer: Optional[str] = None,
    history: Optional[DevCardHistory] = None,
) -> Determinization:
    """Sample one determinization of the hidden information from ``observer``'s view
    (default: the current player).

    Only the opponent's face-down dev cards and the deck are resampled — the
    observer's own cards and *both* resource hands are left as given (resource hands
    are determined in 1v1, see :func:`resource_hand_residual`). Pass a
    :class:`DevCardHistory` to apply the held-duration / robbed-pass weighting."""
    rng = rng or random.Random()
    observer = observer or gs.current_player
    det = gs.model_copy(deep=True)

    belief = dev_card_belief(det, observer)
    slot_meta = history.slot_metadata() if history is not None else None
    hand, deck = sample_dev_cards(belief, rng, slot_meta=slot_meta)

    opp = _player(det, belief.opponent)
    opp.dev_cards = DevCards(
        knight=hand["KNIGHT"],
        victory_point=hand["VICTORY_POINT"],
        monopoly=hand["MONOPOLY"],
        year_of_plenty=hand["YEAR_OF_PLENTY"],
        road_building=hand["ROAD_BUILDING"],
    )
    return Determinization(state=det, dev_deck=deck)
