# Electrostatic energy protocol directory

Protocol files for `ElectrostaticEnergyWorkChain`.

## Method

E(z) [eV] = Σᵢ qᵢ [e] · φ(zᵢ + z_COM) [V]

The molecule is oriented so its dipole moment is parallel to the membrane
normal. Both orientations (±dipole) are computed and reported. The COM scan
range is automatically shrunk so the spline is never extrapolated.

This is a fixed-charge 1D electrostatic interaction score, not a PMF or
permeation free energy. It ignores desolvation, polarization, membrane
deformation, and lateral diffusion. See doi:10.1039/d4ob00252k for context.

## Inputs required

- `potential_profile` — `.xvg` file from `ComputeMembranePotentialWorkChain`
- `output_parameters` — `orm.Dict` from `MoleculeChargeDistributionWorkChain`
  (contains `atomcharges['resp']` and atom coordinates)

## What the protocol controls

`charges_model` — which charge set to read from `output_parameters`.
Use `resp` for RESP-fitted charges (recommended). `mulliken` and `loewdin`
are also available from the ORCA output but are less suitable for
electrostatic calculations.

`z_scan_nm.n_points` — resolution of the COM scan along z. 200 is sufficient
for a smooth E(z) curve.

`z_scan_nm.min` / `z_scan_nm.max` — optional clip to restrict the scan to a
sub-range (nm). The auto-shrink already removes unphysical edge zones; these
are additional user-defined limits.

## Storing results

```bash
retrace import aiida --pk <ElectrostaticEnergyWorkChain_pk>
```

## Provided files

`default.yaml` — standard settings: RESP charges, 200-point scan, no range clip.
