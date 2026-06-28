r"""FastAPI app: serves the solver over the state schema + the interactive board UI.

Run: .\.venv\Scripts\python.exe -m uvicorn catansolver.api.app:app --reload
then open http://127.0.0.1:8000/
"""

from __future__ import annotations

import random
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from catanatron.models.map import BASE_MAP_TEMPLATE, CatanMap

from catansolver.engine.adapter import adjacent_red_pairs, map_to_schema
from catansolver.engine.spiral import apply_spiral_numbers
from catansolver.io.schema import (
    BoardState,
    DraftSeat,
    OpeningPlacementRequest,
    Placement,
    PracticeResult,
    Recommendation,
)
from catansolver.placement import generate_puzzle, grade_practice, opening_win_prob_gap, recommend_opening

from .geometry import board_geometry

STATIC_DIR = Path(__file__).parent / "static"
DOCS_DIR = Path(__file__).resolve().parents[2] / "docs"

app = FastAPI(title="CatanSolver", description="Colonist.io 1v1 opening-placement advisor")

# --------------------------------------------------------------------------- #
# Calibrated opening win-% (Phase 5.2c)
# --------------------------------------------------------------------------- #
# The win-% display was shelved in Phase 2 because the only number we could produce was a
# rollout-vs-weak-bot estimate that read ~96% where strong humans win ~44%. We surface an
# honest "≈X% vs an equal-strength bot" from the **heuristic opening-strength gap** mapped
# through a logistic (docs/opening_gap_model.json): at the opening the purpose-built
# production score out-predicts the learned value model (Brier 0.155 vs 0.195).
# The remaining draft picks (the opponent's, and the user's tail pick) are completed at the
# bot's **best** opening, not a random one — without that the optimized pick faced an
# artificially weak opponent and the number inflated to ~80%. With realistic completion the
# gap model self-centres (best opening ≈51% first / ≈45% second, max ~60%), close to the
# ~56/44 first-mover edge seen in elite 1v1 play, so no extra scaling is applied.
WINPROB_SAMPLES = 1  # the optimal-completion is deterministic, so one pass suffices (~10ms)
WINPROB_LABEL = "vs an equal-strength bot"


@lru_cache(maxsize=1)
def _opening_model():
    """Load the opening-gap win-% model once, or ``None`` if the artifact is absent — in
    which case the win-% is simply omitted and the UI falls back to scores."""
    try:
        from catansolver.learn import ValueModel  # the gap model is a 1-feature logistic

        return ValueModel.load(str(DOCS_DIR / "opening_gap_model.json"))
    except Exception:  # missing/unreadable artifact — degrade gracefully
        return None


def _win_prob(request: OpeningPlacementRequest, placements: List[Placement]) -> Optional[float]:
    """Calibrated P(user wins) for an opening, or ``None`` if the model is unavailable.
    ``placements`` has length 1 for FIRST/FIRST_FINAL, 2 for the SECOND seat's pair."""
    gap_model = _opening_model()
    if gap_model is None or not placements:
        return None
    pls = [(p.settlement, tuple(p.road)) for p in placements]
    try:
        return opening_win_prob_gap(request, pls, gap_model, n_samples=WINPROB_SAMPLES)
    except Exception:
        return None


@app.get("/api/layout")
def get_layout() -> dict:
    """Fixed board geometry (pixel positions for hexes/nodes/edges/ports)."""
    return board_geometry()


@app.get("/api/board/random", response_model=BoardState)
def get_random_board(seed: Optional[int] = None) -> BoardState:
    """A valid random board (resources/numbers/ports), to start from or sanity-check."""
    # Always reseed: ``seed=None`` reseeds from OS entropy, so board generation is a fresh
    # draw immune to any *pinned* global RNG left behind by other code (e.g. the opening
    # win-% calc seeds games with fixed seeds — that used to make practice boards repeat).
    random.seed(seed)
    # Terrain is shuffled by Catanatron; numbers follow the canonical **spiral** sequence
    # (apply_spiral_numbers) with a random start hex + direction, matching the physical game.
    # The spiral keeps reds spread, but a randomly-placed desert can still abut two reds, so
    # resample terrain + orientation until no adjacent 6/8 (or give up after a cap).
    board = apply_spiral_numbers(map_to_schema(CatanMap.from_template(BASE_MAP_TEMPLATE)))
    for _ in range(200):
        if not adjacent_red_pairs(board):
            break
        board = apply_spiral_numbers(map_to_schema(CatanMap.from_template(BASE_MAP_TEMPLATE)))
    return board


class RecommendBody(BaseModel):
    request: OpeningPlacementRequest
    top_k: int = Field(default=6, ge=1, le=20)
    n_rollouts: int = Field(default=0, ge=0, le=200)  # 0 = instant heuristic ranking
    win_prob: bool = True  # annotate each pick with the calibrated opening win-%


@app.post("/api/recommend", response_model=List[Recommendation])
def post_recommend(body: RecommendBody) -> List[Recommendation]:
    """Heuristic-ranked opening recommendations, each annotated (when ``win_prob``) with the
    calibrated learned-value opening win-% vs an equal-strength bot. Ranking stays heuristic;
    the win-% is the value model's independent read of the same picks."""
    recs = recommend_opening(body.request, top_k=body.top_k, n_rollouts=body.n_rollouts)
    if body.win_prob:
        for rec in recs:
            rec.opening_win_prob = _win_prob(body.request, rec.placements)
    return recs


# --------------------------------------------------------------------------- #
# Practice mode (Phase 2.5)
# --------------------------------------------------------------------------- #
_PRACTICE_SEATS = [DraftSeat.FIRST, DraftSeat.SECOND, DraftSeat.FIRST_FINAL]


class PracticeNewBody(BaseModel):
    seat: str = "RANDOM"  # FIRST | SECOND | FIRST_FINAL | RANDOM
    seed: Optional[int] = None
    board: Optional[BoardState] = None  # reuse this board (same-board practice); else random


class PracticeGradeBody(BaseModel):
    request: OpeningPlacementRequest
    placements: List[Placement]  # the user's chosen settlement(s)+road(s): 1, or 2 for SECOND


@app.post("/api/practice/new", response_model=OpeningPlacementRequest)
def post_practice_new(body: PracticeNewBody) -> OpeningPlacementRequest:
    """A fresh practice puzzle: a valid random board plus policy-generated priors
    for the chosen seat (or a random seat). The user must place what the seat asks."""
    seat = random.choice(_PRACTICE_SEATS) if body.seat == "RANDOM" else DraftSeat(body.seat)
    board = body.board if body.board is not None else get_random_board(body.seed)
    return generate_puzzle(board, seat, seed=body.seed)


@app.post("/api/practice/grade", response_model=PracticeResult)
def post_practice_grade(body: PracticeGradeBody) -> PracticeResult:
    """Grade the user's opening (heuristic, instant) and annotate it with the calibrated
    learned-value win-% for both the user's line and the model's optimal line — so the
    feedback can say "your opening ≈X%, the model's ≈Y% (vs an equal-strength bot)"."""
    result = grade_practice(body.request, body.placements)
    result.user_win_prob = _win_prob(body.request, body.placements)
    result.optimal_win_prob = _win_prob(body.request, result.optimal_placements)
    # Annotate each of the solver's top picks with the same calibrated win-% the advisor
    # shows, so the practice "top picks" list reads consistently with the advisor tab.
    for rec in result.ranking:
        rec.opening_win_prob = _win_prob(body.request, rec.placements)
    return result


@app.get("/")
def index() -> HTMLResponse:
    # Stamp app.js with its mtime so the browser refetches it whenever it changes
    # (StaticFiles caches aggressively otherwise — stale JS is a recurring footgun).
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    version = int((STATIC_DIR / "app.js").stat().st_mtime)
    html = html.replace("/static/app.js", f"/static/app.js?v={version}")
    return HTMLResponse(html)


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
