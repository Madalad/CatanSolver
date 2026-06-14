# Phase 0 — Findings & Decision Memo

Date: 2026-06-14 · Status: ✅ complete

## TL;DR
**Build the solver on top of [Catanatron](https://github.com/bcollazo/catanatron) (MIT-licensed), wrapped behind a thin `catansolver.engine` adapter.** The empirical spike confirmed Catanatron supports everything the Colonist 1v1 ruleset needs *natively* except Friendly Robber, which we injected in ~30 lines and unit-tested. A from-scratch engine is **not** needed.

## Decision: extend Catanatron (high confidence)

### Spike results
| Question | Result |
|---|---|
| License | **MIT** (the draft plan guessed GPL-3.0 — wrong). No redistribution constraints. |
| 2-player | Works out of the box. |
| Board | Standard **19 hexes / 54 nodes / 72 edges**. |
| 15 VP to win | **Native**: `Game(players, vps_to_win=15)`. A full game ran to a 15-VP win. |
| Discard limit 9 | **Native**: `Game(players, discard_limit=9)`. Discard math is `len(hand)//2` when `cards > limit` — exact match to the rule. |
| Friendly Robber | Not native. **Injected & unit-tested** — a visible-VP filter in `robber_possibilities` (`catansolver/engine/friendly_robber.py`). |
| Snake draft | Exactly **P1, P2, P2, P1** (second player places both settlements consecutively) — the MVP structure. |
| Simulation API | `game.copy()` is **independent**; `state.playable_actions`, `game.execute(action)`; rich flat `player_state`. Ready for MC rollouts / MCTS. |
| Trade | **Maritime/port only**; no domestic (player-to-player) trade. Acceptable for competitive 1v1. |
| Speed | "thousands of games/sec" per docs; full random/greedy games run instantly. |

### API we build on
- `Game(players, seed, discard_limit, vps_to_win, catan_map)` → `state.playable_actions`, `game.execute(action)`, `game.winning_color()`, `game.copy()`.
- `Action = (color, action_type, value)`. Action types: ROLL, MOVE_ROBBER, DISCARD, BUILD_{ROAD,SETTLEMENT,CITY}, BUY_DEVELOPMENT_CARD, PLAY_{KNIGHT,YEAR_OF_PLENTY,MONOPOLY,ROAD_BUILDING}, MARITIME_TRADE, END_TURN.
- Flat per-player `player_state` keys: visible + actual VPs, longest-road length, army flag, per-resource hand, dev-card counts.
- Benchmark bots in `catanatron.players` (VictoryPointPlayer + search-based) for evaluation.

## Environment notes (Windows + Anaconda)
- Python is **Anaconda 3.9.7** (`C:\Users\ollie\anaconda3`). The project uses a venv at `.venv`.
- **Gotcha:** a venv built from Anaconda's Python lacks OpenSSL on its path, so `pip` can't do HTTPS (`the ssl module is not available`). Fix: prepend `C:\Users\ollie\anaconda3\Library\bin` to `PATH` (see `scripts/dev-shell.ps1`).
- **`conda` itself is broken on this machine** (`HTTP 000 CONNECTION FAILED`) — we use **pip in the venv**, not conda.
- Python is 3.9.7, not the 3.11+ the plan targeted. 3.9 is fine for the whole near-term stack; revisit only if something needs it.

## What was built in Phase 0
- `catansolver/engine/` — `RulesConfig` (`COLONIST_1V1`), `new_1v1_game()`, Friendly Robber injection (`patch_friendly_robber`).
- `catansolver/io/schema.py` — pydantic state schema (board / player / game + `OpeningPlacementRequest` encoding the three draft seats), with board-legality validation. The contract for manual input and the future UI ↔ solver API.
- `tests/` — **14 tests** (schema validation + Friendly Robber behaviour + config), all green.
- `spikes/catanatron_spike.py` — the reproducible capability spike.

## Open questions (updated)
1. **Domestic trade** — not modeled by Catanatron; proceeding without it for 1v1 (it mostly aids your sole opponent). Revisit if confirmed necessary.
2. **Friendly Robber exact semantics** — implemented as "cannot steal from a player with < 3 *visible* VP". Whether the rule *also* forbids placing the robber to block such a player is still open (plan §9 Q2); it's a one-function change if it does.

## Next: Phase 1
Engine ↔ schema adapter (import a user-specified board into a Catanatron map; export engine state to our schema), Longest-Road cross-check vs Catanatron, and the full rules test suite.
