r"""FastAPI app: serves the solver over the state schema + the interactive board UI.

Run: .\.venv\Scripts\python.exe -m uvicorn catansolver.api.app:app --reload
then open http://127.0.0.1:8000/
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from catanatron.models.map import BASE_MAP_TEMPLATE, CatanMap

from catansolver.engine.adapter import adjacent_red_pairs, map_to_schema
from catansolver.io.schema import (
    BoardState,
    DraftSeat,
    OpeningPlacementRequest,
    Placement,
    PracticeResult,
    Recommendation,
)
from catansolver.placement import generate_puzzle, grade_practice, recommend_opening

from .geometry import board_geometry

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="CatanSolver", description="Colonist.io 1v1 opening-placement advisor")


@app.get("/api/layout")
def get_layout() -> dict:
    """Fixed board geometry (pixel positions for hexes/nodes/edges/ports)."""
    return board_geometry()


@app.get("/api/board/random", response_model=BoardState)
def get_random_board(seed: Optional[int] = None) -> BoardState:
    """A valid random board (resources/numbers/ports), to start from or sanity-check."""
    if seed is not None:
        random.seed(seed)
    # Catanatron shuffles numbers freely; official setup forbids adjacent red (6/8)
    # numbers, so resample until the board complies (or give up after a cap).
    board = map_to_schema(CatanMap.from_template(BASE_MAP_TEMPLATE))
    for _ in range(200):
        if not adjacent_red_pairs(board):
            break
        board = map_to_schema(CatanMap.from_template(BASE_MAP_TEMPLATE))
    return board


class RecommendBody(BaseModel):
    request: OpeningPlacementRequest
    top_k: int = Field(default=6, ge=1, le=20)
    n_rollouts: int = Field(default=0, ge=0, le=200)  # 0 = instant heuristic ranking


@app.post("/api/recommend", response_model=List[Recommendation])
def post_recommend(body: RecommendBody) -> List[Recommendation]:
    return recommend_opening(body.request, top_k=body.top_k, n_rollouts=body.n_rollouts)


# --------------------------------------------------------------------------- #
# Practice mode (Phase 2.5)
# --------------------------------------------------------------------------- #
_PRACTICE_SEATS = [DraftSeat.FIRST, DraftSeat.SECOND, DraftSeat.FIRST_FINAL]


class PracticeNewBody(BaseModel):
    seat: str = "RANDOM"  # FIRST | SECOND | FIRST_FINAL | RANDOM
    seed: Optional[int] = None


class PracticeGradeBody(BaseModel):
    request: OpeningPlacementRequest
    placements: List[Placement]  # the user's chosen settlement(s)+road(s): 1, or 2 for SECOND


@app.post("/api/practice/new", response_model=OpeningPlacementRequest)
def post_practice_new(body: PracticeNewBody) -> OpeningPlacementRequest:
    """A fresh practice puzzle: a valid random board plus policy-generated priors
    for the chosen seat (or a random seat). The user must place what the seat asks."""
    seat = random.choice(_PRACTICE_SEATS) if body.seat == "RANDOM" else DraftSeat(body.seat)
    board = get_random_board(body.seed)
    return generate_puzzle(board, seat, seed=body.seed)


@app.post("/api/practice/grade", response_model=PracticeResult)
def post_practice_grade(body: PracticeGradeBody) -> PracticeResult:
    return grade_practice(body.request, body.placements)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
