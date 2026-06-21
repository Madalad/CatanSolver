"""Map a heuristic score to an estimated win probability.

A 2-parameter logistic ``P(win) = sigmoid(a + b * heuristic)`` fitted offline by
binomial MLE against WeightedRandom rollouts (the same even-strength baseline the
rollout mode uses). Calibration is **per seat** because the heuristic scales differ
— the SECOND seat scores a settlement *pair* (``pair_score``), roughly double the
single-node scale.

This gives the UI an interpretable, instant win-% for any spot without running
rollouts. Caveats (see docs/heuristic-accuracy.md):
  * it is relative to the baseline opponent, not a strong human;
  * it is the *average* win-rate for that heuristic level (board-agnostic), so the
    true board-specific value scatters by ~±8 points — show it coarsely;
  * running rollouts (``n_rollouts > 0``) gives the exact board-specific figure.

Fit/refresh with scripts/calibrate_winprob.py (writes docs/winprob-coeffs.json).
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

from catansolver.io.schema import DraftSeat

# logit(p) = a + b * heuristic, per seat (fit by binomial MLE; see
# docs/winprob-coeffs.json and scripts/calibrate_winprob.py). None = uncalibrated.
_COEFFS: Dict[DraftSeat, Optional[Tuple[float, float]]] = {
    # seat: (a, b)            # n_obs, calibration quality
    DraftSeat.FIRST: (-1.6015, 5.7759),       # 400, well-calibrated, low scatter
    DraftSeat.FIRST_FINAL: (-1.5795, 5.3170),  # 220, unbiased mean but noisier (the
    #                                            4th pick's outcome is mostly set by
    #                                            the first three settlements)
    DraftSeat.SECOND: (-3.7082, 5.7587),      # 220, well-calibrated (pair-score scale,
    #                                            so ~2x the single-node intercept)
}


def win_prob_estimate(seat: DraftSeat, heuristic: float) -> Optional[float]:
    """Estimated P(win) for a spot/pair with this heuristic score, or None if the
    seat has not been calibrated yet."""
    coeffs = _COEFFS.get(seat)
    if coeffs is None:
        return None
    a, b = coeffs
    return 1.0 / (1.0 + math.exp(-(a + b * heuristic)))
