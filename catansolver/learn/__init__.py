"""Tier-3 learned play (Phase 5). See plan.md §6.6.

A numpy-only learned **value function**: engineered position features -> a logistic
P(win), trained on self-play outcomes, used as the MCTS leaf evaluator (Approach D) to
replace the crude VP-lead heuristic and the weak-self-model rollouts the calibration
study flagged. Deep RL / AlphaZero stay a later stretch gated on a proper ML environment.
"""

from .features import FEATURE_NAMES, extract_features
from .selfplay import collect_opening_samples, collect_opening_samples_parallel, generate_dataset
from .value_model import ValueModel, train_logistic

__all__ = [
    "FEATURE_NAMES",
    "extract_features",
    "generate_dataset",
    "collect_opening_samples",
    "collect_opening_samples_parallel",
    "ValueModel",
    "train_logistic",
]
