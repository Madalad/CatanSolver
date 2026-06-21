"""Phase 3.5 — strength evaluation: play the advisor head-to-head against baselines.

Wraps the PIMC turn advisor as a Catanatron :class:`Player` (:class:`AdvisorPlayer`)
and runs balanced matches (:func:`play_match`) against reference bots, reporting
win-rate with a Wilson CI. The Phase-3 exit criterion is that the advisor beats
random / heuristic / VP baselines by a statistically significant margin.

`AdvisorPlayer` only drives ordinary **PLAY_TURN** decisions through the advisor;
forced moves are returned directly, and the prompts our `GameState` schema doesn't
capture (initial placement, discard, move-robber) fall back to a fast WeightedRandom
policy. That's an honest limitation of the position schema, not the search — robber /
discard advice waits on a finer-grained prompt capture.
"""
from __future__ import annotations

# Cap native BLAS/OMP threads *before* numpy is imported (transitively, via catanatron)
# so the per-process pool doesn't oversubscribe cores when games run in parallel.
import os

for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Callable, Tuple

from catanatron import Color, Player
from catanatron.models.enums import ActionPrompt
from catanatron.players.weighted_random import WeightedRandomPlayer

from catansolver.advisor import recommend_actions_ismcts, recommend_actions_pimc
from catansolver.engine import COLONIST_1V1, RulesConfig, game_to_state, new_1v1_game
from catansolver.placement.rollout import wilson_interval

PlayerFactory = Callable[[Color], Player]
# Initial-build placement is the opening solver's domain; everything else in PLAY
# (PLAY_TURN, MOVE_ROBBER, and any multi-option DISCARD) is advisor-driven.
_FALLBACK_PROMPTS = {ActionPrompt.BUILD_INITIAL_SETTLEMENT, ActionPrompt.BUILD_INITIAL_ROAD}


def _normalize(value):
    """Match Catanatron action values (tuples) against recommendation values (lists)."""
    if isinstance(value, tuple):
        return [_normalize(v) for v in value]
    return value


class AdvisorPlayer(Player):
    """A Catanatron player driven by the Phase-3 turn advisor (PIMC or ISMCTS).

    ``method="pimc"`` uses ``n_determinizations`` trees of ``iterations`` UCT iters each;
    ``method="ismcts"`` uses a single tree of ``n_determinizations * iterations`` iters
    (same total budget) re-determinized per iteration.
    """

    def __init__(self, color, n_determinizations=3, iterations=40, rollout_depth=12,
                 method="pimc", rules: RulesConfig = COLONIST_1V1, is_bot=True):
        super().__init__(color, is_bot)
        self.n_determinizations = n_determinizations
        self.iterations = iterations
        self.rollout_depth = rollout_depth
        self.method = method
        self.rules = rules
        self._fallback = WeightedRandomPlayer(color)
        self._decisions = 0
        #: win-prob the advisor assigned to each move it actually chose (for calibration)
        self.predictions: list = []

    def decide(self, game, playable_actions):
        actions = list(playable_actions)
        if len(actions) == 1:
            return actions[0]
        if game.state.current_prompt in _FALLBACK_PROMPTS:
            return self._fallback.decide(game, actions)  # initial-build placement

        self._decisions += 1
        gs = game_to_state(game, rules=self.rules)  # captures prompt + has_rolled

        # the advisor's rollouts consume the global RNG; snapshot/restore it so they
        # don't perturb the real game's dice stream.
        rng_state = random.getstate()
        try:
            if self.method == "ismcts":
                recs = recommend_actions_ismcts(
                    gs,
                    iterations=self.n_determinizations * self.iterations,
                    rollout_depth=self.rollout_depth,
                    rules=self.rules,
                    seed=self._decisions,
                )
            else:
                recs = recommend_actions_pimc(
                    gs,
                    n_determinizations=self.n_determinizations,
                    iterations=self.iterations,
                    rollout_depth=self.rollout_depth,
                    rules=self.rules,
                    seed=self._decisions,
                )
        finally:
            random.setstate(rng_state)

        for rec in recs:
            for a in actions:
                if a.action_type.value == rec.action_type and _normalize(a.value) == rec.value:
                    self.predictions.append(rec.win_prob)  # P(win) it assigned this move
                    return a
        return self._fallback.decide(game, actions)  # no rec matched (shouldn't happen)


@dataclass
class MatchResult:
    """Outcome of a match from player A's perspective."""

    a_wins: int
    b_wins: int
    draws: int

    @property
    def n_games(self) -> int:
        return self.a_wins + self.b_wins + self.draws

    @property
    def a_winrate(self) -> float:
        return self.a_wins / self.n_games if self.n_games else 0.0

    @property
    def ci(self) -> Tuple[float, float]:
        return wilson_interval(self.a_wins, self.n_games)

    @property
    def significant(self) -> bool:
        """Win-rate significantly above 50% (Wilson lower bound clears one-half)."""
        return self.ci[0] > 0.5


def _play_one_game(a_factory, b_factory, i, rules, seed) -> int:
    """Play game ``i``, alternating which factory is seated first / which colour A holds.
    Returns +1 if A wins, -1 if B wins, 0 for a draw."""
    random.seed(seed + i)
    if i % 2 == 0:  # A seated first (RED)
        players = [a_factory(Color.RED), b_factory(Color.BLUE)]
        a_color = Color.RED
    else:  # A seated second (BLUE)
        players = [b_factory(Color.RED), a_factory(Color.BLUE)]
        a_color = Color.BLUE

    winner = new_1v1_game(players, rules=rules, seed=seed + i).play()
    return 1 if winner == a_color else (0 if winner is None else -1)


def play_match(
    a_factory: PlayerFactory,
    b_factory: PlayerFactory,
    n_games: int,
    rules: RulesConfig = COLONIST_1V1,
    seed: int = 0,
    workers: int = 1,
) -> MatchResult:
    """Play ``n_games`` between factories A and B, alternating seat + colour each game so
    A and B share first-move and board luck evenly. Returns A's record.

    ``workers > 1`` plays games across processes (``ProcessPoolExecutor``); the factories
    and ``rules`` must then be picklable (use module-level callables / ``functools.partial``,
    not lambdas)."""
    if workers <= 1:
        outcomes = [_play_one_game(a_factory, b_factory, i, rules, seed) for i in range(n_games)]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            outcomes = list(pool.map(
                _play_one_game,
                *zip(*[(a_factory, b_factory, i, rules, seed) for i in range(n_games)]),
            ))
    return MatchResult(
        a_wins=outcomes.count(1), b_wins=outcomes.count(-1), draws=outcomes.count(0)
    )
