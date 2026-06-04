"""Potential analysis utilities: component additivity check."""

from __future__ import annotations

import numpy as np

from aiida import orm
from aiida.engine import calcfunction

from tracy.calculations.electrostatic_energy import parse_xvg_potential


def check_component_additivity(
    total_xvg_content: str,
    component_contents: dict[str, str],
) -> dict:
    """Check that component φ(z) profiles sum to the total profile.

    Each component is interpolated onto the total's z-grid before summing.
    Returns residual statistics in Volts.
    """
    z_total, phi_total = parse_xvg_potential(total_xvg_content)

    phi_sum = np.zeros_like(phi_total)
    for content in component_contents.values():
        z_comp, phi_comp = parse_xvg_potential(content)
        phi_sum += np.interp(z_total, z_comp, phi_comp)

    residual = np.abs(phi_total - phi_sum)
    return {
        "max_residual_V":  float(residual.max()),
        "mean_residual_V": float(residual.mean()),
        "n_slices":        int(len(z_total)),
        "groups":          list(component_contents.keys()),
    }


@calcfunction
def validate_component_additivity(total_xvg: orm.SinglefileData, **component_xvgs) -> orm.Dict:
    """Calcfunction wrapper for check_component_additivity.

    ``component_xvgs`` keyword arguments map sanitized group labels to SinglefileData nodes.
    """
    with total_xvg.open(mode="r") as fh:
        total_content = fh.read()

    component_contents: dict[str, str] = {}
    for label, node in component_xvgs.items():
        with node.open(mode="r") as fh:
            component_contents[label] = fh.read()

    result = check_component_additivity(total_content, component_contents)
    return orm.Dict(result)
