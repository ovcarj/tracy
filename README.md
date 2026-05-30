# tracy

AiiDA-based workflow package for building and simulating mitochondrial membrane systems.

## Overview

`tracy` orchestrates a multi-step computational workflow for mitochondrial membrane research using [AiiDA](https://www.aiida.net) for provenance tracking and workflow management.

```
CHARMM-GUI membrane construction  →  BuildMembraneWorkChain
GROMACS molecular dynamics        →  RunMembraneMDWorkChain
Electrostatic potential           →  (planned)
```

Each stage is a separate, independently testable WorkChain.

## Requirements

- Python ≥ 3.10
- [AiiDA](https://aiida.net) ≥ 2.5
- [aiida-charmm-gui](https://github.com/ovcarj/aiida-charmm-gui)
- A valid CHARMM-GUI account and API token

For GROMACS MD (optional):
- [aiida-gromacs](https://github.com/CCPBioSim/aiida-gromacs)
- A GROMACS installation registered as an AiiDA code

## Installation

```bash
pip install -e .
```

With GROMACS support:

```bash
pip install -e ".[gromacs]"
```

Register the AiiDA entry points after installation:

```bash
verdi plugin list aiida.workflows
# should show: tracy.build_membrane, tracy.gromacs_run, tracy.run_membrane_md
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

Runs a CHARMM-GUI GROMACS bundle through minimization and/or equilibration using [aiida-gromacs](https://github.com/CCPBioSim/aiida-gromacs). Each step is a separate provenance-tracked `grompp + mdrun` pair.

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
| `md_report` | `Dict` | List of steps run and final exit status |

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
  mdp_overrides:            # optional per-step MDP patches
    equilibration:
      nstxout-compressed: "1000"
```

**`md_steps`** is an explicit ordered sequence. Each entry consumes the next matching step from the CHARMM-GUI manifest in order. Repeating `"equilibration"` six times runs all six equilibration stages (`step6.1` through `step6.6`) sequentially. Listing it once runs only the first.

**`mdp_overrides`** patches MDP key-value pairs before submission. Keys are matched case-insensitively with hyphens and underscores treated as equivalent. New keys are appended if not already present. Patching is tracked as an AiiDA `calcfunction` so the modified MDP is part of the provenance graph.

### Output file naming

Output files are named after each step with a numeric suffix for repeated steps:

```
minimization.gro / .trr / .edr / .log / .tpr
equilibration_1.gro / .trr / .edr / .log / .tpr / .cpt
equilibration_2.gro / ...
...
equilibration_6.gro / ...
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
                     "equilibration", "equilibration", "equilibration"],
    },
})

options = orm.Dict({
    "resources": {"num_machines": 1, "num_mpiprocs_per_machine": 64},
    "max_wallclock_seconds": 3600,
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

### Short test runs

Use `mdp_overrides` to reduce step length without modifying the input files:

```python
"mdp_overrides": {
    "equilibration": {
        "nsteps": "500",
        "nstxout": "500",
        "nstxout-compressed": "0",
    },
},
```

---

## GromacsRunWorkChain

A thin, generic WorkChain wrapping a single `grompp + mdrun` pair. Engine-agnostic and reusable — knows nothing about membranes or CHARMM-GUI. Called by `RunMembraneMDWorkChain` for each step.

**Entry point:** `tracy.gromacs_run`

**Outputs** include `output_structure`, `trajectory`, `energy`, `log`, `tpr_file` (always), and `trajectory_compressed`, `checkpoint` (conditional on MDP settings).

The integrator and `nstxout-compressed` values are read from the MDP file to determine whether to request checkpoint and compressed trajectory outputs — no flags needed from the caller.

---

## Testing

```bash
pytest tests/
```

Tests do not require a live CHARMM-GUI connection or a GROMACS installation.

## License

MIT
