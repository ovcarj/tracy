# Membrane MD protocol directory

Protocol files for `RunMembraneMDWorkChain`.

## What the protocol controls

`md_steps` selects which MDP files to run and in what order. Each
`"equilibration"` entry picks successive `step6.N_equilibration.mdp` files
from the CHARMM-GUI bundle.

`mdp_overrides` patches key-value pairs into the MDP before submission.
Hyphens and underscores are interchangeable in key names.

The `production` step **must** include `nstxout-compressed > 0` so that
`ComputeMembranePotentialWorkChain` has a trajectory to analyse.

## Provided files

`charmm_gui_charmm36.yaml` — standard 8-step protocol for bundles built with
the CHARMM-GUI Quick Bilayer tool using CHARMM36/36m force field. Works with
both 2 fs (default) and 4 fs (HMR) timesteps; set `nsteps` and
`nstxout-compressed` in `mdp_overrides.production` to match your system.
