"""Example: submit RunMembraneMDWorkChain with GROMACS via AiiDA.

Loads the bundled GROMACS fixture, constructs a protocol for
minimization followed by all six equilibration steps.

Requirements:
    - AiiDA daemon running              (verdi daemon start)
    - GROMACS registered as an AiiDA code (verdi code setup)
    - aiida-gromacs installed           (pip install -e .[gromacs])

Edit GROMACS_CODE_LABEL below to match your registered code, then run with:

    python examples/run_membrane_md_gromacs.py

Monitor progress with:

    verdi process show <pk>
    verdi process report <pk>
"""

from __future__ import annotations

from pathlib import Path

from aiida import load_profile, orm
from aiida.engine import submit

FIXTURE_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "gromacs_bundle"

# Edit this to match your registered GROMACS code: `verdi code list`
GROMACS_CODE_LABEL = "gmx@localhost"


def main():
    load_profile()

    bundle = orm.FolderData()
    bundle.put_object_from_tree(str(FIXTURE_DIR))
    bundle.store()

    protocol = orm.Dict({
        "tracy": {
            "expected_engine": "gromacs",
            "membrane_normal_axis": "z",
            "md_steps": ["minimization",
                         "equilibration", "equilibration", "equilibration",
                         "equilibration", "equilibration", "equilibration"],
            # mdp_overrides patches MDP keys per step before submission.
            # Useful for short test runs — remove for production:
            # "mdp_overrides": {
            #     "equilibration": {
            #         "nsteps": "500",
            #         "nstxout": "500",
            #         "nstxout-compressed": "0",
            #     },
            # },
        },
    })

    # Scheduler options — adjust resources and queue to match your cluster.
    # withmpi=True is applied to mdrun only; grompp always runs serial.
    options = orm.Dict({
        "resources": {"num_machines": 1, "num_mpiprocs_per_machine": 1},
        "max_wallclock_seconds": 3600,
        "withmpi": True,
        # "queue_name": "partition",  # uncomment and set for SLURM --partition / PBS -q
    })

    from tracy.workflows.membrane_md import RunMembraneMDWorkChain

    wc = submit(
        RunMembraneMDWorkChain,
        md_input_bundle=bundle,
        protocol=protocol,
        code=orm.load_code(GROMACS_CODE_LABEL),
        options=options,
    )
    print(f"Submitted RunMembraneMDWorkChain: pk={wc.pk}")
    print(f"\nMonitor with:  verdi process show {wc.pk}")


if __name__ == "__main__":
    main()
