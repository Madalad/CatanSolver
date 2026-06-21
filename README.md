# CatanSolver

A solver/advisor for **Colonist.io 1v1** Settlers of Catan: given a game state, it computes the move(s) that maximise your probability of winning. See **[plan.md](plan.md)** for the full spec/roadmap and **[docs/phase0-findings.md](docs/phase0-findings.md)** for the Phase-0 decision memo.

**Status:** Phases 0–2.5 complete — engine + 1v1 rules, opening-placement optimizer, interactive board UI (Advisor), and an opening **practice/drill** mode. The engine extends [Catanatron](https://github.com/bcollazo/catanatron) (MIT).

## Setup (Windows + Anaconda)

The project uses a venv built from Anaconda's Python.

```powershell
# from the repo root
& "C:\Users\ollie\anaconda3\python.exe" -m venv .venv

# IMPORTANT: a venv built from Anaconda lacks OpenSSL on PATH, so pip can't do
# HTTPS. Prepend Anaconda's Library\bin first:
$env:PATH = "C:\Users\ollie\anaconda3\Library\bin;C:\Users\ollie\anaconda3;" + $env:PATH

.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Or just dot-source **`scripts/dev-shell.ps1`**, which sets PATH and activates the venv.

> Notes: `conda` is currently broken on this machine (`HTTP 000`); use `pip` in the venv. Python is 3.9.7.

## Run the tests
```powershell
. .\scripts\dev-shell.ps1   # puts Anaconda's OpenSSL on PATH (the web deps import ssl)
.\.venv\Scripts\python.exe -m pytest -q
```

## Run the UI
```powershell
. .\scripts\dev-shell.ps1
.\.venv\Scripts\python.exe -m uvicorn catansolver.api.app:app --reload
```
Open <http://127.0.0.1:8000/>. Two tabs:

- **Advisor** — the board starts empty; fill it either by **clicking a hex** (a menu sets its resource + number) or by **selecting a paint** and clicking hexes to fill them fast (or hit **Random Board**). Choose your seat, place any existing draft pieces, then click **Analyze** (the **ⓘ** explains it). Each spot shows a **strength score** (higher = better), and the best are highlighted on the board. (A win-% display was trialled but shelved — the only available bots are too weak to give a believable probability; see [docs/heuristic-accuracy.md](docs/heuristic-accuracy.md). It'll return with the Tier-2/3 bot.)
- **Practice** — pick a scenario from the chooser (or random), place your own settlement(s)+road(s) on a generated puzzle (click a piece again to remove it), then **Submit** to see how close to optimal you were, the model move on the board, and a running score/streak (saved in your browser). Each puzzle is scored out of **10** by answer quality (settlements weighted double roads); only a truly optimal answer is "Perfect". Spots are named by their hex numbers (e.g. `5-8-11`) and roads by direction (L/R/U/D).

## Layout
```
catansolver/
  engine/      # Catanatron adapter + RulesConfig + Friendly Robber injection
  io/          # pydantic state schema (manual input + UI/solver API contract)
  placement/   # Tier 1 placement optimizer        (Phase 2)
  advisor/     # Tier 2 turn advisor (PIMC/ISMCTS)  (Phase 3)
  beliefs/     # hidden-info belief tracking         (Phase 3)
  eval/        # heuristics / learned value          (Phases 2-5)
tests/         # pytest suite
spikes/        # reproducible capability spikes
docs/          # phase findings / memos
plan.md        # full spec & roadmap
```
