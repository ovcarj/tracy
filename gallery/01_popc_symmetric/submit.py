"""Gallery example 1: symmetric POPC bilayer — end-to-end submission.

Chains CHARMM-GUI membrane build → GROMACS MD → electrostatic potential
in a single MembraneElectrostaticsWorkChain.

Requirements
------------
- AiiDA daemon running:        verdi daemon start
- CHARMM-GUI token cached:     aiida-charmm-gui login
- GROMACS registered:          verdi code list

Edit GROMACS_CODE_LABEL below to match your registered code, adjust the
scheduler options to your cluster, then run:

    python gallery/01_popc_symmetric/submit.py

Monitor progress:

    verdi process show <pk>
    verdi process report <pk>

After completion, store the potential profile in remembrane:

    # Find the ComputeMembranePotentialWorkChain pk in the Called section:
    verdi process show <pk>

    remembrane import aiida --pk <compute_membrane_potential_pk>

    remembrane list
    remembrane show <uuid>

    # If remembrane cannot resolve the BuildMembraneWorkChain automatically
    # (e.g. standalone submission outside MembraneElectrostaticsWorkChain),
    # pass it explicitly:
    remembrane import aiida \\
        --pk <compute_membrane_potential_pk> \\
        --build-membrane-pk <build_membrane_pk>
"""

from __future__ import annotations

from pathlib import Path

import yaml
from aiida import load_profile, orm
from aiida.engine import submit

GROMACS_CODE_LABEL = "gmx@localhost"


def main():
    load_profile()

    protocol_path = Path(__file__).parent / "protocol.yaml"
    with protocol_path.open() as fh:
        protocol = orm.Dict(yaml.safe_load(fh))

    # Scheduler options for production MD (grompp + mdrun).
    # mdrun is launched with MPI; adjust num_mpiprocs_per_machine to match
    # the number of cores available on your compute node.
    md_options = orm.Dict({
        "resources": {"num_machines": 1, "num_mpiprocs_per_machine": 8},
        "max_wallclock_seconds": 864000,   # 10 days
        "withmpi": True,
        # "queue_name": "partition",
    })

    # Scheduler options for lightweight analysis jobs (trjconv, gmx select,
    # gmx potential).  These run on far fewer cores and finish in minutes.
    # Providing analysis_options separately prevents them from queuing behind
    # the long production run when they could run immediately on a free node.
    analysis_options = orm.Dict({
        "resources": {"num_machines": 1, "num_mpiprocs_per_machine": 4},
        "max_wallclock_seconds": 3600,
        "withmpi": True,
        # "queue_name": "partition",
    })

    from tracy.workflows.membrane_pipeline import MembraneElectrostaticsWorkChain

    wc = submit(
        MembraneElectrostaticsWorkChain,
        protocol=protocol,
        code=orm.load_code(GROMACS_CODE_LABEL),
        options=md_options,
        analysis_options=analysis_options,
    )
    print(f"Submitted MembraneElectrostaticsWorkChain: pk={wc.pk}")
    print(f"\nMonitor with:  verdi process show {wc.pk}")
    print(f"Full log:      verdi process report {wc.pk}")


if __name__ == "__main__":
    main()
