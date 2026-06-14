"""Gallery example 2: asymmetric POPC / POPE:POPS bilayer — end-to-end submission.

Chains CHARMM-GUI membrane build → GROMACS MD → electrostatic potential
in a single MembraneElectrostaticsWorkChain.

The asymmetric composition (POPC outer / POPE:POPS 3:1 inner) mimics the
plasma-membrane lipid distribution.  POPS carries a net −1e charge, which
produces a large electrostatic asymmetry visible in the component-decomposed
potential profile (see potential.png).

Requirements
------------
- AiiDA daemon running:        verdi daemon start
- CHARMM-GUI token cached:     aiida-charmm-gui login
- GROMACS registered:          verdi code list

Edit GROMACS_CODE_LABEL below, adjust scheduler options, then run:

    python gallery/02_popc_pope_pops_asymmetric/submit.py

Monitor progress:

    verdi process show <pk>
    verdi process report <pk>
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
    # The asymmetric patch is larger (~14×14 nm, ~335 inner lipids) than the
    # symmetric example; allocate proportionally more cores if available.
    md_options = orm.Dict({
        "resources": {"num_machines": 1, "num_mpiprocs_per_machine": 8},
        "max_wallclock_seconds": 864000,   # 10 days
        "withmpi": True,
        # "queue_name": "partition",
    })

    # Lightweight analysis jobs (trjconv, gmx select, gmx potential).
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
