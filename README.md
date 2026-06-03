# tracy

AiiDA-based workflow package for building and simulating mitochondrial membrane systems.

## Overview

`tracy` orchestrates a multi-step computational workflow for mitochondrial membrane research using [AiiDA](https://www.aiida.net) for provenance tracking and workflow management.

```
CHARMM-GUI membrane construction  →  BuildMembraneWorkChain
GROMACS molecular dynamics        →  RunMembraneMDWorkChain
Electrostatic potential           →  ComputeMembranePotentialWorkChain
Molecular charge distribution     →  MoleculeChargeDistributionWorkChain
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

For molecular charge distribution (optional):
- [aiida-orca](https://github.com/ovcarj/aiida-orca/tree/update-orca-parser), branch `update-orca-parser` (fork of ezpzbz/aiida-orca)
  — contains two fixes required for ORCA 6 + XTB support: RESP charge extraction from
  `RESP Charges` output section (commit `4bad37f`), and XTB energy parsing for ORCA 6
  calculations where there is no SCF block (commit `50afef8`)
- ORCA 6.x (tested with 6.1.1)

## Installation

```bash
pip install -e .
```

With GROMACS support:

```bash
pip install -e ".[gromacs]"
pip install -e "git+https://github.com/ovcarj/aiida-gromacs.git@fix-itp-dirs-upload#egg=aiida-gromacs"
```

With ORCA molecular charge support:

```bash
pip install -e ".[orca]"
pip install -e "git+https://github.com/ovcarj/aiida-orca.git@update-orca-parser#egg=aiida-orca"
```

The `aiida-orca` fork (`update-orca-parser` branch) is required — the PyPI version does not
support ORCA 6 RESP charges or XTB energy parsing.

Verify that AiiDA has discovered the entry points (other installed plugins also appear):

```bash
verdi plugin list aiida.workflows
# tracy entries: tracy.build_membrane, tracy.gromacs_run, tracy.run_membrane_md,
#                tracy.compute_membrane_potential, tracy.create_index_groups,
#                tracy.molecule_charges, tracy.orca_preopt, tracy.orca_opt,
#                tracy.electrostatic_energy
verdi plugin list aiida.calculations
# tracy entries: tracy.trjconv, tracy.potential, tracy.select_groups
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
  name: mitochondrial_inner_membrane
  description: Mammalian IMM — asymmetric PC/PE/cardiolipin bilayer

charmm_gui:
  module: membrane_builder
  quick_bilayer:
    upper: "POPE:POPC:TLCL2=40:40:20"   # IMS-facing leaflet
    lower: "POPE:POPC:TLCL2=45:35:20"   # matrix-facing leaflet
    membrane_only: true
    margin: 20.0
    wdist: 22.5
    ion_conc: 0.15
    ion_type: KCl
    run_ff_converter: true
    temperature: 310.15

tracy:
  expected_engine: gromacs
  membrane_normal_axis: z
  require_gromacs_files: true
```

The full reference protocol with all configuration options and example compositions is at
`tracy/protocols/charmm_gui/mitochondrial_membrane.yaml`.

### CHARMM36/36m lipid residue codes

Use these codes in the `upper` / `lower` composition strings.
Verify names against the CHARMM-GUI Membrane Builder lipid library before submitting —
new lipids are added regularly.

**Phosphatidylcholines (PC) — neutral**

| Code | Acyl chains | Notes |
|---|---|---|
| `DPPC` | 16:0 / 16:0 | gel phase at 298 K [[1]](https://doi.org/10.1021/jp101759q) |
| `POPC` | 16:0 / 18:1 | most common model PC [[1]](https://doi.org/10.1021/jp101759q) |
| `DOPC` | 18:1 / 18:1 | |
| `PLPC` | 16:0 / 18:2 n-6 | representative linoleoyl PC for mammalian mitochondrial models [[2]](https://doi.org/10.1016/0005-2736(90)90036-n)[[3]](https://doi.org/10.1016/0005-2736(76)90353-9) |
| `PAPC` | 16:0 / 20:4 n-6 | arachidonoyl |
| `SAPC` | 18:0 / 20:4 n-6 | representative arachidonoyl PC for mammalian mitochondrial models [[2]](https://doi.org/10.1016/0005-2736(90)90036-n)[[3]](https://doi.org/10.1016/0005-2736(76)90353-9) |
| `PDPC` | 16:0 / 22:6 n-3 | DHA (docosahexaenoyl) |
| `SDPC` | 18:0 / 22:6 n-3 | DHA; enriched in brain and retinal membranes [[4]](https://doi.org/10.1038/nrm2330) |

**Phosphatidylethanolamines (PE) — neutral**

| Code | Acyl chains | Notes |
|---|---|---|
| `DPPE` | 16:0 / 16:0 | |
| `POPE` | 16:0 / 18:1 | most common model PE [[5]](https://doi.org/10.1021/jz200167q) |
| `DOPE` | 18:1 / 18:1 | |
| `PLPE` | 16:0 / 18:2 n-6 | representative linoleoyl PE for mammalian mitochondrial models [[2]](https://doi.org/10.1016/0005-2736(90)90036-n) |
| `SAPE` | 18:0 / 20:4 n-6 | representative arachidonoyl PE for mammalian mitochondrial models [[2]](https://doi.org/10.1016/0005-2736(90)90036-n) |
| `SDPE` | 18:0 / 22:6 n-3 | DHA-PE; enriched in brain and retinal membranes [[4]](https://doi.org/10.1038/nrm2330) |

**Negatively charged lipids**

| Code | Type | Charge | Notes |
|---|---|---|---|
| `POPS` | PS | −1 | preferentially inner (cytoplasmic) leaflet [[4]](https://doi.org/10.1038/nrm2330) |
| `DOPS` | PS | −1 | |
| `POPG` | PG | −1 | major acidic lipid in bacteria and chloroplasts [[6]](https://doi.org/10.1146/annurev.biochem.66.1.199) |
| `DOPG` | PG | −1 | |
| `POPI` | PI | −1 | OMM, ER, and plasma membrane [[4]](https://doi.org/10.1038/nrm2330) |

**Cardiolipins (CL) — use suffix `2` (−2 e) at physiological pH**

| Code | Chains | Biological context |
|---|---|---|
| `TLCL2` | 18:2 × 4 | dominant cardiolipin species in mammalian heart mitochondria [[7]](https://doi.org/10.1016/S0163-7827(00)00005-9)[[10]](https://doi.org/10.1194/jlr.m600551-jlr200) |
| `TOCL2` | 18:1 × 4 | dominant species in yeast IMM [[8]](https://doi.org/10.1128/jb.173.6.2026-2034.1991) |
| `TPCL2` | 16:0 × 4 | |
| `TMCL2` | 14:0 × 4 | bacteria [[6]](https://doi.org/10.1146/annurev.biochem.66.1.199) |

Use suffix `1` (−1 e) only when modelling a partially protonated cardiolipin.

**Sphingomyelins (SM) — neutral**

| Code | N-acyl | Notes |
|---|---|---|
| `PSM` | 16:0 | most abundant SM species in mammalian plasma membrane [[4]](https://doi.org/10.1038/nrm2330) |
| `SSM` | 18:0 | |
| `BNSM` | 22:0 | |

**Sterols — neutral**

| Code | Name |
|---|---|
| `CHL1` | Cholesterol (mammalian) [[4]](https://doi.org/10.1038/nrm2330) |
| `ERG` | Ergosterol (yeast/fungal) [[8]](https://doi.org/10.1128/jb.173.6.2026-2034.1991) |

### Common compositions

Molar percentages; ratios must sum to 100 per leaflet. The compositions below are
**simplified simulation models** — the cited papers report lipid class distributions
at the whole-membrane level; exact molecular-species ratios and leaflet-specific
asymmetries are modeling choices, not values directly taken from the cited papers.
Mitochondrial inner/outer leaflet asymmetry is not well-characterised experimentally.

```yaml
# Mammalian IMM — simplified PC/PE/CL model:
# IMM enriched in PE, PC (together ~80%), and CL (~15-20%) [2,3,7].
# Leaflet split and TLCL2 species choice are modeling decisions.
upper: "POPE:POPC:TLCL2=40:40:20"
lower: "POPE:POPC:TLCL2=45:35:20"

# Mammalian IMM — PUFA-enriched species model:
# Mammalian mitochondrial PC and PE are enriched in unsaturated chains including 18:2 and 20:4 [2,3].
# SAPC, PLPC, SAPE are representative molecular species chosen to reflect this; ratios are modeling choices.
upper: "POPE:SAPC:PLPC:TLCL2=35:20:15:30"
lower: "POPE:SAPC:PLPC:TLCL2=38:18:12:32"

# Outer mitochondrial membrane (OMM) — simplified:
# OMM is PC/PE-rich with minor PI and PS; CL very low [2].
# Native OMM also contains SM and cholesterol, omitted here [9].
upper: "POPC:POPE:POPI:POPS=50:30:10:10"
lower: "POPC:POPE:POPI:POPS=48:32:12:8"

# Yeast IMM (S. cerevisiae) — simplified:
# S. cerevisiae IMM enriched in PE, PI, PC, and CL [8].
# TOCL2 chosen as representative of yeast CL (predominantly 18:1 chains [8]).
upper: "POPE:POPI:POPC:TOCL2=40:15:25:20"
lower: "POPE:POPI:POPC:TOCL2=35:15:30:20"

# Asymmetric plasma membrane — didactic raft-forming model:
# Outer leaflet SM/cholesterol-enriched; inner leaflet PE/PS-enriched [4].
# Species ratios are not derived from a primary source.
upper: "POPC:PSM:CHL1=25:40:35"           # outer leaflet
lower: "POPE:POPS:POPC:CHL1=45:15:15:25"  # inner leaflet
```

References: [[1]](https://doi.org/10.1021/jp101759q) Klauda et al. *J Phys Chem B* 2010 · [[2]](https://doi.org/10.1016/0005-2736(90)90036-n) Hovius et al. *BBA* 1990 · [[3]](https://doi.org/10.1016/0005-2736(76)90353-9) Comte et al. *BBA* 1976 · [[4]](https://doi.org/10.1038/nrm2330) van Meer et al. *Nat Rev Mol Cell Biol* 2008 · [[5]](https://doi.org/10.1021/jz200167q) Pastor & MacKerell *J Phys Chem Lett* 2011 · [[6]](https://doi.org/10.1146/annurev.biochem.66.1.199) Dowhan *Annu Rev Biochem* 1997 · [[7]](https://doi.org/10.1016/S0163-7827(00)00005-9) Schlame et al. *Prog Lipid Res* 2000 · [[8]](https://doi.org/10.1128/jb.173.6.2026-2034.1991) Zinser et al. *J Bacteriol* 1991 · [[9]](https://doi.org/10.3389/fmolb.2022.910936) Schiaffarino et al. *Front Mol Biosci* 2022 · [[10]](https://doi.org/10.1194/jlr.m600551-jlr200) Sparagna et al. *J Lipid Res* 2007

> **Ion residue names (CHARMM36):** KCl → `POT` (K⁺) / `CLA` (Cl⁻); NaCl → `SOD` (Na⁺) / `CLA` (Cl⁻).
> These names are required in the electrostatics protocol `new_index_groups` strings.

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

Step-to-step continuation uses the `.gro` output (which carries coordinates and
velocities). CHARMM-GUI equilibration MDPs set `continuation = yes` to read velocities
from the input structure rather than regenerating them. Checkpoints (`.cpt`) are **not**
forwarded between steps: GROMACS embeds the source filename and ensemble parameters in
each checkpoint, so passing a checkpoint from step N as `-cpi` to step N+1 causes an
incompatible-checkpoint crash. Each step starts clean from the `.gro` output of the
previous step.

Individual dynamics steps do write a `.cpt` checkpoint (exposed as the optional
`checkpoint` output of `GromacsRunWorkChain`). This is useful for resuming a crashed
step, not for chaining steps. See *Restart / resume* below.

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

### Restart / resume

If an MD step crashes (SLURM walltime, node failure), you can resume without re-running
completed steps. Two mechanisms are available:

**Automatic retry** — add `max_retries` to the protocol (default: 0):

```yaml
tracy:
  max_retries: 2   # retry each failed step up to 2 times before giving up
```

**Manual resume** — after a crash, find the last successful step and re-submit starting
from the failed step using the `initial_structure` input:

```python
from aiida import orm
from aiida.engine import run_get_node
from tracy.workflows.membrane_md import RunMembraneMDWorkChain

failed_run = orm.load_node(<failed_pk>)
last_good = max(
    (c for c in failed_run.called
     if c.is_finished_ok and c.process_label == "GromacsRunWorkChain"),
    key=lambda n: n.pk,
)

_, node = run_get_node(
    RunMembraneMDWorkChain,
    md_input_bundle=orm.load_node(<bundle_pk>),
    initial_structure=last_good.outputs.output_structure,
    protocol=orm.Dict({"tracy": {
        "expected_engine": "gromacs",
        "md_steps": ["equilibration_4", "equilibration_5", "equilibration_6", "production"],
        # ... rest of protocol
    }}),
    code=orm.load_code("gmx_mpi@cluster"),
    options=orm.Dict({...}),
)
```

The failed workchain's `md_report` output is available even on failure and contains
`steps_run` (completed steps with PKs) and `failed_step` (name of the crashed step).

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

## MoleculeChargeDistributionWorkChain

Computes per-atom RESP charge distributions for drug-like molecules.
Engine-agnostic at the top level: dispatches to ORCA sub-WorkChains based on
`protocol.tracy.expected_engine`.

Pipeline:
1. Conformer generation (`generate_conformers` calcfunction, RDKit ETKDG)
2. XTB pre-optimisation in parallel (`OrcaPreoptWorkChain`) — optional
3. DFT geometry optimisation + RESP charges in parallel (`OrcaOptWorkChain`)
4. Return lowest-energy result

**Entry point:** `tracy.molecule_charges`

**Inputs**

| Name | Type | Required | Description |
|---|---|---|---|
| `smiles` | `Str` | no† | SMILES string for conformer generation |
| `conformers` | `FolderData` | no† | Pre-generated XYZ conformers (skips step 1) |
| `protocol` | `Dict` | yes | Tracy protocol (see below) |
| `code` | `AbstractCode` | yes | ORCA code registered in AiiDA |
| `options` | `Dict` | no | AiiDA scheduler options |

†Either `smiles` or `conformers` must be provided.

**Outputs**

| Name | Type | Description |
|---|---|---|
| `relaxed_structure` | `StructureData` | Lowest-energy DFT-relaxed geometry |
| `output_parameters` | `Dict` | ORCA output including `atomcharges['resp']` |
| `charge_report` | `Dict` | Provenance metadata (preopt pk, opt pk, best energy) |

### Protocol format

```yaml
tracy:
  conformer_engine: rdkit    # default; only implementation currently
  expected_engine: orca      # default; only implementation currently
  n_conformers: 20           # RDKit ETKDG
  random_seed: 42
  run_preopt: true           # set false to skip XTB and go directly to DFT
  preopt_top_k: 5            # top-K lowest-energy conformers passed to DFT
  charge: 0
  multiplicity: 1
orca:
  preopt:
    method: XTB2
    input_blocks:
      pal:
        nproc: 4             # must match num_mpiprocs_per_machine in scheduler options
  opt:
    method: B3LYP
    basis: def2-SVP
    dispersion: D3BJ
    resp_keyword: RESP       # ORCA 6 native RESP keyword; produces atomcharges['resp']
    input_blocks:
      pal:
        nproc: 4
```

### Submitting

```python
from aiida import load_profile, orm
from aiida.engine import submit

load_profile()

ORCA_OPTIONS = orm.Dict({
    "resources": {"num_machines": 1, "num_mpiprocs_per_machine": 4},
    "queue_name": "cm",
    "max_wallclock_seconds": 7200,
    "withmpi": False,   # ORCA manages its own MPI
})

PROTOCOL = orm.Dict({
    "tracy": {
        "conformer_engine": "rdkit", "expected_engine": "orca",
        "n_conformers": 20, "random_seed": 42,
        "run_preopt": True, "preopt_top_k": 5,
        "charge": 0, "multiplicity": 1,
    },
    "orca": {
        "preopt": {"method": "XTB2", "input_blocks": {"pal": {"nproc": 4}}},
        "opt": {
            "method": "B3LYP", "basis": "def2-SVP", "dispersion": "D3BJ",
            "resp_keyword": "RESP",
            "input_blocks": {"pal": {"nproc": 4}},
        },
    },
})

from tracy.workflows.molecule_charges import MoleculeChargeDistributionWorkChain
wc = submit(
    MoleculeChargeDistributionWorkChain,
    smiles=orm.Str("CCO"),
    protocol=PROTOCOL,
    code=orm.load_code("orca@cluster"),
    options=ORCA_OPTIONS,
)
print(f"pk={wc.pk}")
```

### Inspecting RESP charges

```python
from aiida import load_profile, orm
load_profile()

n = orm.load_node(<pk>)
p = n.outputs.output_parameters.get_dict()
print("RESP charges:", p["atomcharges"]["resp"])
print("Atoms:       ", p["atomnos"])
print("Best energy: ", n.outputs.charge_report.get_dict()["best_energy"])
```

### ORCA operational notes

**RESP keyword**: use `! RESP` (ORCA 6 native, first-class keyword). Do not use
`! CHELPG` with `%chelpg RestrictedFit True end` — that is an ORCA 5 pattern and
produces `atomcharges['chelpg']`, not `['resp']`.

**MPI slots**: ORCA manages its own MPI (`withmpi: false` in AiiDA).
`num_mpiprocs_per_machine` in scheduler options **must equal** `nproc` in `%pal`.
Mismatching causes the SLURM job to allocate too few slots and ORCA's `mpirun -np N`
call fails with "not enough slots".

**Daemon restart**: after editing WorkChain source code, run `verdi daemon restart`.
The daemon caches Python imports; code changes are not picked up until restart.

---

## OrcaPreoptWorkChain

Parallel XTB pre-optimisation of conformers via ORCA. Accepts a `FolderData` of XYZ
files, submits one `OrcaBaseWorkChain` per conformer in parallel, ranks by final XTB
energy, and returns the top-K relaxed structures as `StructureData`.

Individual conformer failures are tolerated (unphysical geometries are expected to fail);
the WorkChain succeeds if at least `top_k` converge.

**Entry point:** `tracy.orca_preopt`

---

## OrcaOptWorkChain

Parallel DFT geometry optimisation + RESP charge calculation via ORCA. Accepts a
dynamic namespace of `StructureData` nodes (e.g. from `OrcaPreoptWorkChain`), submits
one `OrcaBaseWorkChain` per structure, and returns the lowest-energy converged result.

`opt_report` includes `charges_key` so downstream consumers know which
`atomcharges` key to read (e.g. `'resp'` for `! RESP`, `'chelpg'` for `! CHELPG`).

**Entry point:** `tracy.orca_opt`

---

---

## Companion packages

### [remolecule](https://github.com/ovcarj/remolecule)

Per-molecule RESP charge database storing vacuum and implicit-solvent DFT charge
distributions computed by the tracy pipeline.

`remolecule` stores the output of `MoleculeChargeDistributionWorkChain` as
structured records on disk — one record per run, with per-solvent geometries,
RESP/Mulliken/Löwdin charges, and full conformer ensembles in `.npz` format.
Results for multiple solvents (vacuum, CPCM water, …) are grouped in a single
record keyed by solvent name.

```bash
pip install "git+https://github.com/ovcarj/remolecule#egg=remolecule[aiida]"
remolecule init
remolecule import aiida --pk <MoleculeChargeDistributionWorkChain_pk>
remolecule list
remolecule show <uuid>
```

### [remembrane](https://github.com/ovcarj/remembrane)

Electrostatic potential database for membrane simulations.

`remembrane` stores the output of `ComputeMembranePotentialWorkChain` as
structured records on disk — one record per run, with the total potential
profile φ(z) and per-component decomposition (MEMB, Water, ION, …) stored as
numpy arrays alongside full composition and protocol metadata.

```bash
pip install "git+https://github.com/ovcarj/remembrane#egg=remembrane[aiida]"
remembrane init
remembrane import aiida --pk <ComputeMembranePotentialWorkChain_pk>
remembrane list
remembrane show <uuid>
remembrane plot <uuid> --components
```

### [retrace](https://github.com/ovcarj/retrace)

Database for electrostatic interaction energies between drug-like molecules and membrane potentials.

`retrace` stores the output of `ElectrostaticEnergyWorkChain` — the E(z) profile
of a molecule as it moves along the membrane normal, with its dipole oriented in
both directions. Records cross-reference remolecule and remembrane entries for
full traceability.

```bash
pip install "git+https://github.com/ovcarj/retrace#egg=retrace[aiida]"
retrace init
retrace import aiida --pk <ElectrostaticEnergyWorkChain_pk> \
    --remolecule ~/.remolecule --remembrane ~/.remembrane
retrace list
retrace show <uuid>
retrace query --inchikey <InChIKey>
```

---

## Testing

```bash
pytest tests/
```

Tests do not require a live CHARMM-GUI connection, a GROMACS installation, or an ORCA installation.

## License

MIT
