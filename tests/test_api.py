from fastapi.testclient import TestClient

from catansolver.api.app import app
from catansolver.engine.adapter import adjacent_red_pairs
from catansolver.io.schema import BoardState

client = TestClient(app)


def test_layout_endpoint():
    g = client.get("/api/layout").json()
    assert len(g["hexes"]) == 19
    assert len(g["nodes"]) == 54
    assert len(g["edges"]) == 72
    assert len(g["ports"]) == 9
    assert len(g["hex_adjacency"]) > 0
    assert len(g["node_hexes"]) == 54  # every node maps to its touching hexes
    assert all(1 <= len(v) <= 3 for v in g["node_hexes"].values())


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "CatanSolver" in r.text


def test_random_board_is_valid():
    b = client.get("/api/board/random?seed=1").json()
    assert len(b["hexes"]) == 19 and len(b["ports"]) == 9


def test_recommend_first_seat_heuristic_only():
    board = client.get("/api/board/random?seed=2").json()
    body = {
        "request": {
            "board": board, "seat": "FIRST", "user_color": "P1",
            "settlements": {}, "roads": {},
        },
        "top_k": 5,
        "n_rollouts": 0,
    }
    recs = client.post("/api/recommend", json=body).json()
    assert len(recs) == 5
    assert all(r["win_prob"] is None for r in recs)
    assert all(len(r["placements"]) == 1 for r in recs)


def test_recommend_annotates_calibrated_win_prob():
    # the value model + advisor calibrator live in docs/; the recommend endpoint should
    # annotate each pick with a calibrated opening win-% in (0, 1) (Phase 5.2c).
    board = client.get("/api/board/random?seed=2").json()
    body = {
        "request": {
            "board": board, "seat": "FIRST", "user_color": "P1",
            "settlements": {}, "roads": {},
        },
        "top_k": 4,
    }
    recs = client.post("/api/recommend", json=body).json()
    assert all(r["opening_win_prob"] is not None for r in recs)
    assert all(0.0 <= r["opening_win_prob"] <= 1.0 for r in recs)


def test_recommend_can_disable_win_prob():
    board = client.get("/api/board/random?seed=2").json()
    body = {
        "request": {
            "board": board, "seat": "FIRST", "user_color": "P1",
            "settlements": {}, "roads": {},
        },
        "top_k": 3,
        "win_prob": False,
    }
    recs = client.post("/api/recommend", json=body).json()
    assert all(r["opening_win_prob"] is None for r in recs)


def test_recommend_rejects_invalid_board():
    board = client.get("/api/board/random?seed=3").json()
    idx = next(i for i, h in enumerate(board["hexes"]) if h["resource"] != "DESERT")
    board["hexes"][idx]["number"] = 7  # never a legal token
    body = {
        "request": {
            "board": board, "seat": "FIRST", "user_color": "P1",
            "settlements": {}, "roads": {},
        },
        "top_k": 3,
        "n_rollouts": 0,
    }
    assert client.post("/api/recommend", json=body).status_code == 422


def test_random_board_has_no_adjacent_reds():
    for seed in [0, 1, 2, 3, 4, 5]:
        board = BoardState.model_validate(client.get(f"/api/board/random?seed={seed}").json())
        assert adjacent_red_pairs(board) == []


def test_practice_new_and_grade_roundtrip():
    # generate a FIRST-seat puzzle (no priors), then grade its own model line
    puzzle = client.post("/api/practice/new", json={"seat": "FIRST", "seed": 7}).json()
    assert puzzle["seat"] == "FIRST"
    assert sum(len(v) for v in puzzle["settlements"].values()) == 0

    # any answer to discover the model line, then grade the model line for full marks
    probe = client.post(
        "/api/practice/grade",
        json={"request": puzzle, "placements": [{"settlement": 0, "road": [0, 1]}]},
    ).json()
    model = probe["optimal_placements"]
    result = client.post(
        "/api/practice/grade", json={"request": puzzle, "placements": model}
    ).json()
    assert result["all_correct"] is True
    assert result["is_optimal"] is True
    assert result["total_awarded"] == result["total_max"] == 10.0
    # the practice grade is annotated with calibrated win-% for the user's line and the
    # model's line; grading the model line, both should be present and in (0, 1) (Phase 5.2c)
    assert result["user_win_prob"] is not None and 0.0 <= result["user_win_prob"] <= 1.0
    assert result["optimal_win_prob"] is not None and 0.0 <= result["optimal_win_prob"] <= 1.0


def test_practice_new_second_seat_has_one_prior():
    puzzle = client.post("/api/practice/new", json={"seat": "SECOND", "seed": 5}).json()
    assert puzzle["seat"] == "SECOND"
    assert sum(len(v) for v in puzzle["settlements"].values()) == 1
