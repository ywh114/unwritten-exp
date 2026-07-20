"""GMM representation for the K2 position kernel.

A `GMM` is a weighted set of 2-D Gaussian components stored as flat numpy
arrays: weights (n,), means (n, 2), covs (n, 2, 2). All library math
(`dynamics.evolve`, `dynamics.stationary`) acts on the arrays in place-free
fashion — functions return new arrays, never mutate the input.
"""

from __future__ import annotations

import math

import numpy as np

_COV_TOL = 1e-12


class GMM:
    """2-D Gaussian mixture: weights (n,), means (n,2), covs (n,2,2)."""

    __slots__ = ("weights", "means", "covs")

    def __init__(self, weights, means, covs) -> None:
        w = np.asarray(weights, dtype=float)
        m = np.asarray(means, dtype=float)
        c = np.asarray(covs, dtype=float)
        if w.ndim != 1 or m.shape != (w.size, 2) or c.shape != (w.size, 2, 2):
            raise ValueError("shapes must be weights (n,), means (n,2), covs (n,2,2)")
        if np.any(w < 0.0):
            raise ValueError("weights must be non-negative")
        if not w.sum() > 0.0:
            raise ValueError("weights must have positive total mass")
        for i in range(w.size):
            _check_psd(c[i])
        self.weights = w
        self.means = m
        self.covs = c

    @property
    def n_components(self) -> int:
        return self.weights.size

    def copy(self) -> "GMM":
        return GMM(self.weights.copy(), self.means.copy(), self.covs.copy())

    def normalized(self) -> "GMM":
        """Return a copy with weights summing exactly to 1."""
        return GMM(self.weights / self.weights.sum(), self.means, self.covs)

    def mixture_mean(self) -> np.ndarray:
        """First moment of the whole mixture, shape (2,)."""
        return (self.weights[:, None] * self.means).sum(axis=0) / self.weights.sum()

    def mixture_cov(self) -> np.ndarray:
        """Second central moment of the whole mixture, shape (2,2)."""
        mu = self.mixture_mean()
        d = self.means - mu
        within = (self.weights[:, None, None] * self.covs).sum(axis=0)
        between = (self.weights[:, None, None] * (d[:, :, None] * d[:, None, :])).sum(axis=0)
        return (within + between) / self.weights.sum()

    def total_mass(self) -> float:
        return float(self.weights.sum())

    def moments_close(self, other: "GMM", tol: float = 1e-9) -> bool:
        """Elementwise closeness of weights, means and covs (test helper)."""
        return (
            self.weights.shape == other.weights.shape
            and np.allclose(self.weights, other.weights, atol=tol, rtol=0.0)
            and np.allclose(self.means, other.means, atol=tol, rtol=0.0)
            and np.allclose(self.covs, other.covs, atol=tol, rtol=0.0)
        )

    def __repr__(self) -> str:
        return f"GMM(n_components={self.n_components}, mass={self.total_mass():.6f})"


def _check_psd(c: np.ndarray) -> None:
    if not math.isclose(c[0, 1], c[1, 0], abs_tol=_COV_TOL):
        raise ValueError("covariance must be symmetric")
    if c[0, 0] < 0.0 or c[1, 1] < 0.0 or np.linalg.det(c) < -_COV_TOL:
        raise ValueError("covariance must be positive semidefinite")


def Gaussian(mean, var) -> GMM:
    """Single-component helper.

    `var` is either a scalar (isotropic), a length-2 sequence (axis
    variances), or a full (2,2) covariance matrix.
    """
    v = np.asarray(var, dtype=float)
    if v.ndim == 0:
        cov = np.eye(2) * float(v)
    elif v.shape == (2,):
        cov = np.diag(v)
    elif v.shape == (2, 2):
        cov = v
    else:
        raise ValueError("var must be scalar, (2,) or (2,2)")
    return GMM([1.0], np.asarray(mean, dtype=float).reshape(1, 2), cov.reshape(1, 2, 2))
