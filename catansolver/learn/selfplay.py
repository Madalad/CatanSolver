"""Self-play data generation for the value model (Phase 5.1b).

Plays games (WeightedRandom by default — fast and produces realistic positions, the same
policy the rollouts use) and records ``(features, outcome)`` at sampled mid-game PLAY_TURN
states. Each sampled state is recorded **from both players' perspectives**, so exactly one
label is a win and one a loss — the dataset is balanced by construction.
"""
from __future__ import annotations

# cap native threads before numpy is imported, so the process pool doesn't oversubscribe
import os

for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import random
from concurrent.futures import ProcessPoolExecutor
from typing import Callable, List, Tuple

import numpy as np
from catanatron import Color, Player
from catanatron.models.enums import ActionPrompt
from catanatron.players.weighted_random import WeightedRandomPlayer

from catansolver.engine import COLONIST_1V1, RulesConfig, new_1v1_game

from .features import FEATURE_NAMES, extract_features

PlayerFactory = Callable[[Color], Player]


def _weighted(color: Color) -> Player:
    return WeightedRandomPlayer(color)


def generate_dataset(
    n_games: int,
    player_factory: PlayerFactory = _weighted,
    rules: RulesConfig = COLONIST_1V1,
    seed: int = 0,
    sample_every: int = 6,
    min_tick: int = 10,
    max_ticks: int = 2000,
) -> Tuple[np.ndarray, np.ndarray]:
    """Return ``(X, y)`` — features and {0,1} win labels — from ``n_games`` self-play
    games. States are sampled every ``sample_every`` ticks from ``min_tick`` on (skipping
    the opening), at PLAY_TURN only.

    ``max_ticks`` is in *actions*, not turns: weak self-play to 15 VP runs long (≈450-1600
    actions), so the cap is generous to avoid discarding unfinished games."""
    rows = []
    labels = []
    for i in range(n_games):
        random.seed(seed + i)
        game = new_1v1_game(
            [player_factory(Color.RED), player_factory(Color.BLUE)], rules=rules, seed=seed + i
        )
        snapshots = []
        tick = 0
        while game.winning_color() is None and tick < max_ticks:
            if (
                tick >= min_tick
                and tick % sample_every == 0
                and game.state.current_prompt == ActionPrompt.PLAY_TURN
            ):
                for color in game.state.colors:
                    snapshots.append((color, extract_features(game, color)))
            game.play_tick()
            tick += 1

        winner = game.winning_color()
        if winner is None:  # draw / turn-limit — no label
            continue
        for color, feats in snapshots:
            rows.append(feats)
            labels.append(1.0 if color == winner else 0.0)

    if not rows:
        return np.empty((0, len(FEATURE_NAMES))), np.empty((0,))
    return np.asarray(rows, dtype=float), np.asarray(labels, dtype=float)


def collect_opening_samples(
    value_model,
    n_games: int,
    player_factory: PlayerFactory = _weighted,
    rules: RulesConfig = COLONIST_1V1,
    seed: int = 0,
    max_ticks: int = 2000,
):
    """For each game, evaluate the value model at the **first PLAY state** (the position
    right after the snake draft completes) for both colours, then play to the end and
    label by the winner. Returns ``[(predicted_p, outcome)]`` — exactly the pairs needed
    to calibrate an *opening* win-probability."""
    samples = []
    for i in range(n_games):
        random.seed(seed + i)
        game = new_1v1_game(
            [player_factory(Color.RED), player_factory(Color.BLUE)], rules=rules, seed=seed + i
        )
        while game.state.is_initial_build_phase and game.winning_color() is None:
            game.play_tick()
        if game.winning_color() is not None:  # (shouldn't happen during the draft)
            continue
        opening = {c: value_model(extract_features(game, c)) for c in game.state.colors}

        tick = 0
        while game.winning_color() is None and tick < max_ticks:
            game.play_tick()
            tick += 1
        winner = game.winning_color()
        if winner is None:
            continue
        for color, p in opening.items():
            samples.append((p, 1.0 if color == winner else 0.0))
    return samples


def _opening_game(value_model_path, player_factory, rules, seed, max_ticks):
    """One opening-sample game (loads its own value model so it's process-safe)."""
    from .value_model import ValueModel

    vm = ValueModel.load(value_model_path)
    random.seed(seed)
    game = new_1v1_game(
        [player_factory(Color.RED), player_factory(Color.BLUE)], rules=rules, seed=seed
    )
    while game.state.is_initial_build_phase and game.winning_color() is None:
        game.play_tick()
    if game.winning_color() is not None:
        return []
    opening = {c: vm(extract_features(game, c)) for c in game.state.colors}

    tick = 0
    while game.winning_color() is None and tick < max_ticks:
        game.play_tick()
        tick += 1
    winner = game.winning_color()
    if winner is None:
        return []
    return [(p, 1.0 if c == winner else 0.0) for c, p in opening.items()]


def collect_opening_samples_parallel(
    value_model_path: str,
    player_factory: PlayerFactory,
    n_games: int,
    rules: RulesConfig = COLONIST_1V1,
    seed: int = 0,
    workers: int = 6,
    max_ticks: int = 2000,
) -> List[Tuple[float, float]]:
    """Parallel :func:`collect_opening_samples`. ``value_model_path`` and
    ``player_factory`` must be picklable (path string + e.g. ``functools.partial`` over a
    Player class) since games run across processes."""
    if workers <= 1:
        args = [(value_model_path, player_factory, rules, seed + i, max_ticks) for i in range(n_games)]
        return [s for a in args for s in _opening_game(*a)]
    samples: List[Tuple[float, float]] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = pool.map(
            _opening_game,
            *zip(*[(value_model_path, player_factory, rules, seed + i, max_ticks)
                   for i in range(n_games)]),
        )
        for res in results:
            samples.extend(res)
    return samples
