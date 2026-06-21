# Opening-placement heuristic: accuracy study

> **TL;DR.** Across 400 opening spots on 40 boards (200 rollouts each, ~96k games), the
> production-weighted heuristic tracks Monte-Carlo win probability **strongly**:
> pooled Pearson **0.885**, within-board Spearman **0.879**, and win-prob rises
> monotonically through every heuristic quintile (25% → 74%). It picks the
> best-sampled opener **75%** of the time with a mean regret of just **1.4 win-%
> points**. The residual misses (≈11% of spot-pairs mis-ordered, worst board 16 pts)
> come from exactly what it ignores — expansion room, blocking, and road topology.
>
> Run: 40 boards × 10 spots × 200 rollouts = 400 observations / ~96k games, 96 min.
> Raw data: [`heuristic-eval-data.csv`](heuristic-eval-data.csv) · summary: [`heuristic-eval-stats.json`](heuristic-eval-stats.json) · script: [`../scripts/heuristic_eval.py`](../scripts/heuristic_eval.py)

## 1. What the heuristic computes

The opening optimiser ranks candidate settlement spots with a single fast score,
[`node_score`](../catansolver/placement/heuristic.py). For a node it is:

```
score = Σ_resource  weight[resource] · P(resource)          # weighted production rate
      + 0.04 · (number of distinct resources at the node)    # diversity bonus
      + port bonus                                           # 3:1 / 2:1 synergy
```

**Production term.** Catanatron precomputes `node_production[node]` = a map from
resource to the **expected fraction of rolls** that pay that node (summing the
dice probability — "pips"/36 — of each adjacent hex). The heuristic multiplies
each resource's rate by a weight and sums. So a spot on `6-wheat / 8-ore / 5-wood`
scores its three pip-probabilities, weighted by resource.

**Resource weights** (`RESOURCE_WEIGHTS`): wheat 1.30, ore 1.20, brick 1.05,
wood 1.00, sheep 0.90. *Justification:* the Colonist 1v1 game is to **15 VP**, where
cities (2 wheat + 3 ore) and development cards (wheat + ore + sheep) dominate the
late game — so wheat and ore are weighted up. Wood and brick retain near-baseline
value (they drive early expansion and Longest Road); sheep is nudged down as the
least independently useful good. These are **hand-set**, slated for tuning in Phase 4.

**Diversity bonus** (`+0.04` per distinct resource). A spot touching three
different resources is more robust than one doubled on a single good: it keeps you
building through more dice outcomes and reduces reliance on trade. The bonus is
small and deliberately secondary to raw production.

**Port bonus.** A generic 3:1 adds `+0.03`; a 2:1 port adds `+0.06` plus a
`0.5 · P(that resource)` kicker — a specific port is only valuable if you actually
produce its resource. Ports are a minor tertiary term.

**What it deliberately ignores (Tier-1 scope).** The heuristic does *not* model the
initial **road** direction beyond pointing it at the best neighbour
([`best_initial_road`](../catansolver/placement/heuristic.py)), nor the **opponent**
(blocking / what spots they are denied), nor longer-range **expansion** topology,
nor **hidden information**. It is a static, per-node production proxy — fast enough
to rank all 54 spots instantly, with Monte-Carlo rollouts layered on top
(`n_rollouts > 0`) when the user wants true win-probabilities.

## 2. Method

We test the claim the heuristic implicitly makes: **a higher `node_score` means a
higher probability of winning.**

- **Scenario.** FIRST seat (player going first), the cleanest case: a single
  settlement on an empty board, so heuristic↔win-prob is a direct 1-to-1 mapping
  with no pair-synergy confound.
- **Boards.** 40 independent random standard boards (`random.seed(1000+i)`).
- **Candidate spots.** On each board we score all 54 legal opening nodes, rank
  them by `node_score`, and sample **10 spots evenly spaced across that ranking**
  (best, …, worst) so each board spans the full quality range.
- **Win probability.** Each spot is fixed as the first player's opening (plus its
  heuristic best road); we then play **200 games to completion**. The remainder of
  the snake draft and all subsequent play use Catanatron's **`WeightedRandomPlayer`**
  for *both* players. Win rate over the 200 games is the estimate (Wilson 95% CI).
- **Why `WeightedRandomPlayer`.** It runs ~95 ms/game (vs ~700 ms for the search
  player), making 96,000 games feasible, and it biases toward reasonable moves so
  the signal is cleaner than uniform-random play. *Caveat:* absolute win-rates are
  relative to this opponent; a stronger opponent would likely **compress** the
  spread between spots. Our conclusions therefore lean on **rank agreement**, which
  is far more robust to opponent strength than absolute win-rate gaps.

**Metrics.**
- *Pooled correlation* (Pearson + Spearman) between `node_score` and win-prob over
  all 400 observations — does the score track win-prob globally?
- *Within-board Spearman* (mean over boards) — on a single board, does the score
  rank spots in the right order? This is what the advisor actually relies on.
- *Top-1 hit rate & regret* — is the heuristic's #1 spot actually the
  highest-win-prob sampled spot, and if not, how much win-prob is left on the table?
- *Monotonicity* — mean win-prob across heuristic quintiles.

## 3. Results

### Headline correlation

| Metric | Value | Reading |
|---|---|---|
| Pooled **Pearson** (heuristic vs win-prob) | **0.885** (95% CI 0.862–0.905) | strong linear agreement |
| Pooled **Spearman** | **0.882** | strong rank agreement globally |
| **Within-board Spearman** (mean ± sd) | **0.879 ± 0.097** | on a single board, spots are ranked in nearly the right order |
| Discordant spot-pairs (within board) | **11.4%** (206 / 1800) | ~1 in 9 pairs mis-ordered, mostly near-ties |

### Monotonicity — win-prob by heuristic quintile

Spots pooled across all boards, split into five equal heuristic bins:

| Heuristic quintile (mean score) | Mean win-prob |
|---|---|
| Q1 — 0.091 | **24.9%** |
| Q2 — 0.183 | **36.9%** |
| Q3 — 0.253 | **47.5%** |
| Q4 — 0.333 | **58.9%** |
| Q5 — 0.470 | **73.5%** |

Strictly monotone, ~12 win-% points per quintile, spanning a **49-point** spread
from worst to best — the heuristic separates good and bad openers cleanly, and the
relationship is close to linear (consistent with Pearson ≈ Spearman).

### Top-pick quality

| Metric | Value |
|---|---|
| Heuristic's #1 spot **is** the best-sampled spot | **75%** of boards |
| Mean **regret** (win-prob lost vs best sampled) | **1.4 pts** |
| Boards with regret > 5 pts | **4 / 40** |
| Worst single board (regret) | **16 pts** (board 25) |
| Observed win-prob range | 4.5% – 93.5% |

So even when the top heuristic pick is *not* the single best spot, it is almost
always a near-tie (mean 1.4 pts) — the optimiser's instant ranking lands on a
near-optimal opener the large majority of the time.

## 4. Interpretation & recommendations

**The heuristic is a strong proxy for opening win probability.** A static,
production-weighted per-node score with no search reproduces Monte-Carlo win-prob
ordering at Spearman ≈ 0.88 and never inverts the quintile trend. This validates the
two-tier design: use the heuristic for an **instant, near-optimal ranking**
(`n_rollouts = 0`), and layer rollouts on top only when the user wants calibrated
win-% or to settle close calls. The default advisor view already gives openers
within ~1.4 win-% points of the best.

**Where it misses, and why.** The ~11% discordant pairs and the handful of
high-regret boards (16 pts worst) are concentrated where the heuristic's blind
spots bite — it scores only *production + diversity + ports*, ignoring:
- **Expansion room** — open adjacent vertices / how easily you reach a 2nd and 3rd
  settlement. A slightly lower-pip spot with two strong open expansions can out-win
  a higher-pip dead-end.
- **Blocking** — denying the opponent a premium spot has value the static score
  can't see (it never looks at the opponent).
- **Road / topology** — the initial road is only pointed at the best neighbour; the
  spot's score itself is road-agnostic.

These are precisely the features flagged as out-of-scope for Tier 1, so the misses
are expected rather than bugs.

**Recommendations.**
1. **Keep the heuristic as the ranker / pre-filter** — at Spearman 0.88 it is more
   than good enough to prune to a top-k for rollouts, and to power the instant
   advisor and the practice "model answer".
2. **Phase-4 weight tuning (Optuna) against this very win-prob signal** is well
   motivated: the data here is a ready-made objective. Tuning the five resource
   weights + bonuses should lift within-board Spearman and, more importantly, shrink
   the high-regret tail.
3. **The biggest accuracy gains will come from new features, not re-weighting** —
   adding an *expansion-potential* term and a light *blocking* term targets the exact
   cases that produce the worst regrets. Worth a follow-up study isolating the
   high-regret boards (e.g. board 25) to confirm.
4. **For the practice tool**, note that the heuristic "optimal" can occasionally
   disagree with rollouts by up to ~16 pts on adversarial boards; the existing
   tolerance band already cushions this, but it's a reason not to treat the model
   answer as ground truth.

### Caveats
- **Opponent strength.** Win-rates are vs `WeightedRandomPlayer` (chosen for speed —
  ~95 ms/game). A stronger opponent would likely **compress** the win-prob spread
  between spots; rank-based conclusions (Spearman, monotonicity) are robust to this,
  absolute gaps less so.
- **Scope.** §3 covers the FIRST seat (single settlement). The SECOND seat
  (`pair_score`) and FIRST_FINAL were subsequently calibrated too — see §5; SECOND's
  pair heuristic validates well, FIRST_FINAL is unbiased but noisier.
- **Sampling.** 10 heuristic-spaced spots per board (not all 54) — chosen to span the
  quality range for correlation; regret is measured against the best *sampled* spot.
- **Weights are hand-set**, so this is a baseline; it can only improve with tuning.

## 5. From heuristic to a win-% (UI display)

Because the heuristic↔win-prob relationship is near-linear in log-odds, a
**2-parameter logistic** `P(win) = sigmoid(a + b·heuristic)`, fit by binomial MLE,
turns the raw score into an interpretable, instant win-% for the UI — no rollouts
needed. It is calibrated **per seat** (the SECOND seat scores a *pair*, so its scale
differs) and against the same `WeightedRandomPlayer` baseline the rollout mode now
uses, so the instant estimate and the rollout number are the same quantity at
different fidelities. (Switching the rollout opponent to `WeightedRandomPlayer` also
made the win-% mode ~7× faster.)

| Seat | `a` | `b` | 50% at heuristic | calibration (pred vs obs) | scatter |
|---|---|---|---|---|---|
| FIRST | −1.602 | 5.776 | 0.277 | excellent (Brier 0.008) | low (Pearson 0.89) |
| FIRST_FINAL | −1.580 | 5.317 | 0.297 | unbiased mean (27→27, 50→51, 68→66%) | **high** (Pearson 0.44, Brier 0.106) |
| SECOND (pair) | −3.708 | 5.759 | 0.644 | excellent (14→12, 71→73, 91→90%) | moderate (Pearson 0.86, Brier 0.033) |

**Reading it.** All three are *unbiased* — the predicted win-% matches the observed
average across the range. They differ in **precision**:
- **FIRST / SECOND** are tight: the displayed estimate is close to the board-specific
  truth.
- **FIRST_FINAL is unbiased but coarse** — by the fourth pick the result is mostly
  determined by the three settlements already down, so a single spot's heuristic
  explains less of the variance. The instant estimate is still the best quick guess,
  but the rollout figure matters more here.

**How it's shown.** With rollouts off, each spot reads `est. win ~70% (vs baseline)`
(rounded to 5%, tooltip explaining it's a board-agnostic model estimate); with
rollouts on, it shows the exact `win 73% [70–85]` for that board. Uncalibrated seats
would fall back to the raw heuristic. Refit any time with
[`scripts/calibrate_winprob.py`](../scripts/calibrate_winprob.py) →
[`winprob-coeffs.json`](winprob-coeffs.json).

**Caveat (unchanged).** The win-% is *vs the baseline bot*, not a strong human — it is
a calibrated relative measure, not a real-match probability. A stronger opponent would
compress the spread.

## 6. Update (2026-06-19): win-% shelved; UI shows the score

We tried to make the win-% realistic and concluded we can't yet — so the **UI now
displays the strength score, not a probability.** Two findings drove this:

**(a) Real human data.** TwoSheep.io's 1v1 season (our exact ruleset: 15 VP, 9-card,
Friendly Robber) reports **first player 56% / second 44%** over hundreds of games
between strong players. Our bot-calibrated curves, by contrast, read **~81%** for a
strong first-player opening and **~96%** for a strong second-player pair — wildly
optimistic, because they're measured against a weak bot.

**(b) The stronger built-in opponent doesn't help.** We recalibrated everything
against `VictoryPointPlayer` (the strongest built-in, ~10× slower; parallelised, ~84k
games). The result was a **negative one — VP ≈ WeightedRandom**:

| seat | best-spot win% (WeightedRandom) | best-spot win% (VictoryPointPlayer) | strong humans |
|---|---|---|---|
| FIRST | 81% | 81% | 56% |
| FIRST_FINAL | 77% | 74% | 56% |
| SECOND | 96% | 96% | 44% |

The curves barely moved. **At sub-human skill the opening's resource advantage
dominates so completely that the opponent's mid-game play is almost irrelevant** — a
great opening wins ~96% against either bot, while strong humans hold it to 44%. That
entire gap is skill neither bot has.

**Consequences / decisions:**
- A win-% from either bot would mislead (96% where the truth is ~44%), so it is
  **removed from the UI**; recommendations show the heuristic **score** (a comparative
  ranking, which the study validates at Spearman ≈ 0.88).
- A marginal human anchor (56/44) can't rescue it: the underlying curve is unchanged,
  so anchoring SECOND still needs a −3.5-logit shift that collapses good pairs to ~16%.
- `WeightedRandomPlayer` is kept as the rollout policy — now *evidence-backed*: VP gives
  identical calibration for ~7× the cost.
- The win-prob machinery ([`winprob_model.py`](../catansolver/placement/winprob_model.py),
  `model_win_prob`, rollouts) is kept **dormant** in the backend.
- **The real fix is the Tier-2/3 agent**, whose value head *is* a calibrated win-prob —
  accurate win-% returns then, not by patching this heuristic.

Artifacts: VP run [`winprob-vp-coeffs.json`](winprob-vp-coeffs.json),
[`winprob-vp-data.csv`](winprob-vp-data.csv); script
[`scripts/calibrate_winprob_vp.py`](../scripts/calibrate_winprob_vp.py).
