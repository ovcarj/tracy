"""Example: compute electrostatic potential from a completed RunMembraneMDWorkChain.

Loads tpr_file and trajectory_compressed from the last production step of a
completed RunMembraneMDWorkChain and submits ComputeMembranePotentialWorkChain.

Requirements:
    - AiiDA daemon running              (verdi daemon start)
    - GROMACS registered as an AiiDA code (verdi code list)
    - A completed RunMembraneMDWorkChain with a production step
      that has trajectory_compressed output (nstxout-compressed > 0)

Edit the PKs and GROMACS_CODE_LABEL below, then run with:

    python examples/compute_membrane_potential_gromacs.py

Monitor progress with:

    verdi process show <pk>
    verdi process report <pk>
"""

from __future__ import annotations

from aiida import load_profile, orm
from aiida.engine import submit

# PK of the GromacsRunWorkChain for the production step.
# Find it with: verdi process show <RunMembraneMDWorkChain pk>
PRODUCTION_WORKCHAIN_PK = None  # e.g. 749

# Edit this to match your registered GROMACS code: `verdi code list`
GROMACS_CODE_LABEL = "gmx@localhost"


def main():
    load_profile()

    if PRODUCTION_WORKCHAIN_PK is None:
        raise ValueError("Set PRODUCTION_WORKCHAIN_PK to the PK of the production GromacsRunWorkChain.")

    wc = orm.load_node(PRODUCTION_WORKCHAIN_PK)
    tpr_file = wc.outputs.tpr_file
    trajectory_compressed = wc.outputs.trajectory_compressed

    # Load index file from the original bundle if available.
    # Alternatively, pass it directly: index_file=orm.load_node(<pk>)
    index_file = None
    if hasattr(wc.inputs, "index_file"):
        index_file = wc.inputs.index_file

    # Group names must match the index groups in your .ndx file.
    # Check available groups with: gmx make_ndx -f structure.gro -o /dev/null
    # CHARMM-GUI Quick Bilayer typically produces: MEMB, Water, ION, SYSTEM
    protocol = orm.Dict({
        "tracy": {
            "membrane_normal_axis": "z",
            "potential_slices": 100,
            "trjconv_center_group": "MEMB",    # centre on the membrane
            "trjconv_output_group": "SYSTEM",  # write all atoms
            "potential_charge_group": "SYSTEM",
            # Decompose into per-group contributions (omit to compute total only).
            # By Poisson linearity: φ_MEMB + φ_Water + φ_ION = φ_SYSTEM
            "potential_component_groups": ["MEMB", "Water", "ION"],
            "potential_symmetrize": False,      # asymmetric bilayer — do not symmetrize
            "potential_correct": True,
        },
    })

    options = orm.Dict({
        "resources": {"num_machines": 1, "num_mpiprocs_per_machine": 1},
        "max_wallclock_seconds": 3600,
        # "queue_name": "partition",
    })

    from tracy.workflows.electrostatics import ComputeMembranePotentialWorkChain

    inputs = {
        "tpr_file":              tpr_file,
        "trajectory_compressed": trajectory_compressed,
        "protocol":              protocol,
        "code":                  orm.load_code(GROMACS_CODE_LABEL),
        "options":               options,
    }
    if index_file is not None:
        inputs["index_file"] = index_file

    result = submit(ComputeMembranePotentialWorkChain, **inputs)
    print(f"Submitted ComputeMembranePotentialWorkChain: pk={result.pk}")
    print(f"\nMonitor with:  verdi process show {result.pk}")


if __name__ == "__main__":
    main()
