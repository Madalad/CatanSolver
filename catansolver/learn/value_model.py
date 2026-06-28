"""Numpy-only logistic value model (Phase 5.1).

Fits P(win) from position features by L2-regularised logistic regression (Newton/IRLS) —
no sklearn/torch. Features are standardised internally, so the saved model is just a mean,
std, intercept and coefficient vector; it serialises to JSON and evaluates as a single
dot product (fast enough to call at every MCTS leaf).
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))


@dataclass
class ValueModel:
    mean: np.ndarray  # per-feature standardisation
    std: np.ndarray
    intercept: float
    coef: np.ndarray

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=float)
        z = self.intercept + ((X - self.mean) / self.std) @ self.coef
        return _sigmoid(z)

    def __call__(self, features: np.ndarray) -> float:
        """P(win) for a single feature vector."""
        return float(self.predict_proba(np.asarray(features, float)[None, :])[0])

    def to_dict(self) -> dict:
        return {
            "mean": self.mean.tolist(),
            "std": self.std.tolist(),
            "intercept": float(self.intercept),
            "coef": self.coef.tolist(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ValueModel":
        return cls(
            mean=np.asarray(d["mean"], float),
            std=np.asarray(d["std"], float),
            intercept=float(d["intercept"]),
            coef=np.asarray(d["coef"], float),
        )

    def save(self, path) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path) -> "ValueModel":
        with open(path) as f:
            return cls.from_dict(json.load(f))


def train_logistic(X, y, l2: float = 1.0, iterations: int = 100, tol: float = 1e-9) -> ValueModel:
    """Fit a logistic value model by Newton-Raphson (IRLS) with L2 on the coefficients
    (not the intercept). ``X`` is ``(n, d)`` features, ``y`` is ``(n,)`` in {0,1}."""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std[std == 0.0] = 1.0  # guard constant features
    Xs = (X - mean) / std

    n, d = Xs.shape
    A = np.hstack([np.ones((n, 1)), Xs])  # column 0 is the intercept
    w = np.zeros(d + 1)
    reg = l2 * np.eye(d + 1)
    reg[0, 0] = 0.0  # don't regularise the intercept

    for _ in range(iterations):
        p = _sigmoid(A @ w)
        grad = A.T @ (y - p) - reg @ w
        hess = A.T @ (A * (p * (1 - p))[:, None]) + reg
        step = np.linalg.solve(hess, grad)
        w += step
        if np.max(np.abs(step)) < tol:
            break

    return ValueModel(mean=mean, std=std, intercept=float(w[0]), coef=w[1:])
