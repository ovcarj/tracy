"""Example: submit RunMembraneMDWorkChain via AiiDA.

Loads the bundled GROMACS fixture, constructs a protocol for the
minimization step, and submits RunMembraneMDWorkChain.

Requirements:
    - AiiDA daemon running       (verdi daemon start)
    - gmx registered as a code   (verdi code setup)
    - aiida-gromacs installed    (pip install -e .[gromacs])

Run with:
    python examples/run_membrane_md.py

Then monitor with:
    verdi process show <pk>
    verdi process report <pk>
"""

from __future__ import annotations

from pathlib import Path

from aiida import load_profile, orm
from aiida.engine import submit

FIXTURE_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "gromacs_bundle"

# Label of the gmx code registered in AiiDA — adjust to your setup.
GROMACS_CODE_LABEL = "gmx@localhost"


def main():
    load_profile()

    bundle = orm.FolderData()
    bundle.put_object_from_tree(str(FIXTURE_DIR))
    bundle.store()

    protocol = orm.Dict({
        "codes": {
            "gromacs": GROMACS_CODE_LABEL,
        },
        "tracy": {
            "expected_engine": "gromacs",
            "membrane_normal_axis": "z",
            "md_steps": ["minimization"],
        },
    })

    from tracy.workflows.membrane_md import RunMembraneMDWorkChain

    wc = submit(
        RunMembraneMDWorkChain,
        md_input_bundle=bundle,
        protocol=protocol,
        code=orm.load_code(GROMACS_CODE_LABEL),
    )
    print(f"Submitted RunMembraneMDWorkChain: pk={wc.pk}")
    print(f"\nMonitor with:  verdi process show {wc.pk}")


if __name__ == "__main__":
    main()
