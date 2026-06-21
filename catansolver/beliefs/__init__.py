"""Hidden-information belief tracking + determinization sampling (Phase 3.3). See plan.md §6.5.

Given a captured :class:`~catansolver.io.schema.GameState`, build the current player's
belief over what they cannot see (dev cards) and sample concrete *determinizations*
of it for the PIMC/ISMCTS search (Phase 3.4). A :class:`DevCardHistory`, fed the public
turn log, sharpens the belief with two behavioural tells (held-duration -> VP;
robbed-and-passed -> not a knight).
"""

from .determinize import (
    DEV_TYPES,
    KNIGHT_ROBBED_PASS_FACTOR,
    PLAYABLE_HELD_DECAY,
    PLAYABLE_TYPES,
    RESOURCE_TOTAL,
    CardSlot,
    Determinization,
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

__all__ = [
    "DEV_TYPES",
    "PLAYABLE_TYPES",
    "RESOURCE_TOTAL",
    "PLAYABLE_HELD_DECAY",
    "KNIGHT_ROBBED_PASS_FACTOR",
    "CardSlot",
    "DevCardBelief",
    "DevCardHistory",
    "Determinization",
    "dev_card_belief",
    "sample_dev_cards",
    "sample_determinization",
    "multivariate_hypergeometric",
    "weighted_hand_draw",
    "resource_hand_residual",
    "sample_opponent_hand",
]
