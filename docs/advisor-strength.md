# Tier-2 advisor strength (Phase 3.5 + follow-ups)

Does the turn advisor actually play *better* than the reference bots? This is the
Phase-3 exit criterion: beat random / heuristic / search baselines by a statistically
significant win-rate margin.

## Method

- **Player.** The advisor ([catansolver/advisor/pimc.py](../catansolver/advisor/pimc.py))
  wrapped as a Catanatron player ([catansolver/eval/arena.py](../catansolver/eval/arena.py),
  `AdvisorPlayer`). Each non-forced **PLAY_TURN** and **MOVE_ROBBER** decision is chosen
  by the advisor: sample determinizations of the opponent's hidden dev cards from the
  belief, search each (PIMC + UCT, or ISMCTS), play the argmax. Forced moves return
  directly; initial-build placement falls back to a fast WeightedRandom policy (it's the
  opening solver's domain). DISCARD is a single forced action in Catanatron, so it needs
  no search.
- **Settings.** 2 determinizations × 25 UCT iterations, `rollout_depth=10` (truncated
  rollouts finished by the VP-lead leaf heuristic). Deliberately modest so a full sweep
  runs in minutes; strength rises with more iterations.
- **Matches.** 40 games per opponent, **alternating seat + colour each game** so the
  advisor and baseline share first-move and board luck evenly. Full Colonist 1v1 ruleset
  (15 VP, discard 9, friendly robber). Win-rate with a Wilson 95% interval;
  "significant" = Wilson lower bound clears 50%. Games run across 6 processes.
- **Reproduce:** `.venv\Scripts\python.exe scripts\evaluate_advisor.py 40 2 25 10 pimc 6`
  (raw logs: [advisor-eval-final.log](advisor-eval-final.log),
  [advisor-eval-ismcts.log](advisor-eval-ismcts.log)).

## Results (PIMC, current best — with advisor-driven robber)

| Opponent | Advisor W-L-D | Win% | 95% CI | Significant |
|---|---|---|---|---|
| `RandomPlayer` | 34-6-0 | **85%** | 71–93% | ✅ |
| `WeightedRandomPlayer` (heuristic) | 35-5-0 | **88%** | 74–95% | ✅ |
| `VictoryPointPlayer` (search) | 31-9-0 | **78%** | 62–88% | ✅ |

All three lower bounds clear 50% — **the Phase-3 exit criterion is met**, and the margin
shrinks as the opponent strengthens (the right sanity check).

## Round-robin tournament + Elo (Phase 4.1)

Putting the whole field on one scale (Bradley-Terry/Elo MLE, mean anchored to 1500),
30 games per pair, full ruleset:

| Rank | Entrant | Elo | W-L-D | Win% |
|---|---|---|---|---|
| 1 | **Advisor (PIMC)** | **1701** | 74-16-0 | 82% |
| 2 | WeightedRandom (heuristic) | 1464 | 38-48-4 | 44% |
| 3 | VictoryPoint (search) | 1454 | 37-50-3 | 43% |
| 4 | Random | 1381 | 25-60-5 | 31% |

The advisor leads by **~240 Elo** (≈80% expected score) over the next bot, and the two
built-in bots are statistically tied (1464 vs 1454) — the same WeightedRandom ≈ VictoryPoint
result seen in the opening study. Harness: [scripts/tournament.py](../scripts/tournament.py),
log [tournament.log](tournament.log).

## Follow-up findings

### Advisor-driven robber placement helps (controlled A/B)

Capturing the `MOVE_ROBBER` sub-prompt in the state round-trip lets the advisor *search*
robber placement instead of falling back to WeightedRandom. Same seed, same settings —
only the robber code differs:

| Opponent | Robber = fallback | Robber = advisor | Δ |
|---|---|---|---|
| Random | 82% | **85%** | +3 |
| WeightedRandom | 80% | **88%** | +8 |
| VictoryPoint | 75% | **78%** | +3 |

Every matchup improved (clearest vs the heuristic bot). Small-sample (n=40), so directional
rather than conclusive — but a consistent, plausible gain, since robber placement is one of
the few genuinely strategic 1v1 decisions.

### ISMCTS ≈ PIMC (matched 50-iteration budget, 40 games)

| Opponent | PIMC | ISMCTS |
|---|---|---|
| Random | 82% | 80% |
| WeightedRandom | 80% | 82% |
| VictoryPoint | 75% | 75% |

Statistically indistinguishable. This **confirms the §6.4 expectation**: ISMCTS fixes
*strategy fusion*, which only bites when hidden information drives decisions — and in 1v1
the sole hidden information is dev cards. So PIMC stays the default; ISMCTS
(`recommend_actions_ismcts`) is kept for richer-hidden-info settings. (Note: the head-to-head
predates the robber capture, so both used the fallback — a fair like-for-like.)

### Parallelism

`play_match(..., workers=N)` runs games across processes (`ProcessPoolExecutor`, BLAS/OMP
thread caps set before numpy import). ~3× wall-clock on 8 cores — what makes 40-game sweeps
and the A/B above affordable, and what a future interactive UI will need.

## Reading the numbers honestly

- **Relative, not absolute.** Opponents are the built-in bots; beating them ≠ beating a strong
  human (see [heuristic-accuracy.md](heuristic-accuracy.md) for why absolute win-% is shelved
  until a learned value head exists).
- **Modest search settings** (50 iterations over a ~16-wide root) — these are a floor. More
  iterations, explicit chance nodes, and a learned leaf evaluator are open headroom.
- **n=40** keeps CIs wide (~±13 pts); the VP matchup especially would tighten with more games.
