from __future__ import annotations

import numpy as np
from scipy.interpolate import CubicSpline

from aiida import orm
from aiida.engine import calcfunction

# Atomic masses (g/mol) — IUPAC 2021 standard atomic weights
_ATOMIC_MASSES: dict[int, float] = {
    1: 1.008,    5: 10.81,   6: 12.011,  7: 14.007,  8: 15.999,
    9: 18.998,  11: 22.990, 12: 24.305, 14: 28.085,  15: 30.974,
    16: 32.06,  17: 35.45,  19: 39.098, 20: 40.078,  25: 54.938,
    26: 55.845, 29: 63.546, 30: 65.38,  35: 79.904,  53: 126.90,
}

_EV_TO_KJMOL = 96.48533695   # CODATA 2018: 1 eV = 96.48533695 kJ/mol
_ENM_TO_DEBYE = 48.03206     # 1 e·nm = 48.03206 Debye


def parse_xvg_potential(content: str) -> tuple[np.ndarray, np.ndarray]:
    """Parse gmx potential .xvg output, skipping comment/header lines."""
    z, phi = [], []
    for line in content.splitlines():
        line = line.strip()
        if not line or line[0] in ('#', '@'):
            continue
        parts = line.split()
        z.append(float(parts[0]))
        phi.append(float(parts[1]))
    return np.array(z), np.array(phi)


def build_spline(z_nm: np.ndarray, phi_V: np.ndarray) -> CubicSpline:
    """Build a cubic spline interpolator for the potential profile."""
    return CubicSpline(z_nm, phi_V)


def center_at_com(coords_nm: np.ndarray, atomnos: np.ndarray) -> np.ndarray:
    """Translate coordinates so the mass-weighted center of mass is at the origin."""
    unknown = {int(n) for n in atomnos} - _ATOMIC_MASSES.keys()
    if unknown:
        raise ValueError(
            f"Unknown atomic numbers {sorted(unknown)}. "
            f"Expand _ATOMIC_MASSES in tracy/calculations/electrostatic_energy.py."
        )
    masses = np.array([_ATOMIC_MASSES[int(n)] for n in atomnos])
    com = np.average(coords_nm, axis=0, weights=masses)
    return coords_nm - com


def compute_dipole(coords_nm: np.ndarray, charges: np.ndarray) -> np.ndarray:
    """Compute dipole moment vector: d = Σ qᵢ rᵢ (units: e·nm)."""
    return charges @ coords_nm


def orient_to_axis(
    coords_nm: np.ndarray, dipole: np.ndarray, axis: int = 2, sign: int = 1
) -> np.ndarray:
    """Rotate coords so the dipole points along +sign * e_axis (Rodrigues rotation)."""
    target = np.zeros(3)
    target[axis] = float(sign)

    v = dipole / np.linalg.norm(dipole)
    k = np.cross(v, target)
    k_norm = float(np.linalg.norm(k))

    if k_norm < 1e-10:
        if np.dot(v, target) > 0:
            return coords_nm.copy()
        # Anti-parallel: 180° rotation about a perpendicular axis
        perp = np.zeros(3)
        perp[(axis + 1) % 3] = 1.0
        k = perp
        theta = np.pi
    else:
        k = k / k_norm
        theta = float(np.arccos(np.clip(np.dot(v, target), -1.0, 1.0)))

    K = np.array([
        [0.0, -k[2], k[1]],
        [k[2], 0.0, -k[0]],
        [-k[1], k[0], 0.0],
    ])
    R = np.eye(3) * np.cos(theta) + (1.0 - np.cos(theta)) * np.outer(k, k) + np.sin(theta) * K
    return (R @ coords_nm.T).T


def compute_valid_scan_range(
    profile_z_min: float,
    profile_z_max: float,
    atom_proj: np.ndarray,
) -> tuple[float, float]:
    """Return the COM scan range that keeps all atoms inside [profile_z_min, profile_z_max]."""
    return float(profile_z_min - atom_proj.min()), float(profile_z_max - atom_proj.max())


def scan_electrostatic_energy(
    z_scan_nm: np.ndarray,
    coords_nm: np.ndarray,
    charges: np.ndarray,
    spline: CubicSpline,
    axis: int = 2,
) -> np.ndarray:
    """Compute E(z) = Σ qᵢ φ(z + rᵢ_axis) [eV] for each COM position z in z_scan_nm."""
    atom_proj = coords_nm[:, axis]
    return np.array([float(np.dot(charges, spline(z + atom_proj))) for z in z_scan_nm])


@calcfunction
def compute_electrostatic_energy(
    potential_xvg: orm.SinglefileData,
    output_parameters: orm.Dict,
    protocol: orm.Dict,
) -> orm.Dict:
    """Compute the 1D electrostatic energy profile E(z) for a molecule in a membrane potential.

    The molecule is oriented so its dipole is parallel (or anti-parallel) to the membrane
    normal axis. The COM is scanned over the full valid range of the potential profile.
    Both orientations (+axis and -axis) are computed and reported.
    """
    tracy_conf = protocol.get_dict().get('tracy', {})
    axis_str = tracy_conf.get('membrane_normal_axis', 'z').lower()
    axis = {'x': 0, 'y': 1, 'z': 2}[axis_str]
    charges_model = tracy_conf.get('charges_model', 'resp')
    z_scan_conf = tracy_conf.get('z_scan_nm', {}) or {}
    n_points = int(z_scan_conf.get('n_points', 200))
    z_clip_min = z_scan_conf.get('min')
    z_clip_max = z_scan_conf.get('max')

    with potential_xvg.open(mode='r') as f:
        xvg_content = f.read()
    z_nm, phi_V = parse_xvg_potential(xvg_content)
    spline = build_spline(z_nm, phi_V)

    params = output_parameters.get_dict()
    atomnos = np.array(params['atomnos'], dtype=int)
    # aiida-orca (via cclib) stores atomcoords in Angstroms; convert to nm
    atomcoords_A = np.array(params['atomcoords'][-1])
    coords_nm = center_at_com(atomcoords_A / 10.0, atomnos)
    atomcharges = params.get('atomcharges', {})
    if charges_model not in atomcharges:
        available = list(atomcharges.keys())
        raise ValueError(
            f"Charge model '{charges_model}' not found in output_parameters "
            f"(available: {available}). "
            f"Check protocol.tracy.charges_model matches the ORCA keyword used."
        )
    charges = np.array(atomcharges[charges_model])

    dipole = compute_dipole(coords_nm, charges)
    dipole_norm = float(np.linalg.norm(dipole))
    if dipole_norm < 1e-10:
        ddir = [0.0, 0.0, 0.0]
        ddir[axis] = 1.0
    else:
        ddir = (dipole / dipole_norm).tolist()

    report: dict = {
        'membrane_normal_axis': axis_str,
        'charges_model': charges_model,
        'n_atoms': int(len(atomnos)),
        'dipole_magnitude_D': float(dipole_norm * _ENM_TO_DEBYE),
        'dipole_direction': ddir,
    }

    for sign_label, sign in (('pos', 1), ('neg', -1)):
        oriented = orient_to_axis(coords_nm, dipole, axis=axis, sign=sign)
        atom_proj = oriented[:, axis]
        z_start, z_end = compute_valid_scan_range(float(z_nm.min()), float(z_nm.max()), atom_proj)
        if z_clip_min is not None:
            z_start = max(z_start, float(z_clip_min))
        if z_clip_max is not None:
            z_end = min(z_end, float(z_clip_max))

        if z_start >= z_end:
            raise ValueError(
                f"Invalid scan range for '{sign_label}' orientation after applying clip bounds: "
                f"z_start={z_start:.4f} nm >= z_end={z_end:.4f} nm. "
                f"Check protocol.tracy.z_scan_nm.min/max and molecule size vs profile range."
            )
        z_scan = np.linspace(z_start, z_end, n_points)
        energies_eV = scan_electrostatic_energy(z_scan, oriented, charges, spline, axis)
        energies_kJmol = energies_eV * _EV_TO_KJMOL

        min_idx = int(np.argmin(energies_eV))
        max_idx = int(np.argmax(energies_eV))

        report[f'z_scan_nm_{sign_label}'] = z_scan.tolist()
        report[f'energy_eV_{sign_label}'] = energies_eV.tolist()
        report[f'energy_kJmol_{sign_label}'] = energies_kJmol.tolist()
        report[f'min_z_nm_{sign_label}'] = float(z_scan[min_idx])
        report[f'min_energy_eV_{sign_label}'] = float(energies_eV[min_idx])
        report[f'max_z_nm_{sign_label}'] = float(z_scan[max_idx])
        report[f'max_energy_eV_{sign_label}'] = float(energies_eV[max_idx])

    return orm.Dict(report)
