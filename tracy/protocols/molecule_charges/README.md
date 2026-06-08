# Molecule charge distribution protocol directory

Protocol files for `MoleculeChargeDistributionWorkChain`.

## Pipeline

```
generate_conformers  (RDKit ETKDG — local calcfunction)
    ↓  FolderData of .xyz files
OrcaPreoptWorkChain  (parallel XTB2 OPT per conformer)
    ↓  top-K structures by energy
OrcaOptWorkChain     (parallel DFT OPT + RESP per structure)
    ↓  lowest-energy relaxed_structure + output_parameters
```

Results are namespaced by solvent key: `outputs.results.vacuum.*`,
`outputs.results.water.*`, etc. Remove solvents you do not need from
`tracy.solvents`.

## Key protocol fields

`tracy.n_conformers` — number of ETKDG starting geometries. 10–20 is
sufficient for drug-like molecules; increase for flexible macrocycles.

`tracy.run_preopt` — set `false` to skip XTB and submit all conformers
directly to DFT. Use only for very small molecules (< 10 heavy atoms)
or when XTB converges poorly.

`tracy.preopt_top_k` — how many XTB-relaxed conformers proceed to DFT.
The DFT cost grows linearly with this number; 3–5 is usually enough.

`orca.opt.resp_keyword` — use `RESP` (ORCA 6 native) which produces
`atomcharges['resp']` in the parsed output. Do not use `CHELPG` unless
you specifically want ESP-fitted charges with the CHELPG scheme.

`orca.opt.input_blocks.pal.nproc` — **must equal** `num_mpiprocs_per_machine`
in the scheduler options. ORCA manages its own MPI (`withmpi: false` in
AiiDA); mismatching the slot count causes ORCA's internal `mpirun` to fail.

## Protonation state

RESP charges are computed for the SMILES as supplied. **Protonation state and
tautomer selection are the user's responsibility.** For drug-like molecules at
physiological pH, assign ionization state before passing SMILES:

- Weakly basic amines (pKa ~8–10) — likely protonated at pH 7.4 → use `[NH2+]`
- Carboxylic acids (pKa ~3–5) — likely deprotonated at pH 7.4 → use `[O-]`
- Lipophilic cations and mitochondria-targeting agents — charge state is the
  key variable for E(z); compute both neutral and protonated forms.

Tools: Dimorphite-DL for automated pH-aware enumeration; RDKit
`Chem.MolFromSmiles` + `Chem.AddHs` for explicit hydrogen assignment.

## Storing results

```bash
remolecule --db ~/.remolecule import aiida --pk <MoleculeChargeDistributionWorkChain_pk>
remolecule --db ~/.remolecule show <uuid>
```

## Provided files

`b3lyp_resp.yaml` — B3LYP/def2-SVP + RESP protocol validated on ethanol (CCO,
AiiDA pk=5664). Runs in vacuum and CPCM(water). 4 MPI processes per ORCA job.
Adjust `nproc` and scheduler `num_mpiprocs_per_machine` together.
