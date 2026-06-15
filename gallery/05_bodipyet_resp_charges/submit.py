"""Gallery example 5: RESP charge distribution for BODIPY-Et — end-to-end submission.

Pipeline: RDKit ETKDG conformers → XTB2 pre-opt (OrcaPreoptWorkChain) →
B3LYP/def2-SVP OPT + RESP (OrcaOptWorkChain), in vacuum and CPCM water.

Molecule: BODIPY-Et — neutral fluorescent dye with ethyl meso-substituent.
Charge: 0, multiplicity: 1.

Note: the SMILES uses [B-] and [N+] to represent the zwitterionic boron-dipyrrin
core; RDKit treats this as a neutral molecule (charge sums to 0).

Requirements
------------
- AiiDA daemon running:        verdi daemon start
- ORCA registered:             verdi code list
- aiida-orca (fork):           pip install -e "git+https://github.com/ovcarj/aiida-orca.git@update-orca-parser#egg=aiida-orca"
- RDKit:                       pip install rdkit

Run:

    python gallery/05_bodipyet_resp_charges/submit.py

Monitor:

    verdi process show <pk>
    verdi process report <pk>

Inspect RESP charges after completion:

    from aiida import load_profile, orm
    load_profile()
    n = orm.load_node(<pk>)
    for solvent in ['vacuum', 'water']:
        p = n.outputs.results[solvent].output_parameters.get_dict()
        print(solvent, 'RESP:', p['atomcharges']['resp'])

Store results in remolecule:

    remolecule import aiida --pk <pk>

    remolecule list
    remolecule show <uuid>
"""

from __future__ import annotations

from pathlib import Path

import yaml
from aiida import load_profile, orm
from aiida.engine import submit

ORCA_CODE_LABEL = "orca_6_1_1@localhost"

# SMILES for BODIPY-Et (RDKit-canonical)
# [B-]/[N+] zwitterion notation for the boron-dipyrrin core; net charge = 0.
SMILES = "CCc1ccc(C2=C3C(C)=CC(C)=[N+]3[B-](F)(F)n3c(C)cc(C)c32)cc1"


def main():
    load_profile()

    protocol_path = Path(__file__).parent / "protocol.yaml"
    with protocol_path.open() as fh:
        protocol = orm.Dict(yaml.safe_load(fh))

    options = orm.Dict({
        "resources": {"num_machines": 1, "num_mpiprocs_per_machine": 64},
        "queue_name": "cm",
        "max_wallclock_seconds": 43200,   # 12 h
        "withmpi": False,
    })

    from tracy.workflows.molecule_charges import MoleculeChargeDistributionWorkChain

    wc = submit(
        MoleculeChargeDistributionWorkChain,
        smiles=orm.Str(SMILES),
        protocol=protocol,
        code=orm.load_code(ORCA_CODE_LABEL),
        options=options,
    )
    print(f"Submitted MoleculeChargeDistributionWorkChain  pk={wc.pk}")
    print(f"\nMonitor with:  verdi process show {wc.pk}")
    print(f"Full log:      verdi process report {wc.pk}")


if __name__ == "__main__":
    main()
