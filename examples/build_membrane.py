"""Example: submit BuildMembraneWorkChain via AiiDA.

Two usage modes are shown:

1. **Live mode** – calls CHARMM-GUI via the QuickBilayerWorkChain.  Requires:
   - An active AiiDA daemon (``verdi daemon start``).
   - A valid CHARMM-GUI token (``aiida-charmm-gui login``).

2. **Dev / offline mode** – pass a pre-existing FolderData as
   ``charmm_gui_output`` to skip the CHARMM-GUI API call.  Useful for testing
   with a previously downloaded archive.

Run this script with::

    python examples/build_membrane.py

It will print the WorkChain PK and exit.  Monitor progress with::

    verdi process list
    verdi process show <pk>
"""

from __future__ import annotations

import sys

from aiida import load_profile, orm
from aiida.engine import submit


def main():
    load_profile()

    # -------------------------------------------------------------------------
    # Load the protocol from the bundled example YAML.
    # -------------------------------------------------------------------------
    import yaml
    from pathlib import Path

    protocol_path = Path(__file__).parent / "protocols" / "mitochondrial_membrane.yaml"
    with protocol_path.open() as fh:
        protocol_dict = yaml.safe_load(fh)

    protocol = orm.Dict(protocol_dict)

    # -------------------------------------------------------------------------
    # Choose mode.
    # -------------------------------------------------------------------------
    # To run in dev mode, set use_dev_mode = True and provide a stored
    # FolderData PK from a previous CHARMM-GUI run:
    #
    #   use_dev_mode = True
    #   existing_folder_pk = 42  # replace with real PK
    #
    use_dev_mode = False

    from tracy.workflows.membrane_builder import BuildMembraneWorkChain

    if use_dev_mode:
        # Replace `existing_folder_pk` with the PK of a stored FolderData
        # containing a CHARMM-GUI output archive.
        existing_folder_pk = None  # TODO: set this to a real PK
        if existing_folder_pk is None:
            print(
                "Dev mode is enabled but `existing_folder_pk` is not set.\n"
                "Set `existing_folder_pk` to the PK of a stored FolderData, or "
                "set `use_dev_mode = False` to run a live CHARMM-GUI job.",
                file=sys.stderr,
            )
            sys.exit(1)

        charmm_gui_output = orm.load_node(existing_folder_pk)
        wc = submit(
            BuildMembraneWorkChain,
            protocol=protocol,
            charmm_gui_output=charmm_gui_output,
        )
        print(f"Submitted BuildMembraneWorkChain in dev mode: pk={wc.pk}")
    else:
        # Live mode: CHARMM-GUI will be called.
        # Ensure the token file exists: `aiida-charmm-gui login`
        wc = submit(BuildMembraneWorkChain, protocol=protocol)
        print(f"Submitted BuildMembraneWorkChain in live mode: pk={wc.pk}")

    print(f"\nMonitor with:  verdi process show {wc.pk}")


if __name__ == "__main__":
    main()
