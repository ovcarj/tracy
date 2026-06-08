# Membrane builder protocol directory

Protocol files for `BuildMembraneWorkChain`.

## What the protocol controls

The `charmm_gui.quick_bilayer` section maps directly to the CHARMM-GUI
Quick Bilayer API. Key fields:

- `upper` / `lower` — lipid composition per leaflet, e.g. `"POPE:POPC:TLCL2=40:40:20"`.
  See the CHARMM-GUI lipid library at charmm-gui.org for available residue codes.
- `margin` — lateral box size (Å); determines the number of lipids placed per leaflet.
- `wdist` — water layer thickness per side (Å).
- `run_ff_converter: true` — required to produce GROMACS input files downstream.
- `charmmff_hmr_checked: true` — enables hydrogen mass repartitioning (4 fs timestep).
- `ion_type: KCl` or `NaCl` — affects ion residue names in the electrostatics protocol
  (`POT`/`CLA` for KCl, `SOD`/`CLA` for NaCl in CHARMM36).

## Provided files

`mitochondrial_membrane.yaml` — reference protocol for a cardiolipin-containing
asymmetric bilayer representative of the mitochondrial inner membrane. Includes
an annotated lipid library covering the major PC, PE, PS, PG, PI, CL, SM, and
sterol species available in CHARMM36/36m, with example compositions for the
mammalian IMM, OMM, and yeast IMM.
