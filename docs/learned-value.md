# Learned value function (Phase 5.1)

Phase 5's goal is Tier-3 learned play. The environment has **only numpy** (no torch /
sklearn / SB3 / gym, and installs here are fragile), so rather than deep RL we pursue the
same destination by the tractable route: a **learned value function used as the MCTS leaf
evaluator** (Approach D). This directly attacks the weakness the calibration study found —
truncated rollouts ended in a crude VP-lead heuristic, and full rollouts modelled our own
future play as the weak WeightedRandom policy. Deep RL / AlphaZero remain a later stretch
gated on a proper ML environment (see [advisor-calibration.md](advisor-calibration.md)).

## Method (numpy-only)

- **Features** (`catansolver/learn/features.py`) — an 18-dim vector from one player's
  perspective: mostly `me − opponent` differences (VP, settlements, cities, per-resource
  pip production, total production, longest-road length + bonus, knights + largest army,
  hand size, dev cards) plus `me_vp` / `max_vp` (game stage) and a to-move flag. A strict
  superset of the single-feature VP-lead heuristic it replaces.
- **Self-play data** (`selfplay.py`) — WeightedRandom games (the policy the rollouts use),
  each sampled mid-game state recorded from **both** perspectives so labels are balanced by
  construction. (Gotcha found + fixed: weak self-play to 15 VP runs **450–1600 actions**, so
  the tick cap had to be generous or nearly every game is discarded unfinished.)
- **Model** (`value_model.py`) — L2-regularised logistic regression fit by Newton/IRLS in
  numpy; standardised features; serialises to JSON; evaluates as one dot product (cheap
  enough per MCTS leaf).
- **Integration** — `_simulate` uses the model at the truncation point when provided;
  threaded through PIMC/ISMCTS and `AdvisorPlayer(value_model=...)`.

## Model quality

43,264 train / 15,268 val samples (disjoint games). **Held-out accuracy 0.765** at calling
the winner from a mid-game position (log-loss 0.486, Brier 0.162). The dominant coefficient
is `d_vp` (+4.0); the VP *component* features (cities/settlements/road/army) take negative
signs — expected collinearity, since `d_vp` already sums them — which is fine for a value
head where prediction, not interpretation, is the goal.

## Does it make the advisor stronger?

A/B at identical search settings (2 determinizations × 25 iters, `rollout_depth=10`),
value-model leaf vs VP-lead-heuristic leaf:

| Head-to-head | Record | Win% | 95% CI | Verdict |
|---|---|---|---|---|
| n = 40 | 26-14-0 | 65% | 50–78% | noisy subset |
| **n = 100 (authoritative)** | **58-41-1** | **58%** | **48–67%** | one-sided p≈0.04; **not** sig. two-sided |

vs the baselines (n=40), the value-leaf advisor keeps strong, significant margins: Random
**85%**, WeightedRandom **80%**, VictoryPoint **78%**.

**Honest read:** a *slight, directional* edge that does **not** clear 95% two-sided
significance at n=100. The encouraging 65% from the small run was largely sampling noise
(the 100-game run uses the same seed, so it supersedes rather than adds to it). Harnesses:
[train_value.py](../scripts/train_value.py), [evaluate_value.py](../scripts/evaluate_value.py),
[value_h2h.py](../scripts/value_h2h.py); logs [value-eval.log](value-eval.log),
[value-h2h.log](value-h2h.log).

At `rollout_depth=10` the value barely helps — because ten ticks of WeightedRandom rollout
do most of the evaluation *before* the value is consulted. That diagnosis pointed to the
real experiment:

## The real win: truncate to depth 0 (Phase 5.1e)

Drop the rollout entirely (`rollout_depth=0`) so the **value model alone** evaluates each
leaf. Timing (2 det × 25 iters, same position): **37 ms/decision vs 141 ms** for
heuristic@d10 — a **3.8× speedup** (depths 2–10 barely differ; only removing the rollout
wins, since per-iteration overhead dominates a few rollout ticks).

Strength A/B (60 games each):

| Matchup | Record | Win% | 95% CI | |
|---|---|---|---|---|
| value@d0 (equal iters) vs heuristic@d10 | 30-29-1 | 50% | 38–62% | **tie — at 3.8× the speed** |
| value@d0, ~time-matched (×90 iters) vs heuristic@d10 | 38-20-2 | **63%** | 51–74% | **significant** |
| value@d0 vs WeightedRandom (sanity) | 43-15-2 | 72% | 59–81% | significant |

**This meets the Phase-5 exit.** At equal search the pure-value leaf *matches* the
heuristic-rollout advisor while being ~4× faster; spend that speed on more iterations and it
**significantly beats** it (63%). The recommended config with a value model is therefore
`rollout_depth=0` + as many iterations as the time budget allows.

## How much does pure extra search buy? (value@d0)

Because value@d0 is ~4× faster, more iterations are cheap. 36 games/matchup, value@d0 at a
default (2×25) vs a 12× budget (2×300):

| Matchup | Record | Win% | 95% CI |
|---|---|---|---|
| default vs VictoryPoint | 27-7-2 | 75% | 59–86% (sig) |
| **big (12× search) vs VictoryPoint** | 32-4-0 | **89%** | 75–96% (sig) |
| big vs default | 23-12-1 | 64% | 48–78% (one-sided p≈0.03) |

More search clearly helps — **+14 pts vs VictoryPoint (75 → 89%)** and a ~64% head-to-head
edge (≈ +100 internal Elo). The advisor is **not saturated** at the small default settings;
there is real, cheap headroom from compute alone (which value@d0 unlocks). Caveats: this is
still *dominance over weak bots* (doesn't establish human level), and returns will diminish —
the jump to human-competitive play still needs the bigger levers below.

Remaining levers for a bigger jump: a **nonlinear** value (GBT / small net — need libs absent
here) and a **stronger data-generation policy** than WeightedRandom. Harness:
[scripts/evaluate_search_scaling.py](../scripts/evaluate_search_scaling.py),
log [search-scaling.log](search-scaling.log).

## What this banks

The full pipeline — feature extractor, self-play data generator, numpy value model, and the
`value_model`-as-leaf-eval integration in PIMC/ISMCTS — is exactly what a future deep
value/policy net would plug into. So even as a marginal strength result, Phase 5.1
**de-risks and scaffolds** the deep-learning stretch rather than being a dead end.
