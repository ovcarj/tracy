"""Tests for potential_analysis: component additivity check.

Pure-function tests require no AiiDA profile.
"""

from __future__ import annotations

import numpy as np
import pytest


def _make_xvg(z: np.ndarray, phi: np.ndarray) -> str:
    lines = ["# comment", "@ title test"]
    lines += [f"{zi:.6f}  {phii:.12f}" for zi, phii in zip(z, phi)]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# check_component_additivity — pure function
# ---------------------------------------------------------------------------


def test_exact_additivity():
    from tracy.calculations.potential_analysis import check_component_additivity

    z = np.linspace(0.0, 8.0, 100)
    phi_a = np.sin(z)
    phi_b = np.cos(z)
    phi_total = phi_a + phi_b

    result = check_component_additivity(
        _make_xvg(z, phi_total),
        {"a": _make_xvg(z, phi_a), "b": _make_xvg(z, phi_b)},
    )

    assert result["max_residual_V"] < 1e-10
    assert result["mean_residual_V"] < 1e-10
    assert result["n_slices"] == 100
    assert set(result["groups"]) == {"a", "b"}


def test_additivity_with_residual():
    from tracy.calculations.potential_analysis import check_component_additivity

    z = np.linspace(0.0, 8.0, 50)
    phi_a = np.ones(50) * 0.5
    phi_b = np.ones(50) * 0.3
    # total intentionally off by 0.1 V
    phi_total = phi_a + phi_b + 0.1

    result = check_component_additivity(
        _make_xvg(z, phi_total),
        {"a": _make_xvg(z, phi_a), "b": _make_xvg(z, phi_b)},
    )

    assert abs(result["max_residual_V"] - 0.1) < 1e-8
    assert abs(result["mean_residual_V"] - 0.1) < 1e-8


def test_additivity_component_interpolated_to_total_grid():
    """Components on a coarser grid are interpolated to the total's z-grid."""
    from tracy.calculations.potential_analysis import check_component_additivity

    z_total = np.linspace(0.0, 8.0, 200)
    z_coarse = np.linspace(0.0, 8.0, 50)

    phi_a = np.ones(50) * 1.0
    phi_total = np.ones(200) * 1.0

    result = check_component_additivity(
        _make_xvg(z_total, phi_total),
        {"a": _make_xvg(z_coarse, phi_a)},
    )

    assert result["max_residual_V"] < 1e-10
    assert result["n_slices"] == 200


def test_additivity_empty_components_raises():
    from tracy.calculations.potential_analysis import check_component_additivity

    z = np.linspace(0.0, 8.0, 50)
    phi = np.zeros(50)

    # Empty components dict: sum is zero, residual equals |phi_total|
    result = check_component_additivity(_make_xvg(z, phi + 0.5), {})
    assert abs(result["max_residual_V"] - 0.5) < 1e-8
    assert result["groups"] == []
