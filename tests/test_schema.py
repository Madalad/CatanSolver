import pytest
from pydantic import ValidationError

from catansolver.io.examples import example_board
from catansolver.io.schema import (
    BoardState,
    DraftSeat,
    GameState,
    OpeningPlacementRequest,
    PlayerState,
)


def test_example_board_is_valid():
    board = example_board()
    assert len(board.hexes) == 19
    assert len(board.ports) == 9


def test_board_json_roundtrip():
    board = example_board()
    restored = BoardState.model_validate_json(board.model_dump_json())
    assert restored == board


def test_bad_resource_composition_is_rejected():
    data = example_board().model_dump(mode="json")
    data["hexes"][0]["resource"] = "ORE"  # 4 ore / 3 wood -> wrong multiset
    with pytest.raises(ValidationError):
        BoardState.model_validate(data)


def test_seven_token_is_rejected():
    data = example_board().model_dump(mode="json")
    for hex_ in data["hexes"]:
        if hex_["resource"] != "DESERT":
            hex_["number"] = 7
            break
    with pytest.raises(ValidationError):
        BoardState.model_validate(data)


def test_desert_with_number_is_rejected():
    data = example_board().model_dump(mode="json")
    for hex_ in data["hexes"]:
        if hex_["resource"] == "DESERT":
            hex_["number"] = 6
            break
    with pytest.raises(ValidationError):
        BoardState.model_validate(data)


def test_game_state_requires_two_players():
    board = example_board()
    with pytest.raises(ValidationError):
        GameState(board=board, players=[PlayerState(color="P1")], current_player="P1")


def test_game_state_current_player_must_exist():
    board = example_board()
    players = [PlayerState(color="P1"), PlayerState(color="P2")]
    with pytest.raises(ValidationError):
        GameState(board=board, players=players, current_player="P3")


def test_opening_request_seat_consistency():
    board = example_board()
    # SECOND seat: exactly one (opponent) settlement must already be placed.
    with pytest.raises(ValidationError):
        OpeningPlacementRequest(board=board, seat=DraftSeat.SECOND, user_color="P2")

    ok = OpeningPlacementRequest(
        board=board,
        seat=DraftSeat.SECOND,
        user_color="P2",
        settlements={"P1": [10]},
        roads={"P1": [(10, 11)]},
    )
    assert ok.seat == DraftSeat.SECOND


def test_opening_request_first_seat_empty_board():
    board = example_board()
    ok = OpeningPlacementRequest(board=board, seat=DraftSeat.FIRST, user_color="P1")
    assert ok.user_color == "P1"
    with pytest.raises(ValidationError):
        OpeningPlacementRequest(
            board=board, seat=DraftSeat.FIRST, user_color="P1", settlements={"P1": [3]}
        )
