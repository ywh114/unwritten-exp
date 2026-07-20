"""K3 — geometry: 2-D axis-aligned regions and exact bivariate-normal mass.

`rect_mass(mean, cov, rect)` is the exact probability of a 2-D Gaussian
component inside an axis-aligned rectangle, computed via the inclusion–
exclusion form over the bivariate-normal CDF.

The CDF Φ₂(h,k;ρ) is evaluated by Gauss–Legendre quadrature (64 nodes,
error < 1e-12 for most of the parameter space).  The quadrature uses only
stdlib + numpy; no scipy or other optional deps.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# ---------------------------------------------------------------------------
# Gauss–Legendre nodes & weights (cached once, 64 nodes)
# ---------------------------------------------------------------------------

_GL_N: int = 64
_GL_NODES: np.ndarray | None = None   # shape (64,)
_GL_WEIGHTS: np.ndarray | None = None  # shape (64,)
_GL_BUILT: bool = False


def _gl_cache() -> tuple[np.ndarray, np.ndarray]:
    global _GL_NODES, _GL_WEIGHTS, _GL_BUILT
    if not _GL_BUILT:
        _GL_NODES, _GL_WEIGHTS = np.polynomial.legendre.leggauss(_GL_N)
        _GL_BUILT = True
    return _GL_NODES, _GL_WEIGHTS  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Rect
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        if self.x0 > self.x1 or self.y0 > self.y1:
            raise ValueError("rect bounds must be ordered (lo <= hi)")

    @property
    def area(self) -> float:
        return (self.x1 - self.x0) * (self.y1 - self.y0)

    def __repr__(self) -> str:
        return f"Rect(x0={self.x0:.4g}, y0={self.y0:.4g}, x1={self.x1:.4g}, y1={self.y1:.4g})"


# ---------------------------------------------------------------------------
# Univariate normal CDF / PDF  (stdlib: no scipy)
# ---------------------------------------------------------------------------

_SQRT2 = math.sqrt(2.0)
_SQRT2PI = math.sqrt(2.0 * math.pi)


def _normal_cdf(z: float) -> float:
    """Φ(z) = ½(1 + erf(z/√2))."""
    return 0.5 * (1.0 + math.erf(z / _SQRT2))


def _normal_pdf(z: float) -> float:
    """φ(z) = exp(−z²/2) / √(2π)."""
    return math.exp(-0.5 * z * z) / _SQRT2PI


# ---------------------------------------------------------------------------
# Bivariate normal CDF  Φ₂(h,k;ρ)
# ---------------------------------------------------------------------------

_TAIL_CUT = 10.0  # beyond ±10 the tails are < 1e-23
_RHO_CLAMP = 1.0 - 1e-12


def _bvn_cdf(h: float, k: float, rho: float) -> float:
    """Φ₂(h, k; ρ) — standard bivariate cumulative distribution function.

    Integral form (Drezner & Wesolowsky, 1990):
        Φ₂(h,k;ρ) = ∫₋∞ʰ  φ(x) · Φ((k−ρx)/√(1−ρ²))  dx
    evaluated via 64-point Gauss–Legendre on [−10, min(h,10)].
    """
    if h <= -_TAIL_CUT:
        return 0.0

    rho = max(-_RHO_CLAMP, min(_RHO_CLAMP, rho))
    upper = min(h, _TAIL_CUT)
    lower = -_TAIL_CUT

    # ρ = 0 short-circuit (validates the quadrature in tests)
    if rho == 0.0:
        return _normal_cdf(h) * _normal_cdf(k)

    nodes, weights = _gl_cache()
    # Map t ∈ [−1, 1]  →  x ∈ [lower, upper]
    half_width = 0.5 * (upper - lower)
    mid = 0.5 * (upper + lower)
    xs = half_width * nodes + mid

    inv_sqrt_one_m_rho2 = 1.0 / math.sqrt(1.0 - rho * rho)
    # inner: Φ((k − ρ·x) / √(1−ρ²))
    inner_args = (k - rho * xs) * inv_sqrt_one_m_rho2
    inner_vals = np.empty_like(inner_args)
    for i in range(len(inner_args)):
        inner_vals[i] = _normal_cdf(float(inner_args[i]))

    # φ(x) = exp(−x²/2) / √(2π)
    phi_vals = np.exp(-0.5 * xs * xs) / _SQRT2PI

    integrand = phi_vals * inner_vals
    # Gauss–Legendre integral over [−1,1] multiplied by the jacobian half_width
    result = float(np.dot(weights, integrand)) * half_width
    return max(0.0, min(1.0, float(result)))


# ---------------------------------------------------------------------------
# Rectangle mass of a 2-D Gaussian
# ---------------------------------------------------------------------------


def rect_mass(mean: np.ndarray, cov: np.ndarray, rect: Rect) -> float:
    """Exact probability of a 2-D Gaussian (mean, cov) inside `rect`.

    Standard inclusion–exclusion form over the bivariate CDF.
    """
    mx, my = float(mean[0]), float(mean[1])
    sx = math.sqrt(float(cov[0, 0]))
    sy = math.sqrt(float(cov[1, 1]))
    if sx == 0.0 or sy == 0.0:
        # degenerate: point mass — inside iff mean is in rect
        in_x = rect.x0 <= mx <= rect.x1
        in_y = rect.y0 <= my <= rect.y1
        return 1.0 if in_x and in_y else 0.0

    rho = float(cov[0, 1]) / (sx * sy)
    rho = max(-_RHO_CLAMP, min(_RHO_CLAMP, rho))

    # standardise rect bounds
    hx0 = (rect.x0 - mx) / sx
    hx1 = (rect.x1 - mx) / sx
    hy0 = (rect.y0 - my) / sy
    hy1 = (rect.y1 - my) / sy

    return (
        _bvn_cdf(hx1, hy1, rho)
        - _bvn_cdf(hx1, hy0, rho)
        - _bvn_cdf(hx0, hy1, rho)
        + _bvn_cdf(hx0, hy0, rho)
    )
