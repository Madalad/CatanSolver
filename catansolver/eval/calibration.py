"""Phase 4.2 — win-probability calibration.

The advisor attaches a P(win) to the move it plays. Calibration asks the blunt
question: when it says 70%, does it actually win ~70%? We play the advisor against the
**rollout-level opponent** (WeightedRandom — the policy its own rollouts assume, so the
comparison is self-consistent), record each chosen move's predicted win-prob, label it
with the eventual game outcome, and score the (prediction, outcome) pairs with:

* **Brier score** — mean squared error of the probabilities (lower is better; the
  constant base-rate predictor scores ``p(1-p)``).
* **Log-loss** — penalises confident wrong calls harder.
* **ECE** (expected calibration error) + a **reliability table** — predicted vs observed
  frequency per probability bin.

Two known biases pull in opposite directions and are why this is worth *measuring*
rather than assuming: the chosen move is an argmax over noisy estimates (winner's curse
-> over-confidence), while the rollouts model the advisor's own future play as the weaker
WeightedRandom (-> under-confidence). The net is an empirical question.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Tuple

from catanatron import Color
from catanatron.players.weighted_random import WeightedRandomPlayer

from catansolver.engine import COLONIST_1V1, RulesConfig, new_1v1_game

Sample = Tuple[float, float]  # (predicted win-prob, outcome in {0,1})


@dataclass
class CalibrationReport:
    n: int
    brier: float
    log_loss: float
    ece: float
    base_rate: float  # observed win frequency
    mean_pred: float  # mean predicted win-prob
    bins: List[Tuple[float, float, int]]  # (mean_pred, observed_freq, count) per occupied bin


def collect_samples(
    advisor_factory,
    opponent_factory=WeightedRandomPlayer,
    n_games: int = 40,
    rules: RulesConfig = COLONIST_1V1,
    seed: int = 0,
) -> List[Sample]:
    """Play ``n_games`` of advisor vs opponent (alternating colours) and return every
    ``(predicted win-prob, outcome)`` pair the advisor produced. ``advisor_factory``
    must build an :class:`AdvisorPlayer` (it reads ``.predictions``)."""
    samples: List[Sample] = []
    for i in range(n_games):
        random.seed(seed + i)
        if i % 2 == 0:
            advisor = advisor_factory(Color.RED)
            players = [advisor, opponent_factory(Color.BLUE)]
        else:
            advisor = advisor_factory(Color.BLUE)
            players = [opponent_factory(Color.RED), advisor]

        winner = new_1v1_game(players, rules=rules, seed=seed + i).play()
        outcome = 1.0 if winner == advisor.color else 0.0
        samples.extend((p, outcome) for p in getattr(advisor, "predictions", []))
    return samples


def reliability(samples: List[Sample], n_bins: int = 10) -> CalibrationReport:
    """Score (prediction, outcome) pairs: Brier, log-loss, ECE + a reliability table."""
    n = len(samples)
    if n == 0:
        return CalibrationReport(0, 0.0, 0.0, 0.0, 0.0, 0.0, [])

    eps = 1e-15
    brier = sum((p - o) ** 2 for p, o in samples) / n
    log_loss = -sum(
        o * math.log(min(max(p, eps), 1 - eps)) + (1 - o) * math.log(min(max(1 - p, eps), 1 - eps))
        for p, o in samples
    ) / n
    base_rate = sum(o for _, o in samples) / n
    mean_pred = sum(p for p, _ in samples) / n

    bins: List[Tuple[float, float, int]] = []
    ece = 0.0
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        grp = [(p, o) for p, o in samples if (lo <= p < hi or (b == n_bins - 1 and p == hi))]
        if not grp:
            continue
        mp = sum(p for p, _ in grp) / len(grp)
        of = sum(o for _, o in grp) / len(grp)
        bins.append((mp, of, len(grp)))
        ece += len(grp) / n * abs(mp - of)

    return CalibrationReport(n, brier, log_loss, ece, base_rate, mean_pred, bins)
