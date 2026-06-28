# Opening win-probability (Phase 5.2)

Phase 4 shelved the opening win-% because the only thing to calibrate it against was weak
bots (saturated, misleading). With the learned value model (Phase 5.1) and the calibration
machinery (Phase 4.2/4.2b), we can now produce a **trustworthy, honestly-labelled** number.

## How it works

`opening_win_prob(request, placements, value_model, calibrator)`
([catansolver/placement/opening_value.py](../catansolver/placement/opening_value.py)):
drive the snake draft to the user's decision → play the candidate placement(s) → **finish
the draft** with a fast policy → evaluate the resulting first-PLAY position with the value
model, averaged over several draft completions and passed through the opening calibrator.
One value eval per completion (no game played out), so it's far cheaper than the old
full-rollout estimate.

## Is it trustworthy? (calibration study, 5.2a)

Evaluate the value model at the post-draft position (both colours) and label by the eventual
winner, on a TRAIN and a disjoint TEST split of games
([scripts/calibrate_opening.py](../scripts/calibrate_opening.py)):

| | Brier | ECE | mean pred | base rate |
|---|---|---|---|---|
| raw (test) | 0.197 | 0.093 | 0.500 | 0.500 |
| **recalibrated** | **0.188** | **0.040** | 0.500 | 0.500 |

The base rate is a perfect **0.50** (symmetric openings), and the raw value model is
**under-confident** at openings — its reliability curve is steeper than the diagonal, i.e.
the opening matters *more* than the model thinks (predicted 0.55 → observed 0.63; predicted
0.45 → 0.37). It's monotonic, so isotonic recalibration fixes it: **held-out ECE 0.093 →
0.040**. The opening calibrator is saved to
[docs/opening_calibrator.json](opening_calibrator.json).

(Why under-confident here vs over-/under- elsewhere: the opening is a hair earlier than the
value model's training window — it samples from `min_tick=10`, the first PLAY state is ~tick 8
— so it slightly under-reacts to opening structure. Retraining with opening states included
would help the raw model; recalibration already covers it.)

## What it looks like

FIRST seat, an empty board, calibrated win-% (`scripts` demo):

| Placement | heuristic | raw | **calibrated** |
|---|---|---|---|
| best heuristic spot | 0.542 | 72.5% | **84.9%** |
| middle | 0.319 | 58.3% | 64.0% |
| worst of top-30 | 0.252 | 57.0% | 61.1% |

Monotonic with opening quality and sensibly spread — "go first on the best spot and you're a
strong favourite."

## Advisor-level recalibration (5.2c)

The 5.2a calibrator above is fit vs a *baseline* (WeightedRandom) opponent. For the UI we
refit it vs an **equal-strength** opponent — value@d0 self-play, the advisor's own playing
level — so the label can honestly read "vs an equal-strength bot." A parallelised collector
([`collect_opening_samples_parallel`](../catansolver/learn/selfplay.py)) made this ~12 min
for 344 samples instead of ~1 hr; [scripts/calibrate_opening_advisor.py](../scripts/calibrate_opening_advisor.py),
log [opening-cal-advisor.log](opening-cal-advisor.log).

| | Brier | ECE | mean pred | base rate |
|---|---|---|---|---|
| raw (test) | 0.2105 | 0.0794 | 0.500 | 0.500 |
| **recalibrated** | **0.2065** | **0.0554** | 0.500 | 0.500 |

**The headline finding: openings are near coin-flips under equal play.** Base rate and
mean-pred are both exactly **0.500**, and raw Brier is **0.21** — only marginally better than
the 0.25 of always saying "50%". When both seats play at advisor level, who placed where
barely predicts the winner. This is *low resolution*, not a compressed mapping: the
raw→calibrated curve barely moved vs the baseline calibrator (within a few points, and even
slightly sharper at the tails). The opening advantage structure is roughly opponent-
independent, but its *magnitude* is small — a balanced opening really is ≈50/50 against an
equal opponent. Calibrator saved to [opening_calibrator_advisor.json](opening_calibrator_advisor.json)
(the one the API loads).

### Board bank (Approach B): measured and shelved

We prototyped a precomputed "gold-standard" board bank — accurate advisor-self-play win-% for
each board's top candidates ([scripts/board_bank_prototype.py](../scripts/board_bank_prototype.py)).
Measured cost: **3.7 hr/board** (6 workers; 6,750 games/board at 11.9 s/game value@d0) →
**6.2 days for a 40-board bank**. Shelved: the calibrator already gives a win-% for *any*
board instantly, and since openings are ~50/50 there's little spread for the bank's extra
precision to resolve. Revisit only for a curated "ranked openings" feature (5–10 boards
overnight, not 40).

## Heuristic opening-gap model — supersedes the value model for openings (5.2d)

A leverage study ([scripts/opening_leverage.py](../scripts/opening_leverage.py),
[opening-leverage.log](opening-leverage.log)) found that the player who drafts the stronger
opening (by the production heuristic) wins **~70–80% at every skill tier** (random, simple,
search, value@d0) — opening advantage is large and roughly **skill-independent**, not the
coin-flip the value model's low resolution implied. That pointed at a better opening
evaluator: map the **heuristic opening-strength gap** (my node-score sum − opponent's)
straight to a win-%.

Head-to-head on held-out self-play, the gap predictor **beats the value model + calibrator**
([scripts/calibrate_opening_heuristic.py](../scripts/calibrate_opening_heuristic.py),
[opening-heuristic-cal.log](opening-heuristic-cal.log)):

| predictor | Brier (WR) | Brier (equal-strength) |
|---|---|---|
| value model + calibrator | 0.195 | 0.193 |
| **heuristic gap → win%** | **0.155** | **0.166** |

Lower Brier at equal ECE = better *resolution*. Why the narrow heuristic wins **at the
opening**: the value model is an 18-feature evaluator trained on *mid-game* states and
under-reacts to raw production; `node_score` *is* the production signal, purpose-built for
openings. (Mid-game the value model is still the better evaluator — Phase 5.1 — so it stays
the MCTS leaf eval; only the *opening* win-% switched.)

It must be the **gap**, not the absolute heuristic value: win-% is relative, and the same
opening is dominant on a poor board and mediocre on a rich one — differencing against the
opponent cancels the board. The fit (a 1-feature logistic,
[opening_gap_model.json](opening_gap_model.json), 2958 samples) is steep and tier-stable:
gap +0.25 → **85%**, −0.25 → 15%, ±0.50 → 97%/3%. Because the draft policy is WeightedRandom
at fit time, at the equal-strength tier *and* at inference (`rollout_policy`), the map is the
same regardless of opponent skill — consistent with the skill-independence finding.
`opening_win_prob_gap` ([opening_value.py](../catansolver/placement/opening_value.py)) is a
drop-in for `opening_win_prob`, and the API now loads the gap model.

## The honest label

The UI shows the win-% as **"vs an equal-strength bot"** — calibrated against the advisor's
own level, *not* a strong human. It's a real upgrade over the shelved version (saturated,
unvalidated, ~96% where humans win ~44%); a "vs a strong human" version still needs either a
human-level bot (deep-RL stretch) or human game data (a Phase-6 byproduct), and as noted in
[heuristic-accuracy.md](heuristic-accuracy.md), anchoring to human aggregates can't fix the
per-board slope.

**Surfaced (5.2c/d):** the board UI sorts opening recommendations by the gap-based win-%
(score as a secondary number) and the practice feedback shows "your opening ≈X% · model's
line ≈Y%," both labelled "vs an equal-strength bot." Because the win-% is now derived from
the same production heuristic that ranks the candidates, the displayed order and the win-%
agree (the earlier value-model inversions are gone).
