"""Tier 1 — initial-placement optimizer (Phase 2). See plan.md §6.3.

Draft-aware opening recommendations with Monte-Carlo win-probability estimates,
for all three seats: FIRST (P1 opener), SECOND (joint settlement pair), and
FIRST_FINAL (P1's last pick).
"""

from .draft import default_policy, drive_to_user_decision
from .heuristic import best_initial_road, node_score, pair_score
from .opening_value import opening_win_prob, opening_win_prob_gap
from .optimize import optimal_continuation, recommend_opening
from .practice import generate_puzzle, grade_practice
from .rollout import estimate_win_prob, wilson_interval
from .winprob_model import win_prob_estimate

__all__ = [
    "recommend_opening",
    "node_score",
    "pair_score",
    "best_initial_road",
    "estimate_win_prob",
    "wilson_interval",
    "drive_to_user_decision",
    "optimal_continuation",
    "default_policy",
    "generate_puzzle",
    "grade_practice",
    "win_prob_estimate",
    "opening_win_prob",
    "opening_win_prob_gap",
]
