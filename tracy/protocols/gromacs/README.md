# GROMACS protocol directory

Protocol files for `RunMembraneMDWorkChain` and `ComputeMembranePotentialWorkChain`.

## Protonation state and molecular charge models

RESP charges computed by `MoleculeChargeDistributionWorkChain` are derived from the input
SMILES exactly as provided. **Protonation state and tautomer selection are the user's
responsibility.** For drug-like molecules at physiological pH, assign protonation states
before providing SMILES (e.g., using Dimorphite-DL for pH-aware enumeration, or
RDKit's `Chem.MolFromSmiles` followed by `Chem.AddHs` for neutral forms).

Incorrect protonation will produce charges for the wrong ionization state, leading to
a systematically wrong E(z) profile. This is particularly important for:
- Weakly basic amines (pKa ~8–10) — likely protonated at pH 7.4
- Carboxylic acids (pKa ~3–5) — likely deprotonated at pH 7.4
- Lipophilic cations / mitochondria-targeting agents — charge state is the key variable
