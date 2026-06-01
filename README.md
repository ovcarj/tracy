# tracy

AiiDA-based workflow package for building and simulating mitochondrial membrane systems.

## Overview

`tracy` orchestrates a multi-step computational workflow for mitochondrial membrane research using [AiiDA](https://www.aiida.net) for provenance tracking and workflow management.

```
CHARMM-GUI membrane construction  →  BuildMembraneWorkChain
GROMACS molecular dynamics        →  RunMembraneMDWorkChain
Electrostatic potential           →  ComputeMembranePotentialWorkChain
```

Each stage is a separate, independently testable WorkChain.

## Requirements

- Python ≥3.11
- [AiiDA](https://aiida.net) 2.6.3
- [aiida-charmm-gui](https://github.com/ovcarj/aiida-charmm-gui) 0.1.0a0
- A valid CHARMM-GUI account and API token

For GROMACS MD and electrostatics (optional):
- [aiida-gromacs](https://github.com/ovcarj/aiida-gromacs/tree/fix-itp-dirs-upload) 2.2.1, branch `fix-itp-dirs-upload` (fork of CCPBioSim/aiida-gromacs)
  — contains two fixes not yet merged upstream: MdrunParser index misalignment when
  `nstxout-compressed > 0`, and sandbox subdirectory creation for `itp_dirs`/`plumed_dirs`
- GROMACS 2021.7

## Installation

```bash
pip install -e .
```

With GROMACS support:

```bash
pip install -e ".[gromacs]"
```

Install the patched aiida-gromacs from the required branch:

```bash
pip install -e "git+https://github.com/ovcarj/aiida-gromacs.git@fix-itp-dirs-upload#egg=aiida-gromacs"
```

Register the AiiDA entry points after installation:

```bash
verdi plugin list aiida.workflows
# should show: tracy.build_membrane, tracy.gromacs_run, tracy.run_membrane_md,
#              tracy.compute_membrane_potential, tracy.create_index_groups
verdi plugin list aiida.calculations
# should show: tracy.trjconv, tracy.potential, tracy.select_groups
```

---

## BuildMembraneWorkChain

Builds a membrane via CHARMM-GUI Quick Bilayer and extracts a GROMACS-ready input bundle.

**Entry point:** `tracy.build_membrane`

**Inputs**

| Name | Type | Required | Description |
|---|---|---|---|
| `protocol` | `Dict` | yes | Tracy protocol (see below) |
| `charmm_gui_output` | `FolderData` | no | Pre-existing CHARMM-GUI output; skips the API call |

**Outputs**

| Name | Type | Description |
|---|---|---|
| `charmm_gui_output` | `FolderData` | Raw CHARMM-GUI output archive |
| `gromacs_input_bundle` | `FolderData` | Extracted GROMACS-ready input files |
| `system_metadata` | `Dict` | System name, CHARMM-GUI job info, available MD engines |
| `validation_report` | `Dict` | Structured validation of the GROMACS bundle |

### Protocol format

```yaml
system:
  name: my_membrane
  description: Brief description

charmm_gui:
  module: membrane_builder
  quick_bilayer:
    membtype: PMm
    membrane_only: true
    margin: 20.0
    wdist: 22.5
    ion_conc: 0.15
    ion_type: NaCl

tracy:
  expected_engine: gromacs
  membrane_normal_axis: z
  require_gromacs_files: true
```

An example protocol is provided at `examples/protocols/mitochondrial_membrane.yaml`.

### Submitting

```python
from aiida import load_profile, orm
from aiida.engine import submit
import yaml

load_profile()

with open("examples/protocols/mitochondrial_membrane.yaml") as f:
    protocol = orm.Dict(yaml.safe_load(f))

from tracy.workflows.membrane_builder import BuildMembraneWorkChain
wc = submit(BuildMembraneWorkChain, protocol=protocol)
print(f"pk={wc.pk}")
```

Or use the bundled example script:

```bash
python examples/build_membrane.py
```

### Authentication

Authenticate with CHARMM-GUI once before submitting:

```bash
aiida-charmm-gui login
```

### Development mode

Pass a previously stored `FolderData` as `charmm_gui_output` to skip the API call:

```python
wc = submit(
    BuildMembraneWorkChain,
    protocol=protocol,
    charmm_gui_output=orm.load_node(<pk>),
)
```

### GROMACS bundle output

A successful run produces a `gromacs_input_bundle` (`FolderData`) containing:

```
step5_input.gro
topol.top
toppar/                    # force-field parameter files (.itp)
step6.0_minimization.mdp
step6.1_equilibration.mdp
  ...
step6.6_equilibration.mdp
step7_production.mdp
index.ndx
```

---

## RunMembraneMDWorkChain

Runs a CHARMM-GUI GROMACS bundle through the full MD protocol — minimization, staged
NPT equilibration, and production — using [aiida-gromacs](https://github.com/CCPBioSim/aiida-gromacs).
Each step is a separate provenance-tracked `grompp + mdrun` pair.

Step-to-step continuation uses the `.gro` output (which carries velocities). CHARMM-GUI
equilibration MDPs use `continuation = yes` to read velocities from the input structure
rather than regenerating them; checkpoints are not forwarded between steps.

**Entry point:** `tracy.run_membrane_md`

**Inputs**

| Name | Type | Required | Description |
|---|---|---|---|
| `md_input_bundle` | `FolderData` | yes | CHARMM-GUI GROMACS bundle (output of `BuildMembraneWorkChain` or loaded from disk) |
| `protocol` | `Dict` | yes | Tracy protocol (see below) |
| `code` | `AbstractCode` | yes | Registered GROMACS code (`verdi code list`) |
| `options` | `Dict` | no | AiiDA scheduler options (resources, walltime, queue) |

**Outputs**

| Name | Type | Description |
|---|---|---|
| `md_results` | `FolderData` | Output files from the last completed step |
| `md_report` | `Dict` | Per-step record (name, prefix, mdp, step_id, pk) and final exit status |

### Protocol format

```yaml
tracy:
  expected_engine: gromacs
  membrane_normal_axis: z
  md_steps:
    - minimization
    - equilibration   # step6.1
    - equilibration   # step6.2
    - equilibration   # step6.3
    - equilibration   # step6.4
    - equilibration   # step6.5
    - equilibration   # step6.6
    - production
  mdp_overrides:            # optional per-step MDP patches
    production:
      nstxout-compressed: "1000"
```

**`md_steps`** is an explicit ordered sequence. Each entry consumes the next matching step
from the CHARMM-GUI manifest in order. Repeating `"equilibration"` six times runs all six
equilibration stages (`step6.1` through `step6.6`) sequentially.

**`mdp_overrides`** patches MDP key-value pairs before submission, with three levels of
specificity (most specific wins):

| Key form | Example | Applies to |
|---|---|---|
| CHARMM-GUI step ID | `"step6.3"` | that step only |
| unique prefix | `"equilibration_3"` | that step only |
| generic name | `"equilibration"` | all equilibration steps |

Patching is tracked as an AiiDA `calcfunction` so the modified MDP is part of the provenance graph.

### Output file naming

Output files are named after each step with a numeric suffix for repeated steps:

```
minimization.gro / .trr / .edr / .log / .tpr
equilibration_1.gro / .xtc / .edr / .log / .tpr / .cpt
equilibration_2.gro / ...
...
equilibration_6.gro / ...
production.gro / .xtc / .edr / .log / .tpr / .cpt
```

### Submitting

```python
from aiida import load_profile, orm
from aiida.engine import submit

load_profile()

bundle = orm.FolderData()
bundle.put_object_from_tree("path/to/gromacs_bundle")
bundle.store()

protocol = orm.Dict({
    "tracy": {
        "expected_engine": "gromacs",
        "membrane_normal_axis": "z",
        "md_steps": ["minimization",
                     "equilibration", "equilibration", "equilibration",
                     "equilibration", "equilibration", "equilibration",
                     "production"],
    },
})

options = orm.Dict({
    "resources": {"num_machines": 1, "num_mpiprocs_per_machine": 64},
    "max_wallclock_seconds": 21600,
    "withmpi": True,
    # "queue_name": "partition",  # SLURM --partition / PBS -q
})

from tracy.workflows.membrane_md import RunMembraneMDWorkChain
wc = submit(
    RunMembraneMDWorkChain,
    md_input_bundle=bundle,
    protocol=protocol,
    code=orm.load_code("gmx@cluster"),
    options=options,
)
print(f"pk={wc.pk}")
```

Or use the bundled example script:

```bash
python examples/run_membrane_md_gromacs.py
```

---

## GromacsRunWorkChain

A thin, generic WorkChain wrapping a single `grompp + mdrun` pair. Knows nothing about
membranes or CHARMM-GUI; called by `RunMembraneMDWorkChain` for each step.

**Entry point:** `tracy.gromacs_run`

**Outputs** include `output_structure`, `energy`, `log`, `tpr_file` (always), and
`trajectory`, `trajectory_compressed`, `checkpoint` (conditional on MDP settings — the
integrator and `nstxout-compressed` are read from the MDP file automatically).

`tpr_file` is always exposed so that downstream workchains (e.g.
`ComputeMembranePotentialWorkChain`) can pass it to analysis tools without re-running grompp.

---

## ComputeMembranePotentialWorkChain

Computes the electrostatic potential profile φ(z) across the membrane from a production
trajectory. Engine-agnostic: dispatches to GROMACS tools via adapter functions; other
engines can be added by implementing new adapters.

Pipeline:
1. Trajectory preprocessing (`gmx trjconv`) — centres membrane, fixes PBC
2. Optional: create new index groups (`gmx select`) via `CreateIndexGroupsWorkChain`
3. `gmx potential` — one run per group, all in parallel; total + per-component profiles

**Entry point:** `tracy.compute_membrane_potential`

**Inputs**

| Name | Type | Required | Description |
|---|---|---|---|
| `tpr_file` | `SinglefileData` | yes | `.tpr` from the production `GromacsRunWorkChain` |
| `trajectory_compressed` | `SinglefileData` | yes | `.xtc` from the production run |
| `index_file` | `SinglefileData` | no | `.ndx` index file |
| `protocol` | `Dict` | yes | Tracy protocol (see below) |
| `code` | `AbstractCode` | yes | Registered GROMACS code |
| `options` | `Dict` | no | AiiDA scheduler options |

**Outputs**

| Name | Type | Description |
|---|---|---|
| `potential_profile` | `SinglefileData` | `potential.xvg` for total group |
| `potential_report` | `Dict` | Axis, slices, groups, component list, symmetrize flag |
| `potential_components.<group>` | `SinglefileData` | Per-component `.xvg` (one per entry in `potential_component_groups`) |

### Protocol format

```yaml
tracy:
  expected_engine: gromacs
  membrane_normal_axis: z
  potential_slices: 100            # number of z-slices for gmx potential
  trjconv_center_group: "MEMB"     # index group to centre on
  trjconv_output_group: "SYSTEM"   # index group to write out
  potential_charge_group: "SYSTEM" # group for total potential
  potential_component_groups:      # optional: per-group decomposition (run in parallel)
    - "MEMB"
    - "Water"
    - "ION"
  new_index_groups:                # optional: create additional groups before analysis
    - '"Water" resname TIP3'       # gmx-select syntax; CHARMM36 water residue name
    - '"ION" resname POT CLA'      # CHARMM36 K+ and Cl- residue names
  potential_symmetrize: false      # true for symmetric bilayers (post-processing only)
  potential_correct: true          # -correct flag: assume net-zero charge
```

**Per-group decomposition**: by linearity of Poisson's equation,
φ(MEMB) + φ(Water) + φ(ION) = φ(SYSTEM). Each component is run as a separate
`gmx potential` job in parallel and stored as `potential_components.<group>`.

**`new_index_groups`**: CHARMM-GUI Quick Bilayer produces only `MEMB`, `SOLV`, `SYSTEM`.
To decompose `SOLV` into `Water` and `ION`, supply `new_index_groups` with
`gmx select` selection strings. Residue names are force-field dependent:

| Force field | Water | K⁺ | Cl⁻ |
|---|---|---|---|
| CHARMM36 (CHARMM-GUI) | `TIP3` | `POT` | `CLA` |
| AMBER | `WAT` / `HOH` | `Na+` | `Cl-` |
| GROMOS | `SOL` | `NA` | `CL` |

`potential_symmetrize` averages φ(z) with φ(L−z) at plot time. GROMACS 2021 has no
`-symm` flag; symmetrization is applied in post-processing.

### Production MDP requirement

The production MDP must have `nstxout-compressed > 0` to write a `.xtc` trajectory.
Use `mdp_overrides` in the `RunMembraneMDWorkChain` protocol if the default MDP does
not include this:

```yaml
mdp_overrides:
  production:
    nstxout-compressed: "25000"
```

### Submitting

```python
from aiida import load_profile, orm
from aiida.engine import submit

load_profile()

md_wc = orm.load_node(<RunMembraneMDWorkChain_pk>)
production_wc = sorted(md_wc.called, key=lambda n: n.pk)[-1]

protocol = orm.Dict({
    "tracy": {
        "expected_engine": "gromacs",
        "membrane_normal_axis": "z",
        "potential_slices": 200,
        "trjconv_center_group": "MEMB",
        "trjconv_output_group": "SYSTEM",
        "potential_charge_group": "SYSTEM",
        "new_index_groups": ['"Water" resname TIP3', '"ION" resname POT CLA'],
        "potential_component_groups": ["MEMB", "Water", "ION"],
        "potential_symmetrize": False,
        "potential_correct": True,
    },
})

from tracy.workflows.electrostatics import ComputeMembranePotentialWorkChain
wc = submit(
    ComputeMembranePotentialWorkChain,
    tpr_file=production_wc.outputs.tpr_file,
    trajectory_compressed=production_wc.outputs.trajectory_compressed,
    index_file=production_wc.inputs.index_file,
    protocol=protocol,
    code=orm.load_code("gmx@cluster"),
)
print(f"pk={wc.pk}")
```

Or use the bundled example script:

```bash
python examples/compute_membrane_potential_gromacs.py
```

---

## CreateIndexGroupsWorkChain

Creates new named atom groups from selection strings and appends them to an existing
index file. Useful for splitting CHARMM-GUI's `SOLV` group into separate `Water` and
`ION` groups before electrostatic analysis.

**Entry point:** `tracy.create_index_groups`

**Inputs**

| Name | Type | Required | Description |
|---|---|---|---|
| `tpr_file` | `SinglefileData` | yes | Topology reference for atom information |
| `index_file` | `SinglefileData` | no | Existing `.ndx` to append to |
| `selections` | `List` | yes | `gmx select` selection strings |
| `protocol` | `Dict` | yes | Tracy protocol (`expected_engine` key) |
| `code` | `AbstractCode` | yes | Registered GROMACS code |
| `options` | `Dict` | no | AiiDA scheduler options |

**Output**: `index_file` (`SinglefileData`) — original groups + newly created groups.

The original groups are never modified:
```
Before:  [ MEMB ]  [ SOLV ]  [ SYSTEM ]
After:   [ MEMB ]  [ SOLV ]  [ SYSTEM ]  [ Water ]  [ ION ]
```

Internally runs `SelectGroupsCalculation` (`gmx select`) to create the new groups,
then merges with the original index via `merge_index_files` (plain-text concatenation,
tracked as an AiiDA `calcfunction`).

---

## Testing

```bash
pytest tests/
```

Tests do not require a live CHARMM-GUI connection or a GROMACS installation.

## License

MIT
