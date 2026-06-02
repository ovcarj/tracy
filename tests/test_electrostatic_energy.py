"""Tests for the electrostatic energy calculation (Milestone 5).

Pure-function tests require no AiiDA profile.
WorkChain spec tests use the session-scoped aiida_profile fixture from conftest.py.
"""

from __future__ import annotations

import numpy as np
import pytest

from tracy.calculations.electrostatic_energy import (
    build_spline,
    center_at_com,
    compute_dipole,
    compute_valid_scan_range,
    orient_to_axis,
    parse_xvg_potential,
    scan_electrostatic_energy,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_XVG_CONTENT = """\
# This is a comment
@ title "Electrostatic Potential"
@ xaxis label "z (nm)"
@ yaxis label "Potential (V)"
0.0   0.0
1.0   1.0
2.0   2.0
3.0   3.0
4.0   4.0
"""

# Three-atom linear molecule along z: O-C-O with RESP charges
_COORDS_NM = np.array([
    [0.0, 0.0, -0.12],
    [0.0, 0.0,  0.00],
    [0.0, 0.0,  0.12],
])
_ATOMNOS = np.array([8, 6, 8])
_CHARGES = np.array([-0.4, 0.8, -0.4])  # net charge = 0, dipole = 0


# ---------------------------------------------------------------------------
# parse_xvg_potential
# ---------------------------------------------------------------------------


def test_parse_xvg_skips_header_lines():
    z, phi = parse_xvg_potential(_XVG_CONTENT)
    assert len(z) == 5
    np.testing.assert_array_almost_equal(z, [0.0, 1.0, 2.0, 3.0, 4.0])
    np.testing.assert_array_almost_equal(phi, [0.0, 1.0, 2.0, 3.0, 4.0])


def test_parse_xvg_empty_lines_ignored():
    content = "\n\n0.5  2.3\n\n1.5  3.7\n"
    z, phi = parse_xvg_potential(content)
    assert len(z) == 2
    assert abs(phi[0] - 2.3) < 1e-10


# ---------------------------------------------------------------------------
# build_spline
# ---------------------------------------------------------------------------


def test_build_spline_interpolates_exactly_at_knots():
    z = np.linspace(0, 4, 10)
    phi = z ** 2
    spline = build_spline(z, phi)
    for zi, phii in zip(z, phi):
        assert abs(spline(zi) - phii) < 1e-8


def test_build_spline_smooth_interior():
    z = np.linspace(0, 4, 100)
    phi = np.sin(z)
    spline = build_spline(z, phi)
    assert abs(spline(2.0) - np.sin(2.0)) < 1e-4


# ---------------------------------------------------------------------------
# center_at_com
# ---------------------------------------------------------------------------


def test_center_at_com_com_is_zero():
    centered = center_at_com(_COORDS_NM, _ATOMNOS)
    masses = np.array([15.999, 12.011, 15.999])
    com = np.average(centered, axis=0, weights=masses)
    np.testing.assert_allclose(com, [0, 0, 0], atol=1e-12)


def test_center_at_com_preserves_relative_positions():
    original = _COORDS_NM.copy()
    centered = center_at_com(original, _ATOMNOS)
    diffs_before = original[1] - original[0]
    diffs_after = centered[1] - centered[0]
    np.testing.assert_allclose(diffs_before, diffs_after, atol=1e-12)


def test_center_at_com_unknown_element_raises():
    coords = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    atomnos = np.array([0, 0])  # element 0 not in lookup
    with pytest.raises(ValueError, match="Unknown atomic numbers"):
        center_at_com(coords, atomnos)


def test_center_at_com_metal_element_ok():
    # Zn (30), Na (11), Ca (20) must work without error
    coords = np.array([[0.0, 0.0, 0.0], [0.5, 0.0, 0.0]])
    atomnos = np.array([30, 11])  # Zn + Na
    centered = center_at_com(coords, atomnos)
    assert centered.shape == (2, 3)


# ---------------------------------------------------------------------------
# compute_dipole
# ---------------------------------------------------------------------------


def test_compute_dipole_zero_for_symmetric():
    d = compute_dipole(_COORDS_NM, _CHARGES)
    np.testing.assert_allclose(d, [0, 0, 0], atol=1e-12)


def test_compute_dipole_direction():
    coords = np.array([[0.0, 0.0, 0.5], [0.0, 0.0, -0.5]])
    charges = np.array([1.0, -1.0])
    d = compute_dipole(coords, charges)
    assert d[2] > 0
    assert abs(d[0]) < 1e-12
    assert abs(d[1]) < 1e-12


def test_compute_dipole_magnitude():
    coords = np.array([[0.0, 0.0, 1.0]])
    charges = np.array([1.0])
    d = compute_dipole(coords, charges)
    np.testing.assert_allclose(d, [0.0, 0.0, 1.0])


# ---------------------------------------------------------------------------
# orient_to_axis
# ---------------------------------------------------------------------------


def _dipole_direction_after_orient(coords, charges, axis, sign):
    dipole = compute_dipole(coords, charges)
    oriented = orient_to_axis(coords, dipole, axis=axis, sign=sign)
    new_d = compute_dipole(oriented, charges)
    return new_d / np.linalg.norm(new_d)


def test_orient_positive_z():
    coords = np.array([[0.0, 0.0, 0.5], [0.0, 0.0, -0.5]])
    charges = np.array([1.0, -1.0])
    dhat = _dipole_direction_after_orient(coords, charges, axis=2, sign=1)
    np.testing.assert_allclose(dhat, [0, 0, 1], atol=1e-6)


def test_orient_negative_z():
    coords = np.array([[0.0, 0.0, 0.5], [0.0, 0.0, -0.5]])
    charges = np.array([1.0, -1.0])
    dhat = _dipole_direction_after_orient(coords, charges, axis=2, sign=-1)
    np.testing.assert_allclose(dhat, [0, 0, -1], atol=1e-6)


def test_orient_already_aligned_unchanged():
    coords = np.array([[0.0, 0.0, 0.5], [0.0, 0.0, -0.5]])
    charges = np.array([1.0, -1.0])
    dipole = compute_dipole(coords, charges)
    oriented = orient_to_axis(coords, dipole, axis=2, sign=1)
    np.testing.assert_allclose(oriented, coords, atol=1e-10)


def test_orient_antiparallel():
    coords = np.array([[0.0, 0.0, -0.5], [0.0, 0.0, 0.5]])
    charges = np.array([1.0, -1.0])
    dipole = compute_dipole(coords, charges)
    oriented = orient_to_axis(coords, dipole, axis=2, sign=1)
    new_d = compute_dipole(oriented, charges)
    assert new_d[2] > 0


def test_orient_x_axis():
    coords = np.array([[0.5, 0.0, 0.0], [-0.5, 0.0, 0.0]])
    charges = np.array([1.0, -1.0])
    dhat = _dipole_direction_after_orient(coords, charges, axis=0, sign=1)
    np.testing.assert_allclose(dhat, [1, 0, 0], atol=1e-6)


def test_orient_preserves_interatomic_distances():
    coords = np.array([[0.0, 0.1, 0.5], [0.0, -0.1, -0.5]])
    charges = np.array([1.0, -1.0])
    dipole = compute_dipole(coords, charges)
    oriented = orient_to_axis(coords, dipole, axis=2, sign=1)
    d_before = np.linalg.norm(coords[0] - coords[1])
    d_after = np.linalg.norm(oriented[0] - oriented[1])
    assert abs(d_before - d_after) < 1e-10


# ---------------------------------------------------------------------------
# compute_valid_scan_range
# ---------------------------------------------------------------------------


def test_valid_scan_range_symmetric_molecule():
    atom_proj = np.array([-0.2, 0.0, 0.2])
    z_start, z_end = compute_valid_scan_range(0.0, 8.0, atom_proj)
    assert abs(z_start - 0.2) < 1e-10
    assert abs(z_end - 7.8) < 1e-10


def test_valid_scan_range_asymmetric_molecule():
    atom_proj = np.array([-0.1, 0.0, 0.3])
    z_start, z_end = compute_valid_scan_range(0.0, 8.0, atom_proj)
    assert abs(z_start - 0.1) < 1e-10
    assert abs(z_end - 7.7) < 1e-10


def test_valid_scan_range_all_atoms_in_same_direction():
    atom_proj = np.array([0.0, 0.1, 0.3])
    z_start, z_end = compute_valid_scan_range(0.0, 8.0, atom_proj)
    assert abs(z_start - 0.0) < 1e-10
    assert abs(z_end - 7.7) < 1e-10


# ---------------------------------------------------------------------------
# scan_electrostatic_energy
# ---------------------------------------------------------------------------


def test_scan_uniform_potential():
    z = np.linspace(0, 5, 50)
    phi = np.ones(50) * 3.0
    spline = build_spline(z, phi)
    coords = np.array([[0.0, 0.0, -0.1], [0.0, 0.0, 0.1]])
    charges = np.array([0.3, -0.5])
    z_scan = np.linspace(1.0, 4.0, 20)
    energies = scan_electrostatic_energy(z_scan, coords, charges, spline, axis=2)
    expected = 3.0 * (0.3 - 0.5)
    np.testing.assert_allclose(energies, expected, atol=1e-6)


def test_scan_linear_potential_increasing():
    z = np.linspace(0, 5, 100)
    phi = z.copy()
    spline = build_spline(z, phi)
    coords = np.array([[0.0, 0.0, -0.1], [0.0, 0.0, 0.1]])
    charges = np.array([1.0, 1.0])  # Σq = 2 → E ∝ z_com
    z_scan = np.linspace(0.2, 4.8, 50)
    energies = scan_electrostatic_energy(z_scan, coords, charges, spline, axis=2)
    assert np.argmin(energies) == 0
    assert np.argmax(energies) == 49


def test_scan_length_matches_n_points():
    z = np.linspace(0, 5, 50)
    spline = build_spline(z, np.zeros(50))
    coords = np.zeros((2, 3))
    charges = np.array([0.0, 0.0])
    z_scan = np.linspace(0.5, 4.5, 37)
    energies = scan_electrostatic_energy(z_scan, coords, charges, spline, axis=2)
    assert len(energies) == 37


# ---------------------------------------------------------------------------
# compute_electrostatic_energy — error handling
# ---------------------------------------------------------------------------


def _make_output_parameters(charges_key: str = 'resp') -> dict:
    """Minimal output_parameters dict for testing."""
    return {
        'atomnos': [6, 8],
        'atomcoords': [[[0.0, 0.0, -0.6], [0.0, 0.0, 0.6]]],
        'atomcharges': {charges_key: [0.5, -0.5]},
    }


def _make_protocol(charges_model: str = 'resp', z_min=None, z_max=None) -> dict:
    z_scan: dict = {'n_points': 50}
    if z_min is not None:
        z_scan['min'] = z_min
    if z_max is not None:
        z_scan['max'] = z_max
    return {'tracy': {'membrane_normal_axis': 'z', 'charges_model': charges_model,
                      'z_scan_nm': z_scan}}


def _make_xvg_node(z_min=0.0, z_max=8.0, n=50):
    import io
    from aiida import orm
    lines = [f"{z:.4f}  {z:.4f}" for z in np.linspace(z_min, z_max, n)]
    xvg = orm.SinglefileData(io.BytesIO("\n".join(lines).encode()), filename="potential.xvg")
    xvg.store()
    return xvg


def test_missing_charge_model_raises_informative_error(aiida_profile):
    from aiida import orm
    from tracy.calculations.electrostatic_energy import compute_electrostatic_energy

    xvg = _make_xvg_node()
    params = orm.Dict(_make_output_parameters(charges_key='resp'))
    params.store()
    protocol = orm.Dict(_make_protocol(charges_model='chelpg'))
    protocol.store()

    with pytest.raises(ValueError, match="chelpg") as exc:
        compute_electrostatic_energy(xvg, params, protocol)
    assert "available" in str(exc.value)


def test_reversed_scan_bounds_raises(aiida_profile):
    from aiida import orm
    from tracy.calculations.electrostatic_energy import compute_electrostatic_energy

    xvg = _make_xvg_node()
    params = orm.Dict(_make_output_parameters())
    params.store()
    # min > max → z_start >= z_end after clipping
    protocol = orm.Dict(_make_protocol(z_min=6.0, z_max=2.0))
    protocol.store()

    with pytest.raises(ValueError, match="Invalid scan range"):
        compute_electrostatic_energy(xvg, params, protocol)


# ---------------------------------------------------------------------------
# WorkChain spec (requires aiida_profile)
# ---------------------------------------------------------------------------


def test_is_workchain_subclass():
    from aiida.engine import WorkChain
    from tracy.workflows.electrostatic_energy import ElectrostaticEnergyWorkChain
    assert issubclass(ElectrostaticEnergyWorkChain, WorkChain)


def test_workchain_has_required_inputs():
    from tracy.workflows.electrostatic_energy import ElectrostaticEnergyWorkChain
    inputs = ElectrostaticEnergyWorkChain.spec().inputs
    assert 'potential_profile' in inputs
    assert 'output_parameters' in inputs
    assert 'protocol' in inputs


def test_workchain_has_report_output():
    from tracy.workflows.electrostatic_energy import ElectrostaticEnergyWorkChain
    outputs = ElectrostaticEnergyWorkChain.spec().outputs
    assert 'electrostatic_energy_report' in outputs
