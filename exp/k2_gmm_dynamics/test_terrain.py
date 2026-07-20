"""K2 terrain tests: the two-patch open question (spec-note owed).

Asserts the measured ordering the spec-note cites: splitting a
boundary-straddling Gaussian at the patch boundary and evolving each piece
under its own field is far more accurate than ignoring the boundary, and
conserves mass to float tolerance.
"""

from __future__ import annotations

import numpy as np

from exp.k2_gmm_dynamics import terrain

RESULT = terrain.run_experiment(seed=1)  # module-level: run the EM reference once


def test_split_conserves_mass_to_float_tolerance():
    assert RESULT["split"]["mass_error_split"] < 1e-12
    assert RESULT["split"]["mass_error_evolved"] < 1e-12


def test_split_is_far_more_accurate_than_ignoring():
    a = RESULT["ignore"]["errors"]
    b = RESULT["split"]["errors"]
    assert b["mean_rel"] < a["mean_rel"] * 0.5
    assert b["cov_rel"] < a["cov_rel"] * 0.5
    # absolute sanity: split tracks the EM reference closely
    assert b["mean_rel"] < 0.10
    assert b["cov_rel"] < 0.15


def test_resplit_buys_accuracy_with_components():
    b = RESULT["split"]
    b2 = RESULT["resplit"]
    assert b2["n_components_after"] == 2 * b["n_components_after"]
    assert b2["errors"]["cov_rel"] < b["errors"]["cov_rel"]
    assert b2["mass_error_evolved"] < 1e-12


def test_ignoring_the_boundary_is_measurably_wrong():
    a = RESULT["ignore"]["errors"]
    assert a["mean_rel"] > 0.15  # O(1) moment error, not noise


def test_mixture_growth_is_one_component_per_boundary():
    assert RESULT["split"]["n_components_before"] == 1
    assert RESULT["split"]["n_components_after"] == 2


def test_split_moment_matching_exact_against_quadrature():
    # fine grid quadrature of the truncated normal vs. closed-form moments;
    # integrate over the kept half-plane only so the pdf has no kink
    import math

    from exp.k2_gmm_dynamics.terrain import truncated_normal_moments

    mean, sd = 1.3, 2.1
    for side, xs in (
        ("right", np.linspace(0.0, mean + 12 * sd, 1_000_001)),
        ("left", np.linspace(mean - 12 * sd, 0.0, 1_000_001)),
    ):
        pdf = np.exp(-0.5 * ((xs - mean) / sd) ** 2) / (sd * math.sqrt(2 * math.pi))
        mass_q = np.trapezoid(pdf, xs)
        mean_q = np.trapezoid(xs * pdf, xs) / mass_q
        var_q = np.trapezoid((xs - mean_q) ** 2 * pdf, xs) / mass_q
        mass, tmean, tvar = truncated_normal_moments(mean, sd, side)
        assert abs(mass - mass_q) < 1e-10
        assert abs(tmean - mean_q) < 1e-9
        assert abs(tvar - var_q) < 1e-8
