"""Phase 4.1: round-robin tournament + Elo. The Elo math is tested deterministically on
synthetic results; a small live round-robin checks the harness end-to-end."""
from catanatron import RandomPlayer
from catanatron.players.weighted_random import WeightedRandomPlayer

from catansolver.engine import RulesConfig
from catansolver.eval import fit_elo, run_tournament

_RULES = RulesConfig(vps_to_win=4)  # short games


def test_fit_elo_orders_by_strength_and_anchors_mean():
    names = ["A", "B", "C"]
    decisive = {
        ("A", "B"): (9.0, 1.0),  # A >> B
        ("B", "C"): (9.0, 1.0),  # B >> C
        ("A", "C"): (10.0, 0.0),  # A >>> C
    }
    elo = fit_elo(names, decisive)
    assert elo["A"] > elo["B"] > elo["C"]
    assert abs(sum(elo.values()) / 3 - 1500.0) < 1e-6  # mean anchored to 1500


def test_fit_elo_equal_strength_is_flat():
    elo = fit_elo(["A", "B"], {("A", "B"): (5.0, 5.0)})
    assert abs(elo["A"] - elo["B"]) < 1e-6
    assert abs(elo["A"] - 1500.0) < 1e-6


def test_elo_gap_matches_win_rate():
    import math

    # a 75% head-to-head score is a 400*log10(0.75/0.25) ~= 191 Elo gap
    elo = fit_elo(["A", "B"], {("A", "B"): (75.0, 25.0)})
    expected = 400 * math.log10(0.75 / 0.25)
    assert abs((elo["A"] - elo["B"]) - expected) < 1.0


def test_run_tournament_is_wellformed():
    entrants = [("rand", RandomPlayer), ("weighted", WeightedRandomPlayer)]
    res = run_tournament(entrants, n_games=4, rules=_RULES, seed=1)
    assert len(res.standings) == 2
    assert len(res.matrix) == 1  # one unordered pair
    for s in res.standings:
        assert s.games == 4
        assert s.wins + s.losses + s.draws == 4
        assert 0.0 <= s.win_rate <= 1.0
        lo, hi = s.ci
        assert 0.0 <= lo <= hi <= 1.0
    # standings sorted by Elo, best first
    assert res.standings[0].elo >= res.standings[-1].elo
    assert abs(sum(s.elo for s in res.standings) / 2 - 1500.0) < 1e-6
