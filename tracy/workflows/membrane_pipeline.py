"""MembraneSimulationPipelineWorkChain: full membrane simulation pipeline (placeholder).

TODO (Milestone 2): Implement RunMembraneMDWorkChain that consumes
      gromacs_input_bundle from BuildMembraneWorkChain and runs GROMACS
      minimisation, equilibration, and production stages via aiida-gromacs.

TODO (Milestone 3): Implement ComputeMembranePotentialWorkChain that computes
      the electrostatic potential profile along the membrane normal axis from
      MD trajectories.

TODO (Milestone 4+): Add MoleculeChargeDistributionWorkChain and
      BindingEnergyWorkChain once the membrane and potential stages are stable.
"""

from __future__ import annotations
