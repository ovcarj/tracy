# Electrostatics protocol directory

Protocol files for `ComputeMembranePotentialWorkChain`.

## What the protocol controls

`potential_slices` sets the number of z-bins for `gmx potential`. 200 slices
gives ~0.04–0.06 nm resolution for a typical 8–12 nm POPC box.

`potential_component_groups` lists groups whose individual φ(z) profiles are
computed in parallel alongside the total. By Poisson linearity:
φ(SYSTEM) = φ(MEMB) + φ(Water) + φ(ION)

`new_index_groups` creates named groups via `gmx select` before the analysis.
Required when the trajectory lacks Water and ION groups (CHARMM-GUI only
provides MEMB, SOLV, SYSTEM by default).

`potential_symmetrize: true` averages φ(z) with φ(L−z) in post-processing.
Use only for symmetric bilayers; set `false` for asymmetric compositions.

`potential_convergence_check: true` computes the potential on the first 50%
and 75% of the trajectory and compares to the full run. Results appear under
`potential_report["convergence"]`.

## Provided files

`charmm36.yaml` — standard settings for CHARMM36/36m systems with KCl.
Covers TIP3P water (resname `TIP3`), K⁺ (`POT`), Cl⁻ (`CLA`).
For NaCl, replace `CLA` → `CLA` (unchanged) and `POT` → `SOD`.
