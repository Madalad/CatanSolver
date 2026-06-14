# CatanSolver

A solver/advisor for **Colonist.io 1v1** Settlers of Catan: given a game state, it computes the move(s) that maximise your probability of winning. See **[plan.md](plan.md)** for the full spec/roadmap and **[docs/phase0-findings.md](docs/phase0-findings.md)** for the Phase-0 decision memo.

**Status:** Phase 0 complete (foundations + engine choice). The engine extends [Catanatron](https://github.com/bcollazo/catanatron) (MIT).

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
.\.venv\Scripts\python.exe -m pytest -q
```

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
