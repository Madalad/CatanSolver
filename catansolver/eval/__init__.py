"""Evaluation: heuristic policy now, learned value/policy later (Phases 2-5). See plan.md §6.3, §6.6.

Phase 3.5 ships a strength-evaluation arena: wrap the PIMC advisor as a Catanatron
player and run balanced matches against baselines, reporting win-rate + Wilson CI.
"""

from .arena import AdvisorPlayer, MatchResult, play_match
from .calibration import CalibrationReport, collect_samples, reliability
from .recalibrate import Calibrator, fit_isotonic
from .tournament import Standing, TournamentResult, fit_elo, run_tournament

__all__ = [
    "AdvisorPlayer",
    "MatchResult",
    "play_match",
    "Standing",
    "TournamentResult",
    "fit_elo",
    "run_tournament",
    "CalibrationReport",
    "collect_samples",
    "reliability",
    "Calibrator",
    "fit_isotonic",
]
