"""Phase 3.5: the evaluation arena. Short games (low VP target) + tiny search settings
keep these fast while exercising the AdvisorPlayer end-to-end and the match harness."""
import random

from catanatron import Color, RandomPlayer

from catansolver.engine import RulesConfig
from catansolver.eval import AdvisorPlayer, MatchResult, play_match
from catansolver.eval.arena import _normalize

_RULES = RulesConfig(vps_to_win=4)  # very short games


def _advisor(color):
    return AdvisorPlayer(color, n_determinizations=1, iterations=6, rollout_depth=6, rules=_RULES)


def test_advisor_plays_a_legal_game_to_completion():
    random.seed(0)
    from catansolver.engine import new_1v1_game

    game = new_1v1_game([_advisor(Color.RED), RandomPlayer(Color.BLUE)], rules=_RULES, seed=0)
    winner = game.play()
    assert winner in (Color.RED, Color.BLUE, None)  # finished without raising
    assert game.state.num_turns > 0


def test_play_match_record_is_consistent():
    res = play_match(_advisor, RandomPlayer, n_games=2, rules=_RULES, seed=2)
    assert isinstance(res, MatchResult)
    assert res.a_wins + res.b_wins + res.draws == res.n_games == 2
    assert 0.0 <= res.a_winrate <= 1.0
    lo, hi = res.ci
    assert 0.0 <= lo <= res.a_winrate <= hi <= 1.0


def test_match_result_significance_flag():
    # a clean sweep should read as significant; a single game cannot
    assert MatchResult(a_wins=30, b_wins=0, draws=0).significant
    assert not MatchResult(a_wins=1, b_wins=0, draws=0).significant


def test_normalize_tuples_to_lists():
    assert _normalize((1, 2)) == [1, 2]
    assert _normalize(("WOOD", ("a", "b"))) == ["WOOD", ["a", "b"]]
    assert _normalize(5) == 5


def test_parallel_match_runs_and_counts(tmp_path):
    # cheap picklable players exercise the ProcessPoolExecutor path on Windows (spawn)
    from catanatron.players.weighted_random import WeightedRandomPlayer

    res = play_match(RandomPlayer, WeightedRandomPlayer, n_games=4, rules=_RULES,
                     seed=7, workers=2)
    assert res.n_games == 4
    assert res.a_wins + res.b_wins + res.draws == 4
