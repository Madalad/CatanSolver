"""Phase 4.1 — round-robin tournament + Elo ratings.

Builds on :func:`catansolver.eval.arena.play_match`: every pair of entrants plays a
balanced match, and the pooled results are turned into **Elo ratings** so a whole field
(random / heuristic / search / our advisor) lands on one comparable scale.

Elo here is the Bradley-Terry model — ``P(i beats j) = γ_i / (γ_i + γ_j)`` — fit by
maximum likelihood with the standard Hunter (2004) MM iteration, then mapped to the Elo
scale (``400·log10 γ``, mean anchored to 1500). Draws count as half a win to each side.
Ratings are identifiable as long as the results graph is connected and no entrant goes
winless/lossless against the field (true for any field that includes RandomPlayer).
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

from catansolver.engine import COLONIST_1V1, RulesConfig
from catansolver.eval.arena import MatchResult, PlayerFactory, play_match
from catansolver.placement.rollout import wilson_interval

Entrant = Tuple[str, PlayerFactory]
_ELO_ANCHOR = 1500.0


@dataclass
class Standing:
    name: str
    wins: int
    losses: int
    draws: int
    elo: float

    @property
    def games(self) -> int:
        return self.wins + self.losses + self.draws

    @property
    def score(self) -> float:
        return self.wins + 0.5 * self.draws  # draws count half

    @property
    def win_rate(self) -> float:
        return self.score / self.games if self.games else 0.0

    @property
    def ci(self) -> Tuple[float, float]:
        return wilson_interval(int(round(self.score)), self.games)


@dataclass
class TournamentResult:
    standings: List[Standing]  # sorted by Elo, best first
    matrix: Dict[Tuple[str, str], MatchResult]  # (A, B) -> A's record vs B


def fit_elo(
    names: List[str],
    decisive: Dict[Tuple[str, str], Tuple[float, float]],
    iterations: int = 2000,
    anchor: float = _ELO_ANCHOR,
) -> Dict[str, float]:
    """Bradley-Terry MLE via MM iteration, returned on the Elo scale.

    ``decisive[(a, b)] = (a_score, b_score)`` are the (draw-adjusted) scores between a
    and b; only unordered pairs need appear. Mean Elo is anchored to ``anchor``.
    """
    wins: Dict[str, float] = {n: 0.0 for n in names}
    games: Dict[str, Dict[str, float]] = {n: {m: 0.0 for m in names} for n in names}
    for (a, b), (sa, sb) in decisive.items():
        wins[a] += sa
        wins[b] += sb
        games[a][b] += sa + sb
        games[b][a] += sa + sb

    gamma = {n: 1.0 for n in names}
    for _ in range(iterations):
        nxt = {}
        for i in names:
            denom = sum(
                games[i][j] / (gamma[i] + gamma[j])
                for j in names
                if j != i and games[i][j] > 0
            )
            nxt[i] = wins[i] / denom if denom > 0 and wins[i] > 0 else gamma[i]
        geo_mean = math.exp(sum(math.log(max(v, 1e-12)) for v in nxt.values()) / len(nxt))
        gamma = {n: nxt[n] / geo_mean for n in names}

    return {n: anchor + 400.0 * math.log10(max(gamma[n], 1e-12)) for n in names}


def run_tournament(
    entrants: List[Entrant],
    n_games: int,
    rules: RulesConfig = COLONIST_1V1,
    seed: int = 0,
    workers: int = 1,
) -> TournamentResult:
    """Round-robin: each pair plays ``n_games`` (balanced seats/colours). Returns
    per-entrant standings with Elo plus the full pairwise result matrix."""
    tally = {name: [0, 0, 0] for name, _ in entrants}  # wins, losses, draws
    matrix: Dict[Tuple[str, str], MatchResult] = {}
    decisive: Dict[Tuple[str, str], Tuple[float, float]] = {}

    for i, ((na, fa), (nb, fb)) in enumerate(itertools.combinations(entrants, 2)):
        res = play_match(fa, fb, n_games, rules=rules, seed=seed + i * n_games, workers=workers)
        matrix[(na, nb)] = res
        tally[na][0] += res.a_wins; tally[na][1] += res.b_wins; tally[na][2] += res.draws
        tally[nb][0] += res.b_wins; tally[nb][1] += res.a_wins; tally[nb][2] += res.draws
        decisive[(na, nb)] = (res.a_wins + 0.5 * res.draws, res.b_wins + 0.5 * res.draws)

    elos = fit_elo([n for n, _ in entrants], decisive)
    standings = [Standing(name, *tally[name], elo=elos[name]) for name, _ in entrants]
    standings.sort(key=lambda s: s.elo, reverse=True)
    return TournamentResult(standings=standings, matrix=matrix)
