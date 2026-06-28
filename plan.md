# Catan Solver — Project Plan & Specification

> A tool that takes a Settlers of Catan game state (Colonist.io **1v1** ruleset) and
> outputs the decision(s) that maximise the player's probability of winning from that point.

Status: **Planning / spec**. Last updated: 2026-06-14.

---

## 1. Locked decisions

These were settled up front and frame the rest of the plan.

| Decision | Choice | Notes |
|---|---|---|
| **Ruleset** | Colonist.io **1v1** | Classic base-game board, **15 VP to win**, **Friendly Robber**, **discard limit 9**. See §3. |
| **Input** | Interactive board UI (manual), Colonist.io later | The user builds the board (resource hexes + number tokens + ports) by clicking in a visual UI; the same state schema is the solver's API contract. Live Colonist capture is a later, decoupled phase. See §6.9. |
| **First deliverable (MVP)** | Placement optimizer **+ interactive board UI** | Headless solver core *plus* a visual, click-to-build board for input and on-board display of recommendations. |
| **Stack** | Python core + thin web frontend | Python (3.9.7 via Anaconda for now, 3.11+ later) solver/engine behind a **FastAPI** API; browser frontend (**SVG/Canvas**) for the interactive board. Python keeps the best engine/RL ecosystem; the browser is the natural fit for a hex board and seeds Phase 6. |
| **Player count** | 2 (1v1) only | 3–4 player support is explicitly out of scope for now. |
| **Expansions** | Base game only | No Seafarers / Cities & Knights. |

---

## 2. Objective & success criteria

**Goal.** Given a fully-specified 1v1 game state, return the best move (or move sequence for
the turn) plus an estimated **win probability** for the top candidates.

**What "optimal" means here.** 1v1 Catan is a **two-player, zero-sum, stochastic game with
imperfect information**. Because exactly one player wins, maximising my win probability is
identical to minimising my opponent's — a clean minimax objective. The theoretically correct
target is a Nash equilibrium in behaviour strategies; that is **intractable** to compute exactly
(see §5). So operationally we define optimal as:

> the action that maximises estimated P(win) against a specified opponent model, where P(win) is
> estimated by search + simulation.

The **opponent model is a first-class assumption**, not an afterthought — it defines what
"optimal" means in practice. We make it a configurable knob (random / heuristic / engine-bot /
self-play / belief-weighted) and report which model produced a given recommendation.

**Success criteria (by tier):**
- **Tier 1:** placement recommendations that beat naive pip-count picks in head-to-head simulation, with calibrated win-probability estimates.
- **Tier 2:** a turn advisor whose recommended actions achieve a measurably higher win rate than strong baseline bots (random, heuristic, and Catanatron's reference bots) in self-play tournaments.
- **Tier 3 (stretch):** a learned value/policy that improves Tier-2 strength and/or rollout speed.

---

## 3. Game specification — Colonist.io 1v1

This is the contract the engine must implement. Items marked **[1v1]** differ from standard
4-player base Catan; items marked **[verify]** are open questions to confirm (see §11).

### 3.1 Board
- **19 land hexes:** 4 forest (wood), 4 pasture (sheep), 4 field (wheat), 3 hills (brick), 3 mountains (ore), 1 desert.
- **18 number tokens** on the non-desert hexes: one `2`, one `12`, and two each of `3,4,5,6,8,9,10,11`. No `7` token. Robber starts on the desert.
- **54 vertices** (settlement/city spots) and **72 edges** (road spots).
- **9 ports:** 4 generic (3:1) and 5 specialised 2:1 (one per resource).
- Board is **randomised per game** (Colonist), so the solver must accept an **arbitrary legal layout**, never a hard-coded one.

### 3.2 Pieces, costs, victory points
- **Per player:** 5 settlements, 4 cities, 15 roads.
- **Build costs:**
  - Road = wood + brick
  - Settlement = wood + brick + wheat + sheep
  - City = 2 wheat + 3 ore (upgrades an existing settlement)
  - Dev card = ore + wheat + sheep
- **Victory points:** settlement = 1, city = 2, Longest Road (≥5 segments) = +2, Largest Army (≥3 knights played) = +2, each VP dev card = +1.
- **Win condition: first to 15 VP [1v1]** (checked on your own turn).

### 3.3 Development cards (standard 25-card deck)
14 Knights · 5 Victory Point · 2 Road Building · 2 Year of Plenty · 2 Monopoly.
At most one dev card played per turn; a Knight may be played before rolling; cards bought this
turn can't be played this turn; VP cards are hidden until they win the game.

### 3.4 Turn structure
1. (Optional) play one Knight before rolling.
2. **Roll 2d6.** On 2–6 / 8–12, every hex with that number produces for adjacent settlements (1) / cities (2), limited by the bank. On a **7**: robber phase.
3. **Trade:** with the bank 4:1, ports 3:1 / 2:1, and with the single opponent (negotiated). [verify] whether Colonist 1v1 allows player trades and on what terms.
4. **Build / buy:** roads, settlements, cities, dev cards (any order, any number affordable).
5. (Optional) play one dev card (if not already played a Knight pre-roll).

### 3.5 Robber & the 7 — the big [1v1] deltas
- **Discard limit = 9 [1v1].** You only discard on a 7 if you hold **≥10** cards (discard half, rounded down). Higher than standard (7), so hoarding is safer.
- **Friendly Robber [1v1].** The robber may only be **placed to block / stolen from a player who already has ≥3 VP**. Practical effect: early game, before you reach 3 VP, you cannot be robbed — so early dev-card stacking and expansion are safe.

### 3.6 Setup (snake draft)
2 players place in order **P1, P2, P2, P1** — so the **second player places both their settlements
consecutively** (picks #2 and #3), while the first player's two picks bookend the draft (#1 and #4).
Each places 2 settlements + 2 adjoining roads; a player's **second** settlement yields one resource
from each adjacent hex. Standard distance rule: no settlement adjacent to another (every vertex
within one edge must be empty).

### 3.7 Hidden information
- Opponent's exact **hand composition** (Colonist's public log reveals gains/discards/robs, so beliefs can be kept *tight* — see §6.5).
- **Dev cards held** (face down) and the **order of the dev-card deck**.
- **Future dice rolls** (pure chance, not hidden).

### 3.8 Strategic consequences of 15 VP (drives the evaluation function)
- **Buildings can reach 13 VP, not 9.** Upgrading a settlement to a city *returns the settlement piece to your supply* (verified against the official rules), so you can eventually field **all 5 settlements *and* all 4 cities** on 9 separate vertices: `5×1 + 4×2 = 13`. The binding constraint is **board space** — 9 distinct, non-adjacent, road-connected vertices — which is scarce on a contested 1v1 board, *not* the piece supply.
- ⇒ **Multiple paths reach 15, and no single component is strictly required:** e.g. 13 buildings + one bonus (Longest Road *or* Largest Army); or fewer buildings + both bonuses + VP dev cards. The solver should treat the win conditions as **substitutable** and re-weigh their availability as the game develops (matching the strategy guide's "assessment of the value of each win condition").
- ⇒ **In practice, fielding all 9 buildings while contested is hard**, so Longest Road, Largest Army, and dev-card VPs are **strong, usually-needed contributors** — valuable, but not theoretical requirements.
- ⇒ **Wheat and Ore are still the dominant resources** (cities = 2 wheat + 3 ore; dev cards = ore + wheat + sheep; Knights → Largest Army), and blocking an opponent's only Wheat is "extremely powerful." **But wood/brick keep real value**: fielding all 5 settlements needs roads + expansion room, and Longest Road is a clean +2 — so the eval weights Wheat/Ore highest **without neglecting expansion**.
- ⇒ Friendly Robber + discard-9 reward an **early dev-card/economy build** that's safe from robbing until 3 VP.
- Reference data point: **average 1v1 game ≈ 69 turns** — useful for setting rollout depth and planning horizon.

---

## 4. Project angles (weighed)

Two orthogonal axes: **how strong the decision engine is**, and **how the product is scoped**.

### 4.1 Decision-engine approaches

| Approach | Accuracy ceiling | Complexity | Feasibility | Verdict |
|---|---|---|---|---|
| **A. Pure heuristics** (pip counts, hand-tuned weights) | Low–med | Low | Trivial | Use as the **rollout/leaf policy** and a baseline, not the final product. |
| **B. Search: MCTS / ISMCTS / expectiminimax** | High | Med–high | Realistic | **Core of the project.** Handles chance + hidden info; gives per-action win-prob. |
| **C. Learned: RL / AlphaZero-style** | Highest | High | Hard (compute, tuning) | **Tier-3 stretch.** Best as a learned eval/policy *feeding* the search (Approach D). |
| **D. Hybrid: search + learned eval** (the AlphaZero recipe) | Highest | High | Hard but proven | **Target end-state**, reached incrementally from B → C. |
| **E. Equilibrium solvers** (CFR / MCCFR / DeepNash) | High (least exploitable) | Very high | Research-grade | Note as the principled imperfect-info alternative; revisit only if exploitability matters. |

**Recommendation:** B now (with A as its policy), evolving toward D; C/E as research extensions.

### 4.2 Product-scope angles

| Scope | Value | Effort | When |
|---|---|---|---|
| **Placement optimizer + interactive board UI** | High, shippable alone | Low–med | **MVP (Tier 1).** |
| **Full turn advisor** | The core ask | Med–high | **Tier 2 — primary goal.** |
| **Playable human-vs-bot game** | High UX payoff, shippable | Med (UI-heavy) | **Phase 6 — next/active.** |
| ~~Live Colonist.io coach~~ | High UX payoff | High, fragile | **Dropped (likely ToS violation).** |
| **Self-play research agent** | Learning/portfolio value | High | Stretch (Phase 5). |

---

## 5. Why a "true optimal solver" is out of reach (and what we do instead)

- **State space is enormous:** board layout × buildings/roads for both players × hands × dev cards × robber × bonuses × bank/deck contents — far beyond exhaustive solving.
- **Chance nodes everywhere:** dice and dev-card draws make this expectiminimax, not minimax.
- **Imperfect information:** hidden hands and deck order require reasoning over *information sets*, not states. Exact equilibria (CFR-style) are intractable at full scale.

**Therefore** we don't chase provable optimality. We compute a **strong approximate best response**
under an explicit opponent model, and **estimate win probability by Monte-Carlo simulation**.
This is exactly the regime where MCTS-family methods shine, and matches the published Catan-AI
literature (Szita et al. MCTS 2010; the deep-RL and cross-dimensional-NN agents that beat the
classic jSettlers heuristic).

---

## 6. Technical approach

### 6.1 Game engine — extend Catanatron (✅ confirmed in Phase 0)

**Recommendation: build on [Catanatron](https://github.com/bcollazo/catanatron)** rather than writing a rules engine from scratch, because it gives us, for free:
- a **fast** simulator ("thousands of games in seconds") — essential for MC rollouts and self-play;
- a **Gymnasium RL environment** (ready for Tier 3);
- **reference bots** (random + stronger value/search players) to benchmark against;
- a tested action/state model and feature extractors.

**Phase-0 spike results — all green** (details in [docs/phase0-findings.md](docs/phase0-findings.md)):
1. **License: MIT** — *not* GPL as first assumed; no redistribution constraints.
2. **2-player works** out of the box; board is the standard 19 hexes / 54 nodes / 72 edges.
3. **VP target & discard limit are native constructor params** — `Game(players, vps_to_win=15, discard_limit=9)`; the discard math (`len(hand)//2` when `cards > limit`) reproduces the 1v1 rule exactly.
4. **Snake draft is exactly P1, P2, P2, P1** (second player places both settlements consecutively) — the structure the MVP needs.
5. **`copy()` is independent**, and `playable_actions` / `execute()` give a clean action API — ready for rollouts/MCTS.
6. **Friendly Robber** was the only gap; it is now **injected and unit-tested** (a visible-VP filter in `robber_possibilities`; see `catansolver/engine/friendly_robber.py`).
7. **Trade:** Catanatron models **maritime/port trade only** (no domestic trade) — an acceptable fit for competitive 1v1 (see §9 Q1).

**Decision: extend Catanatron**, wrapped behind our own thin interface (`RulesConfig` + the
`catansolver/engine/` adapter) so the 1v1 rules live in *our* layer. The home-grown-engine
fallback is no longer needed but remains available if we ever outgrow Catanatron.

### 6.2 State representation
- **Board:** hexes (resource, token, robber flag) on a fixed coordinate system (axial/cube coords); vertex↔hex and vertex↔edge adjacency; port assignments. Computed once per game.
- **Per-player:** resource hand (5 counts), dev cards by type + knights played, pieces remaining, building map (vertex→none/settlement/city), road set (edges), ports owned, Longest-Road / Largest-Army flags, public + hidden VP.
- **Global:** bank resource counts, dev-deck remaining (count + composition belief), robber location, current player, turn phase, last dice, and the **belief model** over hidden info.
- **State schema (the MVP contract):** a **JSON schema validated with `pydantic`**, which doubles as the **HTTP API contract** between the web frontend and the Python solver. Getting this right early matters — it's the interface every tier, the interactive UI, and the future Colonist adapter all target.

### 6.3 Tier 1 — initial-placement optimizer

**Inputs & draft scenarios.** The optimizer takes the **current draft state** (whatever
settlements + roads are already on the board) plus the **user's seat**, and recommends the user's
*next* placement(s) up to their next handoff. In the snake order **P1, P2, P2, P1** that gives
three concrete cases the MVP covers:

| User's situation | Board given as input | Recommend |
|---|---|---|
| **Going first** — P1, pick #1 | empty board | **1** settlement + road |
| **Going second** — P2, picks #2 **and** #3 | opponent's 1st settlement + road | **both** of the user's settlements + roads, chosen **jointly** |
| **First player's final** — P1, pick #4 | 3 settlements (P1's first + P2's two) | **1** settlement + road |

The **opponent's existing placement(s) are part of the input** in all but the first case. Because
the second player places **two settlements back-to-back**, they are optimised as a **synergistic
pair** (complementary resources / ports / expansion / blocking) — *not* the top-2 independent spots.

At placement the board is fully observed; the only uncertainty is future dice and the opponent's
remaining draft choice(s). Tractable, so we combine three layers:

1. **Enumerate** legal placements (respecting the distance rule) for the user's decision — single spots, or **(settlement, settlement) pairs** for the second player.
2. **Heuristic pre-score** to prune to top-k. Features:
   - **Pip count** = sum of dice "pips" (ways-to-roll) on adjacent hexes: `6,8→5; 5,9→4; 4,10→3; 3,11→2; 2,12→1`.
   - **Resource value weighting** skewed toward **Wheat/Ore** (cities + dev cards) while still valuing **wood/brick** for expansion + Longest Road (per §3.8), plus **resource diversity** (measured *across the pair* for the second player).
   - **Port synergy**, **expansion potential** (open adjacent vertices), and **blocking value** vs the opponent's options.
3. **Monte-Carlo rollouts** on the survivors: simulate N games to completion with a fast rollout policy and estimate **win rate**, directly optimising the true objective. The remaining draft picks form a small **expectiminimax tree** (the opponent's reply minimises the user's win-prob) with MC-estimated leaf values; opponent replies can use the cheap heuristic or a deeper search as a **speed/accuracy knob**.

Report each candidate's estimated P(win) with a **confidence interval** (Wilson) so the user
sees both the pick and its certainty.

### 6.4 Tier 2 — turn advisor (mid-game)
**Algorithm: Monte-Carlo Tree Search adapted for chance + hidden information.**
- **Chance nodes** for dice (exact 2d6 distribution) and dev draws — expectiminimax-style expected-value backups, or sampled inside rollouts.
- **Hidden info — two-step plan:**
  1. **PIMC (determinized MCTS) first:** sample a concrete opponent hand + deck order consistent with the belief (§6.5), run standard MCTS, average over many determinizations. Simple and often strong.
  2. **Upgrade to [ISMCTS](https://eprints.whiterose.ac.uk/id/eprint/75048/1/CowlingPowleyWhitehouse2012.pdf)** (Information Set MCTS, Cowling et al. 2012): one tree over *information sets*, a fresh determinization per iteration. Fixes the **strategy-fusion** errors that hurt naive determinization.
- **Selection:** UCT (UCB1) now; **PUCT** once a learned policy prior exists (Tier 3).
- **Rollout policy: heuristic, never uniform-random** — random rollouts converge poorly and slowly in Catan. Use the Tier-1 heuristic (or a learned value to truncate rollouts).
- **Action model:** use the engine's atomic **playable-actions** decomposition (trade → build → play-dev as separate decision points) to keep branching manageable, rather than enumerating whole-turn macros.
- **Output:** from the root, each legal action's visit count + mean value (≈ win prob) → recommend the argmax, show top-3 with win-prob and CI.

### 6.5 Belief tracking over hidden information
Colonist's public log makes beliefs unusually tractable:
- **Opponent resource hand — *determined* in 1v1.** Each resource has 19 cards, so with the bank and our own hand known, `opp[r] = 19 − bank[r] − our[r]` exactly. There is nothing to sample (this is *not* true with ≥3 players, where a hand-size-only multivariate-hypergeometric draw — `sample_opponent_hand` — is needed). So the only genuinely hidden info in 1v1 is **dev cards**.
- **Dev-card deck/hand:** draws are without replacement → **multivariate hypergeometric** over the **unseen pool** = full 25-deck minus everything visibly gone: our own dev cards + every *played* card of both players. Tracking played non-knight cards (monopoly / year-of-plenty / road-building — public and recorded by Catanatron) as well as played knights makes the pool **exact**: `hidden_total == opp_hand_size + deck_remaining`.
- **Robber steal:** the stolen card is hypergeometric over the victim's believed hand.
- Determinizations are sampled **consistently** with all observed constraints.

**Behavioural tells (sharpen the dev-card belief beyond the uniform draw).** Two signals re-weight which face-down cards the opponent holds; both need a *per-card* view of how long each card has been held, carried by a stateful `DevCardHistory` fed the public turn log:
- **(3b) Held-duration → Victory Point.** VP cards are the only type *never actively played* (just revealed on the win); every other type is normally cashed within a few turns. So a long-held card is less likely an actively-playable type — a per-turn multiplier (`PLAYABLE_HELD_DECAY = 0.9`) down-weights KNIGHT/MONOPOLY/YEAR_OF_PLENTY/ROAD_BUILDING, leaving VP relatively more probable.
- **(3a) Robbed-and-passed → not a Knight.** Each turn the robber sits on one of the opponent's hexes and they *could* have knighted it off but didn't, the chance any held card is a knight is cut **90%** (`KNIGHT_ROBBED_PASS_FACTOR = 0.1`, hardcoded) — ~0 after a couple such turns. Two guards keep it honest: it only counts when a knight play was actually possible (they hadn't already played a dev card that turn), and the evidence attaches only to cards acquired *before* that turn (can't play a card the turn you buy it). Deliberately **not** softened for the Largest-Army-timing case — the sharp convergence is intended.
- **Deferred (needs the live log, Phase 6):** the *general* opponent-policy version of (3a) — inferring from any beneficial-play that was declined, not just robbed-and-passed — is more powerful but assumption-laden / exploitable, so it waits for live capture. The mechanics here ride on the same `DevCardHistory.observe_*` seam.

### 6.6 Tier 3 — self-play learning (stretch)
- **Baseline RL first:** PPO / DQN (Stable-Baselines3) on Catanatron's Gym env to learn a **value function / policy** that serves as a stronger rollout policy or leaf evaluator for the MCTS — i.e., move toward **Approach D** without a full from-scratch AlphaZero.
- **AlphaZero-style** (PUCT + policy/value net + self-play) is the aspirational end-state. Caveat: AlphaZero assumes perfect information; for the hidden-info reality, options are (a) train the value net on full state but determinize at play time, or (b) imperfect-info methods (ReBeL, regularized Nash / DeepNash, or the recent *Simultaneous AlphaZero for Markov games* line).
- **Prior art to mine:** [Learning to Play Catan with Deep RL](https://settlers-rl.github.io/), the cross-dimensional-NN agent that beats jSettlers, Catanatron's own bots, and Szita et al.'s MCTS work.

### 6.7 Statistical methods used (and why)

| Method | Used for | Why |
|---|---|---|
| **2d6 distribution / pip counts** | Production estimates, placement scoring | Exact, cheap, foundational. |
| **Monte-Carlo simulation** + Wilson/Wald **CIs** | Win-prob estimation everywhere | Directly estimates the objective; CIs quantify certainty and set sample sizes. |
| **Bandit algorithms (UCB1/UCT, PUCT)** | MCTS node selection | Principled explore/exploit; PUCT integrates a learned prior. |
| **Expectiminimax backups** | Chance nodes (dice/draws) | Correct expected-value propagation through randomness. |
| **(MV) hypergeometric** | Deck draws, robber steals | Exact model of sampling without replacement. |
| **Bayesian belief updating** (categorical/Dirichlet) | Opponent-hand beliefs | Turns the public log into tight, sample-able distributions. |
| **Variance reduction** (common random numbers, antithetics) | Comparing candidate moves | Same dice across candidates → far fewer sims for a reliable ranking. |
| **Calibration metrics** (Brier, log-loss, reliability diagrams) | Validating P(win) outputs | A "70% win" claim must actually win ~70%. |
| **Elo / win-rate with CIs** | Bot-vs-bot evaluation | Standard, comparable strength measurement. |
| **(Stretch) CFR / regret minimisation** | Equilibrium route | The principled, low-exploitability alternative to best-response search. |

### 6.8 Packages (and justification)

| Package | Role | Why |
|---|---|---|
| **Python 3.11+** | Language | Ecosystem + speed/typing improvements. |
| **Catanatron** | Engine, Gym env, benchmark bots | Fast, tested, RL-ready; **MIT**-licensed, 1v1-ready (confirmed Phase 0). |
| **NumPy** | Vectorised probability/feature math | Fast array ops for pip/production/feature calc. |
| **pydantic** | JSON state schema + validation | The manual-input contract must be strictly validated. |
| **pytest** + **hypothesis** | Testing (incl. property-based) | Rules invariants are perfect for property tests. |
| **Typer/Click** + **Rich** | CLI + readable output | Dev/testing surface and scripting. |
| **FastAPI** + **uvicorn** | Solver HTTP API behind the UI | Async, lightweight, auto-validates against the pydantic schema; serves the frontend. |
| **SVG/Canvas frontend** (vanilla JS or a light framework) | Interactive hex board | Easiest path to a clickable, rendered Catan board; reused by the Phase-6 Colonist UI. |
| **multiprocessing / joblib** | Parallel rollouts & self-play | MC and MCTS are embarrassingly parallel. |
| **Numba / Cython** *(optional)* | Hot-loop speedups | Only if we run our own engine and need rollout speed. |
| **scipy.stats** | Distributions, CIs, hypergeometric | Off-the-shelf statistical primitives. |
| **PyTorch** | Tier-3 nets | Standard DL framework; pairs with the Gym env. |
| **Stable-Baselines3** + **Gymnasium** | RL baselines (PPO/DQN) | Fast path to a learned value/policy. |
| **Optuna** *(optional)* | Tune heuristic weights / MCTS params | Systematic tuning beats hand-fiddling. |
| **matplotlib/plotly** *(optional)* | Board viz, calibration plots | Debugging + result communication. |

### 6.9 User interface — interactive board (MVP)
The MVP ships with a **visual, click-to-build board**, not just a CLI. Chosen approach: a **local web app** — the Python solver runs behind a **FastAPI** server and a browser frontend renders the hex board as **SVG/Canvas**.

**Input (the priority).** The user constructs the starting board in the UI:
- drop a **resource** on each of the 19 hexes (wood / brick / sheep / wheat / ore / desert) and assign its **number token**, place the 9 **ports**; then set the **draft state** — choose the user's seat (going first / going second / first-player's-final) and place any **existing settlements + roads** already down (the opponent's, treated as input — and the user's own where applicable);
- the UI enforces legality **live** (token-bag counts, no number on the desert, distance rule for placements) so a malformed board can't be submitted;
- entry helpers: the standard token bag, a "randomise" button, and manual override for transcribing a real Colonist board.

**Output.** Recommendations are drawn **directly on the board** — the top-N candidate settlement+road spots highlighted and ranked, each annotated with estimated **win % ± CI**, plus a side-panel list. No opaque vertex IDs to decode.

**Why a web app over a desktop GUI.** Hex rendering and click interaction are far cleaner in SVG/Canvas; it's instantly shareable/demoable; and it **directly seeds the Phase-6 Colonist.io integration** (also browser-based), which can later auto-populate the *same* board instead of manual clicks. The solver stays fully headless behind the API, so it remains scriptable and unit-testable on its own.

**Alternative (if we want zero JavaScript).** A pure-Python desktop GUI — **Pygame** (custom hex drawing) or **Dear PyGui** — gives the same interactivity in one language, at the cost of reuse for the later browser work. Flagged as a fallback, not the default.

### 6.10 Opening-placement practice mode (Phase 2.5)
A **drill tool** that sits alongside the advisor (a tab in the same UI), turning the optimizer into a trainer. The user is shown a **randomised valid board** plus a generated draft situation for one of the three seats, places their own settlement(s)+road(s), then submits to **reveal the optimal move, a per-piece verdict, and a running score + streak**.

- **Puzzle generation.** A valid random board (no adjacent red 6/8) + a seat (FIRST / SECOND / FIRST_FINAL, or **random each puzzle**). The *prior* placements the seat needs (the opponent's, and for FIRST_FINAL the user's own opener) are produced by the **default rollout policy** and baked into the request, so each puzzle is a self-contained, legal input.
- **Grading (heuristic, instant).** Each settlement/road is graded **sequentially** against the legal options the user actually faced. Roads are judged **relative to the settlement the user chose**. The revealed "model line" is a self-consistent greedy walk, so a perfect answer scores full marks; the solver's joint top-k ranking is also shown for deeper study. A **tolerance band** (settlement ≥93 %, road ≥90 % of best) decides whether a piece counts as "good enough" for the streak.
- **Scoring (continuous, /10).** Each puzzle is scored **out of 10** by how close the answer is to optimal: every piece gets a **quality** in 0–1, and the 10 points are split by weight (**settlements count double the roads**) and scaled by quality. Settlement quality is normalised over the legal spread (worst→best, ~50 options); **road quality is a ratio-to-best** (only ~3 legal roads, so spread-norm was too punitive — the worst road still heads toward a spot ~70% as good and should earn it). A truly **optimal** answer scores 10 and is the only one labelled "Perfect"; near-misses earn fractional points. **Streak** counts consecutive within-tolerance puzzles; **total points / average-per-puzzle** persist in the browser (localStorage). Weights + band thresholds are the only tunables (calibratable in Phase 4).
- **UX.** Entering the tab opens a **scenario chooser**; pieces are placed by clicking (click again to remove); the **Submit** action is the prominent control; the reveal describes spots by their **adjacent hex numbers** (e.g. `5-8-11`) and roads by **direction** (L/R/U/D).
- **Out of scope for the drill:** Monte-Carlo grading (too slow for rapid reps — heuristic only), and mid-game practice (openings only, matching Tier 1).

### 6.11 Proposed repo structure
```
catansolver/
  engine/        # Catanatron adapter + RulesConfig + 1v1 rule patches (Friendly Robber, discard 9, 15 VP)
  io/            # pydantic state schema, JSON parsers/serializers, CLI
  beliefs/       # hidden-info belief tracking + determinization sampling
  placement/     # Tier 1 optimizer (heuristics + MC rollouts + draft expectiminimax)
  advisor/       # Tier 2 PIMC/ISMCTS turn advisor
  eval/          # heuristic policy + (later) learned value/policy
  api/           # FastAPI app exposing the solver over the JSON state schema
  rl/            # Tier 3 gym wrappers + training
  integration/   # Tier 6 Colonist.io capture (separate sub-project)
  tests/
frontend/        # browser board UI (SVG/Canvas): click-to-build input + recommendation overlay
plan.md
pyproject.toml
```

---

## 7. Phased roadmap (chronological)

Each phase has a clear deliverable and exit criteria; phases 1–4 were the committed core
(all complete), Phase 5 (learned play) is complete, and **Phase 6 — a playable human-vs-bot
game — is the active next phase** (the original live-Colonist.io coach was dropped: ToS).

### Phase 0 — Foundations & de-risking  ✅ **complete (2026-06-14)**
- **Tasks:** repo + tooling; **Catanatron spike** (2-player? VP config? where to inject Friendly Robber / discard-9? license?); finalise the 1v1 rules spec; design the JSON **state schema** (it doubles as the UI ↔ solver API contract).
- **Deliverable:** decision memo (extend Catanatron vs build own) + frozen rules spec + schema.
- **Exit:** we can construct, serialise, and validate a 1v1 game state and apply legal actions through our engine interface.
- **Done:** venv (Python 3.9.7) + deps; spike → **extend Catanatron** (MIT; native VP=15 / discard=9; correct snake draft; independent `copy()` + action API); engine adapter + **Friendly Robber injected & tested**; pydantic state schema with `OpeningPlacementRequest`; **14 tests green**. Memo: [docs/phase0-findings.md](docs/phase0-findings.md).

### Phase 1 — Engine & state I/O  ✅ **board adapter complete (2026-06-14)**
- **Tasks:** implement/patch the 1v1 ruleset behind `RulesConfig`; manual JSON/CLI input + output; **Longest-Road** computation (longest simple path in the road subgraph — small but the trickiest rule to get right); production, robber, build-legality, dev-card effects.
- **Deliverable:** a correct, scriptable 1v1 engine + state loader.
- **Exit:** full rules **test suite green**; engine cross-checked against Catanatron on random games (legal-action sets + outcomes agree where rules overlap).
- **Done:** board ⇄ schema adapter (`catansolver/engine/adapter.py`) — export (`map_to_schema`/`board_from_game`) and import (`schema_to_map`/`game_from_board`) onto the *exact* user layout via Catanatron's `initialize_tiles` reverse-`pop` seam; **round-trip verified against real Catanatron maps across 7 seeds**, and constructed games are fully playable. Longest-road / production / build-legality / dev-cards are **native to Catanatron** (no reimplementation needed). **37 tests green.**
- **Deferred to Phase 3:** ~~full *mid-game* `GameState` import/export (hands, buildings, dev cards)~~ — ✅ **done in Phase 3.1** (`catansolver/engine/state_adapter.py`).

### Phase 2 — Tier 1 placement optimizer + interactive board UI (**MVP**)  ✅ **complete (2026-06-14)**
- **Solver tasks:** legal-placement enumeration; heuristic scorer (Wheat/Ore-weighted pip + diversity + ports + expansion + blocking); MC rollouts with Wilson CIs; draft-aware expectiminimax over the snake order — incl. **joint settlement-pair search for the second player** and all three draft cases (P1 opener / P2's two picks / P1's final). See §6.3.
- **UI tasks:** FastAPI endpoint over the state schema; browser hex board (SVG/Canvas) with **click-to-build board entry** (resources, number tokens, ports), **draft-seat selection + entry of the opponent's existing settlement/road**, live legality checks, and **on-board display of ranked recommendations** with win % ± CI. (A thin CLI is kept as a developer/testing surface.)
- **Deliverable:** **enter a board + draft position in the UI → see the best opening placement(s) highlighted on the board, with win-prob estimates** (one spot when going first, both spots when going second).
- **Exit:** a non-technical user can input a real Colonist board and read recommendations without touching JSON; solver beats naive pip-count picks head-to-head; win-prob estimates are **calibrated** (Brier/reliability check).
- **Done (solver, 2026-06-14):** `catansolver/placement/` — heuristic scorer (Wheat/Ore-weighted production + diversity + ports), MC rollouts with Wilson CIs, a draft-driving helper, and `recommend_opening` covering **all three seats** (FIRST, SECOND joint-pair search, FIRST_FINAL) with a multi-placement `Recommendation`. **46 tests green.** Caveats for Phase 4: absolute win-rates inflated by the greedy rollout opponent; calibration + stronger policy still to come.
- **Done (UI, 2026-06-14; refined 2026-06-16):** `catansolver/api/` — **FastAPI** app (`/api/layout`, `/api/board/random`, `/api/recommend`) + a browser **SVG board** (`static/`). Board starts empty; fill it **two ways** — click a hex → centre modal, or select a paint swatch and click hexes ("Random Board" fills one outright). Seat selection + draft-piece entry, live board-legality checks, an **ⓘ** explainer on the Analyze panel, and an on-board recommendation overlay. Geometry derived from Catanatron's topology (19/54/72/9, exact). Verified live under uvicorn; **51 tests green** (incl. API). Follow-ups: in-UI port editing + faster (parallel) rollouts.

### Phase 2.5 — Opening-placement practice mode  ✅ **complete (2026-06-16)**
- **Tasks:** a drill tab beside the advisor — randomised puzzle per seat (or random), click-to-place, instant heuristic grading with a tolerance band, on-board reveal of the model line + grade rings, and a persisted score/streak. See §6.10.
- **Deliverable:** **pick a scenario → place your opening → see right/wrong (and by how much) + the optimal move, with a running score & streak.**
- **Exit:** replaying the solver's model line scores full marks; weak picks lose points and break the streak; puzzles are valid & seat-correct.
- **Done (2026-06-16):** `catansolver/placement/practice.py` (`generate_puzzle` + `grade_practice`, self-consistent greedy model line, **continuous /10 quality scoring**, sequential grading) + schema `UnitGrade`/`PracticeResult`; API `/api/practice/new` + `/api/practice/grade`; geometry now exposes `node_hexes`. UI: scenario-chooser modal, click-to-place **with click-to-remove**, prominent Submit, reveal (gold model line, cyan inspect, green/orange grade rings) describing spots by **hex numbers** + roads by **direction**, "Perfect" only when truly optimal, scoreboard (total/streak/avg-per-puzzle in localStorage) + solver top-k reveal. **66 tests green.**

### Phase 3 — Tier 2 turn advisor  ✅ **complete (2026-06-20; exit criterion met)**
- **Tasks:** belief tracker + determinization sampler; **PIMC** MCTS with heuristic rollouts → **ISMCTS** upgrade; chance-node handling; per-action win-prob output.
- **Deliverable:** **mid-game state → recommended action(s) + win-prob** (CLI; surfaced in the board UI in Phase 4).
- **Exit:** advisor's picks beat random + heuristic + Catanatron reference bots by a statistically significant win-rate margin.
- **Done (3.1, 2026-06-19):** mid-game state import/export (`catansolver/engine/state_adapter.py`) — `game_to_state` / `game_from_state` reconstruct an arbitrary position (buildings, roads, hands, dev cards, bank, dev deck, Longest Road / Largest Army, whose turn) into a live, playable Catanatron game. Round-trip verified across seeds (export→import→export stable; VP preserved; imported game plays on).
- **Done (3.2, 2026-06-19):** baseline turn advisor (`catansolver/advisor/turn_advisor.py`, `recommend_actions`) — enumerates the current player's legal actions and ranks them by **determinized flat Monte-Carlo** win rate (Wilson CIs, common-random-numbers across candidates), output as `ActionRecommendation`s. CLI demo: [scripts/advise_demo.py](scripts/advise_demo.py). **87 tests green.** Known limits (the motivation for 3.3/3.4): treats the position as fully observed (no belief sampling yet), values only one ply before rollout, and win-rate saturates vs the weak baseline opponent on decided positions.
- **Done (3.3, 2026-06-20):** belief tracking + determinization sampling (`catansolver/beliefs/determinize.py`). Key result: in 1v1 with a tracked bank the opponent's **resource hand is *determined*** (`19 - bank[r] - our[r]`), so the only genuinely hidden info is **dev cards**. `dev_card_belief(gs)` builds the observer's belief from public facts only (opponent hand *size* + every played card — never the recorded composition); `sample_determinization(gs, rng)` draws the opponent's face-down hand + remaining deck from the unseen pool by **multivariate hypergeometric**, returning a concrete `GameState` + matching `dev_deck` that `game_from_state(..., dev_deck=...)` consumes. Crucially surfaces hidden **VP cards** (opponent may be closer to 15 than the board shows). CLI demo: [scripts/belief_demo.py](scripts/belief_demo.py).
  - **Exact unseen pool:** schema/`PlayerState` + state-adapter now track *played* monopoly / year-of-plenty / road-building (round-trips through `game_to_state`/`game_from_state`), closing the deck-composition gap so `hidden_total == opp_hand_size + deck_remaining`.
  - **Behavioural belief (§6.5):** a stateful `DevCardHistory` (fed the public turn log via `observe_buy` / `observe_play` / `observe_robbed_turn`) tags each held card with age + robbed-passes; `sample_dev_cards`/`weighted_hand_draw` then apply **(3b)** held-duration→VP (`PLAYABLE_HELD_DECAY=0.9/turn`) and **(3a)** robbed-and-passed→not-a-knight (`KNIGHT_ROBBED_PASS_FACTOR=0.1`, with the buy-turn-epoch and already-played-a-dev guards). Demo: uniform VP 22%/knight 51% → held ~14 turns 56%/30% → +3 robbed passes 64%/**0%**. No history ⇒ falls back to the plain uniform draw (single-snapshot compatible).
  - **113 tests green** (+26 belief tests).
- **Done (3.5, 2026-06-20) — ✅ exit criterion met:** strength evaluation (`catansolver/eval/arena.py` — `AdvisorPlayer` wraps the PIMC advisor as a Catanatron player; `play_match` runs balanced seat/colour-alternated matches with Wilson CIs). 30 games/opponent at modest settings (2 determinizations × 25 UCT iters, `rollout_depth=10`), full 1v1 ruleset: advisor beats **RandomPlayer 26-4 (87%, CI 70–95)**, **WeightedRandom/heuristic 24-6 (80%, 63–90)**, **VictoryPointPlayer/search 21-8-1 (70%, 52–83)** — all Wilson lower bounds clear 50%, so significant over every baseline. Report: [docs/advisor-strength.md](docs/advisor-strength.md); raw log [docs/advisor-eval.log](docs/advisor-eval.log); harness [scripts/evaluate_advisor.py](scripts/evaluate_advisor.py). Caveats at the time: relative (vs built-in bots, not humans); VP margin only just clears significance at n=30; advisor handicapped (robber/discard used the WeightedRandom fallback, settings modest) — *robber since made advisor-driven, see follow-ups below*. **125 tests green.** Also fixed a state-import crash surfaced by deep games: roads *severed from their owner's network by an enemy settlement* now force-place (faithful board + correct broken-segment Longest Road) instead of raising — regression-tested over deep WeightedRandom games.
- **Done (3.4, 2026-06-20):** PIMC turn advisor (`catansolver/advisor/pimc.py`, `recommend_actions_pimc`). Samples `n_determinizations` worlds from the belief (3.3, optional `DevCardHistory`), runs **open-loop UCT** in each fully-observable world, and aggregates root-action visit/win stats across worlds into a per-action win-prob (Wilson CI). Upgrades the 3.2 flat-MC two ways: **hidden info** (search no longer trusts the opponent's recorded hand) and **lookahead** (a real tree vs one ply). Chance (dice/draws) is sampled *open-loop* — the action path is replayed on a fresh game copy each iteration — rather than enumerated as explicit expectiminimax chance nodes (a future refinement). Leaves: full playout (true win/loss, default) or a `rollout_depth`-truncated playout finished by a VP-lead logistic — the latter runs ~4× the iterations per second, which UCT needs since iterations must exceed the ~16-wide root branching. CLI demo: [scripts/pimc_demo.py](scripts/pimc_demo.py) (8×150 in ~3s ranks BUILD_CITY top, END_TURN/BUY_DEV last, CIs ~±9pts). **120 tests green** (+7). Known limit (the motivation for ISMCTS): PIMC searches each world *knowing* the sampled hidden cards → strategy fusion, can't value information-gathering. Win-rates remain *vs the baseline opponent* (relative signal) pending 3.5.
- **Done (follow-ups, 2026-06-20):**
  - **ISMCTS** (`recommend_actions_ismcts`) — one tree over information sets, re-determinized every iteration, with **availability-based UCB**; a *base+inject* optimisation (build the board once, re-sample the hidden hand onto a copy per iteration) keeps it ~as fast as PIMC. **Head-to-head (40 games/opponent, matched 50-iter budget): ISMCTS ≈ PIMC** (Random 80 vs 82, heuristic 82 vs 80, VP 75 vs 75 — all within CI). Confirms the §6.4 expectation: with only dev-card hidden info, strategy fusion costs little, so PIMC stays the default and ISMCTS is kept for when hidden info matters more. Log: [docs/advisor-eval-ismcts.log](docs/advisor-eval-ismcts.log).
  - **Parallel evaluation** — `play_match(..., workers=N)` plays games across processes (`ProcessPoolExecutor`, BLAS/OMP thread caps set before numpy import, picklable factories, `__main__`-guarded). ~3× wall-clock on 8 cores; makes tighter evals / future UI latency affordable.
  - **Robber capture** — schema `prompt` + `has_rolled` now round-trip, so `AdvisorPlayer` drives **MOVE_ROBBER** (18-option, strategic) through the search instead of the WeightedRandom fallback (DISCARD stays auto-resolved — Catanatron offers it as a single forced action). Removed the old post-roll dice hack. Regression-tested.
- **Remaining headroom (Phase 4/5):** explicit expectiminimax chance nodes; stronger search settings; absolute (calibrated, vs-human) win-prob via the eventual learned value head.

### Phase 4 — Evaluation, calibration & UX  ✅ **core complete (2026-06-21; exit criteria met)**
- **Baseline measured (2026-06-18):** the opening heuristic vs Monte-Carlo win-prob — pooled Pearson **0.885**, within-board Spearman **0.879**, monotone across heuristic quintiles, top-pick mean regret **1.4 win-% pts**. Report: [docs/heuristic-accuracy.md](docs/heuristic-accuracy.md). Biggest gains expected from *new features* (expansion potential, blocking) over re-weighting; this win-prob signal is a ready-made Optuna objective.
- **Win-% display trialled then shelved (2026-06-19):** a per-seat logistic ([winprob_model.py](catansolver/placement/winprob_model.py)) maps the heuristic to a win-%, but it's only calibrated against weak built-in bots. A VP recalibration ([scripts/calibrate_winprob_vp.py](scripts/calibrate_winprob_vp.py)) confirmed `VictoryPointPlayer` ≈ `WeightedRandomPlayer` here — e.g. the SECOND seat reads **~96%** for a strong pair vs **44%** for strong humans (TwoSheep 1v1 data). So the absolute % misleads; the **UI shows the strength score** instead, and an accurate win-% awaits the Tier-2/3 agent (whose value head provides it directly). Backend win-prob machinery kept dormant. Details: [docs/heuristic-accuracy.md](docs/heuristic-accuracy.md).
- **Tasks:** tournament harness (Elo + win-rate CIs); win-prob calibration (Brier/log-loss/reliability); MCTS + heuristic-weight tuning (Optuna); extend the board UI to the **full turn advisor** (show recommended action(s) + win-prob for any mid-game state) and polish UX.
- **Done (4.1, 2026-06-20):** round-robin tournament + **Elo** (`catansolver/eval/tournament.py`, `run_tournament`/`fit_elo`) — Bradley-Terry MLE via Hunter MM iteration, Elo scale anchored to mean 1500, draws half. Result (30 games/pair, full ruleset): **Advisor(PIMC) 1701** ≫ WeightedRandom 1464 ≈ VictoryPoint 1454 ≫ Random 1381 — the advisor leads the field by **~240 Elo** (≈80% expected). Harness [scripts/tournament.py](scripts/tournament.py), log [docs/tournament.log](docs/tournament.log), report [docs/advisor-strength.md](docs/advisor-strength.md).
- **Done (4.2, 2026-06-20):** win-prob **calibration** (`catansolver/eval/calibration.py`, `collect_samples`/`reliability`; `AdvisorPlayer` records the chosen move's P(win)). 40 games vs WeightedRandom, 5193 predictions: **Brier 0.097** (vs base-rate 0.143 → **+32% skill**), ECE 0.10, mean pred 0.73 vs actual 0.83. The reliability curve is **monotonic but systematically under-confident** (a predicted coin-flip wins ~75%) — because rollouts model the advisor's own future as the weak baseline policy. Confirms "show strength, not raw %". Report [docs/advisor-calibration.md](docs/advisor-calibration.md), log [docs/calibration.log](docs/calibration.log).
- **Done (4.2b, 2026-06-21):** **isotonic recalibration** (`catansolver/eval/recalibrate.py`, `fit_isotonic`/`Calibrator` — PAVA, no sklearn, knot-compressed + JSON-serialisable). Fit on a train split, evaluated on a **disjoint test split**: **ECE 0.115 → 0.047** (more than halved), Brier 0.101 → 0.083, mean prediction 0.73 → 0.85 (onto the 0.84 base rate). Map saved to [docs/recalibration.json](docs/recalibration.json) for the UI to apply; harness [scripts/fit_recalibration.py](scripts/fit_recalibration.py). Caveat: calibrated vs the WeightedRandom-level opponent, not a human. **145 tests green** (then +2 compression tests = 147).
- **Deliverable:** an evaluation report + a usable, trustworthy advisor.
- **Exit:** documented strength vs baselines; calibrated probabilities; reproducible benchmarks. **All three met** (Advisor 1701 Elo / +240; recalibrated ECE 0.047; tournament + calibration + recalibration harnesses with logs).
- **Optional follow-ups (deferred 2026-06-21):** **4.3 Optuna tuning** of search/heuristic hyperparameters (compute-heavy, diminishing returns given the ~240-Elo lead); **4.4 board-UI integration** of the full turn advisor (mid-game state entry → ranked actions + calibrated win-prob, applying [docs/recalibration.json](docs/recalibration.json)). Neither blocks the exit; both can fold into Phase 5 / a later UI pass.

### Phase 5 — Tier 3 learned play (stretch)  ✅ **5.1 + 5.2 complete (2026-06-25; exit met via depth-0); deep RL deferred (deps)**
- **Tasks:** PPO/DQN baseline on the Gym env → learned value/policy as MCTS leaf-eval/prior (Approach D); optional AlphaZero-style self-play loop.
- **Deliverable:** a stronger and/or faster advisor.
- **Exit:** measurable win-rate improvement over Phase-4 search alone.
- **Env constraint:** the venv has **only numpy** (no torch / sklearn / SB3 / gym, and installs are fragile here), so deep RL / AlphaZero are deferred. Pursued the same goal — a learned **value as MCTS leaf-eval (Approach D)** — with numpy.
- **Done (5.1, 2026-06-22):** learned value pipeline (`catansolver/learn/`): 18-dim position **features** (me−opp diffs + game stage), **self-play data** generator (WeightedRandom, both-perspectives → balanced; cap raised after finding weak self-play runs 450–1600 actions), **numpy IRLS logistic value model** (`docs/value_model.json`, **0.765 held-out accuracy**), and integration as the PIMC/ISMCTS leaf evaluator (`value_model=` on `recommend_actions_*` / `AdvisorPlayer`). **A/B vs the VP-lead heuristic leaf:** at the default `rollout_depth=10` the value barely helps (n=100 **58%, not significant** — the rollout dominates the eval before the value is consulted). **The win is at `rollout_depth=0`** (5.1e): the value-only leaf is **3.8× faster** (37 vs 141 ms/decision) and — at equal iterations — **ties** heuristic@d10 (30-29-1, 50%); spend the freed time on ~3.6× more iterations and it **significantly beats** it (**38-20-2, 63%, CI 51–74**). **Phase-5 exit met.** Recommended config with a value model: `rollout_depth=0` + max iterations. Report [docs/learned-value.md](docs/learned-value.md); harnesses [scripts/train_value.py](scripts/train_value.py) / [evaluate_value.py](scripts/evaluate_value.py) / [evaluate_depth.py](scripts/evaluate_depth.py). **155 tests green** (+~25). Pipeline scaffolds a future deep net.
- **Bigger levers (future):** a nonlinear value (GBT / small net) + a stronger data-generation policy than WeightedRandom — both need libs absent in this env.
- **Done (5.2a/b, 2026-06-22) — opening win-% revisited:** the win-% shelved in Phase 4 (weak-bot calibration) is now produced from the **value model** (`catansolver/placement/opening_value.py`, `opening_win_prob`): drive the draft → play the candidate → finish the draft → value-model eval at the first PLAY position, averaged over completions, recalibrated. **Calibration study** ([scripts/calibrate_opening.py](scripts/calibrate_opening.py), `collect_opening_samples`): value model is **under-confident at openings** (opening matters more than it thinks) but monotonic, so isotonic recalibration gives **held-out ECE 0.093→0.040, base rate 0.50** → [docs/opening_calibrator.json](docs/opening_calibrator.json). Demo (FIRST seat): best spot **84.9%**, middle 64%, worst 61% — monotonic + well-spread. Cheap (one value eval/completion, no rollout). **Honest label required: vs a baseline-level opponent, not a human.** Report [docs/opening-winprob.md](docs/opening-winprob.md). **158 tests green.**
- **Done (5.2c, 2026-06-25) — calibrated opening win-% in the UI:** the win-% is now surfaced in both surfaces, honestly labelled **"vs an equal-strength bot."**
  - **Advisor-level recalibration (Approach A):** rebuilt the opening calibrator against an *equal-strength* opponent (value@d0 self-play) instead of WeightedRandom, via a parallelised collector (`collect_opening_samples_parallel`, ~12 min for 344 samples vs ~1 hr serial). Key finding: **openings are near coin-flips under equal play** — base rate and mean-pred both **0.500**, raw Brier **0.21** (barely better than the 0.25 of always-50%), i.e. *low resolution, not a compressed mapping*. The mapping itself moved little vs the baseline calibrator (recalibration ECE 0.079→0.055). Saved [docs/opening_calibrator_advisor.json](docs/opening_calibrator_advisor.json); log [docs/opening-cal-advisor.log](docs/opening-cal-advisor.log). This is the calibrator the API loads.
  - **Board-bank idea (Approach B) — measured then shelved:** prototyped a precomputed "gold-standard" board bank ([scripts/board_bank_prototype.py](scripts/board_bank_prototype.py)). Measured **`C_board` = 3.7 hr/board** (6 workers; 6,750 games/board at 11.9 s/game value@d0), i.e. **6.2 days for a 40-board bank**. Rejected: Approach A already enables the feature on *any* board instantly, and since openings are ~50/50 there is little spread for B's extra precision to resolve. Documented for the record; revisit only for a curated "ranked openings" feature (and then 5–10 boards overnight, not 40).
  - **Wiring:** [catansolver/api/app.py](catansolver/api/app.py) lazy-loads the opening win-% model and annotates `/api/recommend` (each pick's `opening_win_prob`, ~0.2 s each) and `/api/practice/grade` (`user_win_prob` vs `optimal_win_prob`), degrading gracefully if artifacts are absent. The board UI sorts recommendations by the calibrated win-% (headline) with the heuristic score as a secondary number, the practice feedback shows "your opening ≈X% · model's line ≈Y%," and the "Analyze" copy that promised a win-% "once the solver has its own strong bot" is fulfilled.
- **Done (5.2d, 2026-06-25) — opening leverage + a better opening evaluator:** a leverage study ([scripts/opening_leverage.py](scripts/opening_leverage.py), [docs/opening-leverage.log](docs/opening-leverage.log)) measured how often the stronger-opening drafter wins in equal-vs-equal self-play: **~76% (random), 76% (simple), 70% (search), 80% (value@d0)** — opening advantage is **large and roughly skill-independent** (a clear out-draft wins ~85–96% at every tier), *not* the coin-flip the value model's low resolution had implied. That motivated mapping the **heuristic opening-strength gap** (my node-score sum − opponent's) straight to a win-%, which **beats the value model + calibrator** head-to-head on held-out self-play: **Brier 0.155 (WR) / 0.166 (equal-strength) vs 0.195 / 0.193** ([scripts/calibrate_opening_heuristic.py](scripts/calibrate_opening_heuristic.py), [docs/opening-heuristic-cal.log](docs/opening-heuristic-cal.log)). Why: at the opening the purpose-built production score out-predicts the general mid-game value model (which under-reacts to raw production). It must be the *gap*, not the absolute value (win-% is relative; differencing cancels board richness). Saved a 1-feature logistic [docs/opening_gap_model.json](docs/opening_gap_model.json) (gap +0.25→85%, −0.25→15%); `opening_win_prob_gap` is a drop-in and the API now uses it. Bonus: the win-% now tracks the ranking heuristic, so the displayed order and the win-% agree (no more value-model inversions). UI copy corrected (the old "openings are ~50/50" caption undersold the real leverage). **162 tests green** (+2).

### Phase 6 — Playable human-vs-bot game  ◀ **next / active (planned 2026-06-25)**
**Pivot (2026-06-25):** the original Phase 6 — a *live Colonist.io coach* via websocket reverse-engineering / Playwright capture — is **dropped** (likely ToS violation; user's call). Phase 6 is now a **self-contained 1v1 game the user plays against the bot in the browser, start to finish.** The two normally-hard parts already exist: the **rules engine** (Catanatron plays full 1v1 games — build, dev cards, robber, discard, longest road / largest army, 15 VP, friendly robber) and the **bot** (~1701 Elo, calibrated). The remaining work is a server game-loop + the interactive game UI.

- **Scope decisions (user, 2026-06-25):**
  - **No player-to-player (domestic) trading** — the fiddly negotiation part is cut, matching the project's long-standing "no domestic trade" stance (§9 Q1). **Bank/port maritime trades (4:1 / 3:1 / 2:1) are kept** — they're a single legal action with no negotiation and are essential to normal play (and keep ports meaningful). *(If "no trading of any kind" is preferred, it's a one-line toggle — confirm.)*
  - **Bot always at max strength within a per-turn time budget** (no difficulty slider). **Measured** (value@d0 ISMCTS, opponent's hidden cards sampled): at **n_det=3, iter=100** a decision takes **~0.2 s median, <1 s worst**, a typical bot turn **<0.5 s**, a busy turn **~1–3 s** — comfortably within "a few seconds." Lock in the strongest measured config under that budget; optionally make the search **time-budgeted** later ("iterate until ~1.5 s") to always spend the full budget. The bot's opening placements are instant (fast draft fallback).
  - **Minimum ~1 s per bot decision (deliberate pacing):** even when the search finishes faster (e.g. 0.2 s), the UI holds each bot action for **at least ~1 second** so the user can follow what the bot is doing. Implement as a floor (`max(think_time, 1 s)`) per surfaced bot action, not per turn — a multi-action bot turn then plays out as a readable sequence.

- **Architecture:**
  - **Server:** one in-memory `Game` per session. Endpoints — `POST /api/game/new`, `GET /api/game/{id}` (full state), `POST /api/game/{id}/action` (apply a human action); the server **runs the bot** (`AdvisorPlayer`) until it's the human's turn or a human input is required (discard on a 7). Legal moves come straight from Catanatron's `playable_actions`, so the UI just renders what's legal.
  - **UI:** full-game board (buildings / roads / robber) + both player panels (VP, resource hand, dev cards, knights / longest road / largest army) + action controls (roll, build settlement/city/road, buy dev card, play dev card, move robber & steal, discard, end turn).

- **Incremental steps:**
  1. **Server game-session + bot loop + read-only full-state rendering** (start a game, see the live board + both panels; bot auto-plays its turns).
  2. **Human turn loop:** roll → build (settlement / city / road) → buy / play dev card → robber & discard → end turn. *(Playable end-to-end after this step.)*
  3. **Polish:** bank/port maritime trade actions, win screen, new-game flow, optional time-budgeted search.

- **Exit:** a human can play a complete 1v1 game against the bot in the browser, with the bot responding within a few seconds per turn.

---

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Catanatron can't do 1v1 cleanly / license blocks us | ✅ **Resolved in Phase 0:** MIT license; 2-player + VP=15 + discard=9 native; Friendly Robber injected & tested. Abstraction layer kept; home-grown fallback unused. |
| Random rollouts too weak/slow | Heuristic rollout policy from day one; truncate with a learned value later. |
| Hidden-info handled naively (strategy fusion) | Start with PIMC, upgrade to ISMCTS; keep beliefs tight via the public log. |
| Win-prob numbers look authoritative but are miscalibrated | Calibration is an explicit Phase-4 gate (Brier/reliability), not an afterthought. |
| Wrong opponent model → exploitable advice | Make the opponent model explicit/configurable; benchmark vs several; consider CFR if exploitability matters. |
| Longest-Road bugs (subtle graph rule) | Dedicated property-based tests; cross-check vs Catanatron. |
| Scope creep into 3–4 player / expansions | Explicitly out of scope; revisit only after the 1v1 core is solid. |

---

## 9. Open questions to confirm (§3 `[verify]` items)
1. Does Colonist 1v1 permit **player-to-player trades**? (Affects the trade action space.) — *Phase-0 note:* Catanatron models maritime/port trade only; we proceed **without** domestic trade (a reasonable fit for competitive 1v1, where trading mainly helps your sole opponent), and can add it later if needed.
2. Exact **Friendly-Robber threshold semantics** — strictly "≥3 VP," and does it count hidden VP-card points? (Strategy guide says blockable "after more than 2 points.")
3. Any 1v1 tweaks to **bank size**, **dev-deck composition**, or **ports** vs standard base game (assumed standard unless found otherwise).
4. Discard rounding on a 7 with an odd hand at the 9-card limit (assumed: discard `floor(n/2)` when `n ≥ 10`).

---

## 10. References / prior art
- **Catanatron** — fast Catan engine + AI + Gym env: https://github.com/bcollazo/catanatron · docs: https://docs.catanatron.com · "5 Ways NOT to Build a Catan AI": https://medium.com/@bcollazo2010/5-ways-not-to-build-a-catan-ai-e01bc491af17
- **Colonist 1v1 strategy guide:** https://blog.colonist.io/ranked-1v1-comprehensive-strategy-guide-colonist-io/ · base rules: https://colonist.io/catan-rules
- **ISMCTS** (Cowling, Powley, Whitehouse 2012): https://eprints.whiterose.ac.uk/id/eprint/75048/1/CowlingPowleyWhitehouse2012.pdf
- **MCTS in Settlers of Catan** (Szita, Chaslot, Spronck 2010): https://link.springer.com/chapter/10.1007/978-3-642-12993-3_3
- **Learning to Play Catan with Deep RL:** https://settlers-rl.github.io/
- **Playing Catan with a Cross-dimensional Neural Network** (beats jSettlers): https://www.researchgate.net/publication/343710996_Playing_Catan_with_Cross-dimensional_Neural_Network
- **MCTS — review of modifications & applications** (2021): https://arxiv.org/pdf/2103.04931
- **Simultaneous AlphaZero / tree search for Markov games** (2025): https://arxiv.org/pdf/2512.12486
