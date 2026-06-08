# Tracy protocol files

Each WorkChain accepts a `protocol` input (`orm.Dict`). Protocol files are
plain YAML dictionaries — load them with:

```python
import yaml
from aiida import orm
protocol = orm.Dict(yaml.safe_load(open("protocol.yaml")))
```

## Full pipeline

```
BuildMembraneWorkChain              membrane_builder/
    ↓  gromacs_input_bundle
RunMembraneMDWorkChain              membrane_md/
    ↓  trajectory_compressed, tpr_file
ComputeMembranePotentialWorkChain   electrostatics/
    ↓  potential_profile              → remembrane database
MoleculeChargeDistributionWorkChain molecule_charges/
    ↓  output_parameters (RESP)       → remolecule database
ElectrostaticEnergyWorkChain        electrostatic_energy/
    ↓  electrostatic_energy_report    → retrace database
```

## Directory map

| Directory | WorkChain(s) | What the protocol controls |
|---|---|---|
| `membrane_builder/` | `BuildMembraneWorkChain` | Lipid composition, box geometry, force field, ion type |
| `membrane_md/` | `RunMembraneMDWorkChain` | MD step sequence, MDP overrides, HMR, XTC output |
| `electrostatics/` | `ComputeMembranePotentialWorkChain` | Slice count, component groups, symmetrization, convergence check |
| `molecule_charges/` | `MoleculeChargeDistributionWorkChain` | Conformer generation, pre-opt level, DFT level, RESP keyword |
| `electrostatic_energy/` | `ElectrostaticEnergyWorkChain` | Charges model, scan resolution, z range |

## Companion databases

| Package | Stores | Imports from |
|---|---|---|
| `remembrane` | Electrostatic potential profiles φ(z) | `ComputeMembranePotentialWorkChain` |
| `remolecule` | Per-atom RESP/Mulliken charges, conformer ensembles | `MoleculeChargeDistributionWorkChain` |
| `retrace` | E(z) profiles, cross-references remembrane + remolecule | `ElectrostaticEnergyWorkChain` |
