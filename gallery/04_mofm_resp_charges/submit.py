"""Gallery example 4: RESP charge distribution for mofm — end-to-end submission.

Pipeline: RDKit ETKDG conformers → XTB2 pre-opt (OrcaPreoptWorkChain) →
B3LYP/def2-SVP OPT + RESP (OrcaOptWorkChain), in vacuum and CPCM water.

Molecule: mofm — C₂₃H₁₈F₃NO₄S, same scaffold as fm with an added OMe group
para to CF₃ on the pendant phenyl ring.
Charge: 0, multiplicity: 1.

Requirements
------------
- AiiDA daemon running:        verdi daemon start
- ORCA registered:             verdi code list
- aiida-orca (fork):           pip install -e "git+https://github.com/ovcarj/aiida-orca.git@update-orca-parser#egg=aiida-orca"
- RDKit:                       pip install rdkit

Run:

    python gallery/04_mofm_resp_charges/submit.py

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

# SMILES for mofm (C₂₃H₁₈F₃NO₄S)
# Same scaffold as fm with an additional OMe donor on the CF₃-bearing phenyl ring.
SMILES = "COc1ccc(C2=C3C=CC(=O)C=C3S(=O)(=O)c3cc(N(C)C)ccc32)c(C(F)(F)F)c1"


def main():
    load_profile()

    protocol_path = Path(__file__).parent / "protocol.yaml"
    with protocol_path.open() as fh:
        protocol = orm.Dict(yaml.safe_load(fh))

    # ORCA manages its own MPI (withmpi=False in AiiDA).
    # num_mpiprocs_per_machine must equal nproc in %pal (set to 64 in protocol.yaml).
    options = orm.Dict({
        "resources": {"num_machines": 1, "num_mpiprocs_per_machine": 64},
        "queue_name": "cm",
        "max_wallclock_seconds": 43200,   # 12 h; covers 10 XTB preopt + 3 DFT OPT jobs
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
