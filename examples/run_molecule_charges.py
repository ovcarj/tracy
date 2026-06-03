"""Example: compute per-atom RESP charges for a molecule via MoleculeChargeDistributionWorkChain.

Pipeline:

  1. RDKit ETKDG — generate N conformers (local calcfunction, runs synchronously)
  2. OrcaPreoptWorkChain — parallel XTB2 geometry optimisation per conformer;
     returns the top-K lowest-energy structures.
  3. OrcaOptWorkChain — parallel B3LYP/def2-SVP OPT + RESP per structure;
     returns the lowest-energy conformer and its RESP charge distribution.

Results are namespaced by solvent: outputs.results.vacuum.* and
outputs.results.water.* (remove solvents you do not need from the protocol).

Prerequisites:
  - An active AiiDA daemon (``verdi daemon start``).
  - An ORCA code registered in AiiDA (``verdi code list``).
  - RDKit installed (``pip install rdkit``).
  - aiida-orca installed from the fork:
      pip install -e "git+https://github.com/ovcarj/aiida-orca.git@update-orca-parser#egg=aiida-orca"

Run::

    python examples/run_molecule_charges.py

Monitor::

    verdi process list
    verdi process show <pk>
    verdi process report <pk>

Inspect RESP charges after completion::

    from aiida import load_profile, orm
    load_profile()
    n = orm.load_node(<pk>)
    for solvent in ['vacuum', 'water']:
        p = n.outputs.results[solvent].output_parameters.get_dict()
        cr = n.outputs.results[solvent].charge_report.get_dict()
        print(f'--- {solvent} ---')
        print('RESP charges:', p['atomcharges']['resp'])
        print('Atoms:       ', p['atomnos'])
        print('Best energy: ', cr['best_energy'])

Store results in remolecule::

    remolecule import aiida --pk <pk>
"""

from __future__ import annotations

from aiida import load_profile, orm
from aiida.engine import submit

from tracy.workflows.molecule_charges import MoleculeChargeDistributionWorkChain


def main():
    load_profile()

    # -------------------------------------------------------------------------
    # Configuration — adjust to your cluster setup.
    # -------------------------------------------------------------------------

    # AiiDA code label for ORCA (check with: verdi code list)
    ORCA_CODE = "orca@cluster"  # replace with your code label

    # ORCA manages its own MPI (withmpi=False in AiiDA).
    # num_mpiprocs_per_machine MUST equal the nproc value in %pal below;
    # mismatching causes SLURM to allocate too few slots and ORCA's
    # internal mpirun call fails.
    N_PROCS = 4

    options = orm.Dict({
        "resources": {"num_machines": 1, "num_mpiprocs_per_machine": N_PROCS},
        "queue_name": "your_queue",     # replace with your queue name
        "max_wallclock_seconds": 7200,  # 2 h; enough for XTB preopt + DFT opt
        "withmpi": False,
    })

    # -------------------------------------------------------------------------
    # Protocol
    # -------------------------------------------------------------------------
    protocol = orm.Dict({
        "tracy": {
            "conformer_engine": "rdkit",   # conformer generator
            "expected_engine":  "orca",    # QC engine for preopt + opt + RESP
            "solvents":         [None, "Water"],  # None = vacuum, "Water" = CPCM
            "n_conformers":      20,       # RDKit ETKDG conformers to generate
            "random_seed":       42,
            "run_preopt":        True,     # set False to skip XTB and go straight to DFT
            "preopt_top_k":      5,        # top-K XTB structures passed to DFT
            "charge":            0,
            "multiplicity":      1,
        },
        "orca": {
            "preopt": {
                "method": "XTB2",
                "input_blocks": {"pal": {"nproc": N_PROCS}},
            },
            "opt": {
                "method":       "B3LYP",
                "basis":        "def2-SVP",
                "dispersion":   "D3BJ",
                "resp_keyword": "RESP",    # ORCA 6 native RESP keyword; produces atomcharges['resp']
                "input_blocks": {"pal": {"nproc": N_PROCS}},
            },
        },
    })

    # -------------------------------------------------------------------------
    # Submit
    # -------------------------------------------------------------------------
    wc = submit(
        MoleculeChargeDistributionWorkChain,
        smiles=orm.Str("CCO"),          # ethanol; replace with your SMILES
        protocol=protocol,
        code=orm.load_code(ORCA_CODE),
        options=options,
    )

    print(f"Submitted MoleculeChargeDistributionWorkChain  pk={wc.pk}")
    print(f"Monitor:  verdi process list")
    print(f"Details:  verdi process show {wc.pk}")
    print(f"Report:   verdi process report {wc.pk}")


if __name__ == "__main__":
    main()
