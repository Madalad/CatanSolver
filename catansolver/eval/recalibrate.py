"""Phase 4.2b — recalibrate the advisor's win-prob.

The calibration study ([docs/advisor-calibration.md](../../docs/advisor-calibration.md))
found the raw P(win) is *monotonic but systematically under-confident*. A monotone map
is therefore all that's needed to turn it into a calibrated probability — so we fit
**isotonic regression** (the non-parametric, monotonicity-preserving choice; Platt/logistic
would impose a sigmoid the data doesn't have) on the (prediction, outcome) pairs via the
Pool Adjacent Violators Algorithm.

The fitted :class:`Calibrator` maps a raw value to a calibrated one by piecewise-linear
interpolation between the PAVA blocks, and serialises to JSON so the API/UI can apply it
at display time. It is calibrated *against the opponent the samples were collected on*
(WeightedRandom) — not a strong human; a learned value head (Phase 5) is the deeper fix.
"""
from __future__ import annotations

import bisect
import json
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

Sample = Tuple[float, float]  # (raw prediction, outcome/observed-frequency)


def _clip01(v: float) -> float:
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


@dataclass
class Calibrator:
    """Monotone raw→calibrated map, stored as ``(x, y)`` knots (sorted by x)."""

    knots: List[Tuple[float, float]]

    def __call__(self, raw: float) -> float:
        xs = [k[0] for k in self.knots]
        if raw <= xs[0]:
            return self.knots[0][1]
        if raw >= xs[-1]:
            return self.knots[-1][1]
        i = bisect.bisect_right(xs, raw)
        (x0, y0), (x1, y1) = self.knots[i - 1], self.knots[i]
        t = (raw - x0) / (x1 - x0) if x1 > x0 else 0.0
        return _clip01(y0 + t * (y1 - y0))

    def to_dict(self) -> dict:
        return {"knots": [[x, y] for x, y in self.knots]}

    @classmethod
    def from_dict(cls, d: dict) -> "Calibrator":
        return cls([(float(x), float(y)) for x, y in d["knots"]])

    def save(self, path) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path) -> "Calibrator":
        with open(path) as f:
            return cls.from_dict(json.load(f))


def fit_isotonic(samples: Sequence[Sample], weights: Optional[Sequence[float]] = None) -> Calibrator:
    """Fit isotonic regression (PAVA) on ``(x, y)`` pairs — raw ``(prediction, outcome)``
    samples, or a binned reliability table ``(mean_pred, observed_freq)`` with ``weights``
    = bin counts. Returns a monotone :class:`Calibrator`."""
    if not samples:
        return Calibrator([(0.0, 0.0), (1.0, 1.0)])
    w = list(weights) if weights is not None else [1.0] * len(samples)
    data = sorted(zip(samples, w), key=lambda t: t[0][0])

    # PAVA: each block holds (mean y, total weight, weighted-sum of x)
    vals: List[float] = []
    wts: List[float] = []
    xws: List[float] = []
    for (x, y), wi in data:
        vals.append(y)
        wts.append(wi)
        xws.append(x * wi)
        while len(vals) >= 2 and vals[-2] > vals[-1]:  # pool adjacent violators
            tw = wts[-2] + wts[-1]
            vals[-2:] = [(vals[-2] * wts[-2] + vals[-1] * wts[-1]) / tw]
            xws[-2:] = [xws[-2] + xws[-1]]
            wts[-2:] = [tw]

    knots = [(xws[i] / wts[i], _clip01(vals[i])) for i in range(len(vals))]
    if len(knots) == 1:  # degenerate (one block): a flat map still needs two points
        knots = [(0.0, knots[0][1]), (1.0, knots[0][1])]
    return Calibrator(_compress_knots(knots))


def _compress_knots(knots: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Collapse each maximal run of equal-y knots to its endpoints. Exact for the
    piecewise-linear map (a flat run needs only its first + last point), and turns the
    thousands of 0/1 knots PAVA leaves at the tails into a handful."""
    out: List[Tuple[float, float]] = []
    i, n = 0, len(knots)
    while i < n:
        j = i
        while j + 1 < n and knots[j + 1][1] == knots[i][1]:
            j += 1
        out.append(knots[i])
        if j > i:
            out.append(knots[j])
        i = j + 1
    return out
