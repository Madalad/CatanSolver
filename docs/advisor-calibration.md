# Advisor win-probability calibration (Phase 4.2)

The advisor attaches a P(win) to the move it plays. Is that number trustworthy as a
*probability*? We measured it: play the advisor vs its rollout-level opponent
(WeightedRandom — self-consistent, since that's the policy its rollouts assume), record
each chosen move's predicted win-prob, label it with the eventual outcome, and score the
pairs. Harness: [scripts/calibrate_advisor.py](../scripts/calibrate_advisor.py)
(`catansolver/eval/calibration.py`), log [calibration.log](calibration.log).

## Result (40 games, 5,193 predictions, advisor 2×25 depth 10)

| Metric | Value | Reference |
|---|---|---|
| Brier | **0.097** | base-rate predictor 0.143 → **Brier skill +32%** |
| Log-loss | 0.303 | — |
| ECE | **0.100** | 0 = perfect |
| Mean prediction | 0.727 | actual win rate **0.827** |

**Reliability table** (predicted vs observed frequency per bin):

| predicted | observed | count |
|---|---|---|
| 0.04 | 0.07 | 214 |
| 0.15 | 0.16 | 148 |
| 0.25 | 0.29 | 185 |
| 0.35 | 0.47 | 212 |
| 0.45 | 0.72 | 162 |
| 0.53 | 0.83 | 691 |
| 0.64 | 0.81 | 444 |
| 0.75 | 0.89 | 496 |
| 0.85 | 0.96 | 423 |
| 0.98 | 0.99 | 2218 |

## Reading it

- **The probabilities are informative** — a +32% Brier skill score over predicting the
  base rate, and the reliability curve is **monotonic** (higher prediction ⇒ higher
  observed win rate, always). So as a *ranking* signal it is sound.
- **But it is systematically under-confident**, worst in the mid-range: a predicted
  "coin-flip" (0.45–0.53) actually wins **72–83%**. Mean prediction 0.73 trails the true
  0.83. The well-calibrated tails (≤0.25 and the large 0.98 bin) are mostly clearly-lost
  / clearly-won positions.
- **Why:** the rollouts model the advisor's *own* future moves as the weak WeightedRandom
  policy, so the search underestimates how well it will actually go on to play. This
  under-confidence dominates the opposite (winner's-curse) bias from picking an argmax.

## Recalibration (Phase 4.2b — done)

Because the curve is monotonic, an **isotonic regression** map (PAVA;
`catansolver/eval/recalibrate.py`, no sklearn dependency) is all it takes. Fit on a
TRAIN split of games and evaluated on a **disjoint TEST split** (so the gain is honest,
not in-sample):

| | Brier | ECE | mean pred | base rate |
|---|---|---|---|---|
| raw (test) | 0.101 | 0.115 | 0.730 | 0.844 |
| **recalibrated** | **0.083** | **0.047** | **0.847** | 0.844 |

**ECE more than halved (0.115 → 0.047)**, Brier −17%, and mean prediction snaps onto the
actual win rate. The map (e.g. raw 0.45→0.62, 0.50→0.89) is saved to
[recalibration.json](recalibration.json) (20 knots) for the API/UI to apply at display
time; fit harness [scripts/fit_recalibration.py](../scripts/fit_recalibration.py).

Two caveats keep it honest: (1) it is calibrated against the **WeightedRandom-level
opponent** the samples came from, not a strong human; (2) a stronger rollout/leaf policy
(Phase 5 learned value) attacks the root cause — the weak self-model in rollouts —
directly, and is the better long-term fix.
