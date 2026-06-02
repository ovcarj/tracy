from __future__ import annotations

from aiida import orm
from aiida.engine import WorkChain

from tracy.calculations.electrostatic_energy import compute_electrostatic_energy


class ElectrostaticEnergyWorkChain(WorkChain):
    """Compute the 1D electrostatic energy profile E(z) for a molecule in a membrane potential.

    Inputs are the .xvg potential profile from ComputeMembranePotentialWorkChain and the
    output_parameters Dict from OrcaOptWorkChain (containing RESP charges and geometry).
    No external codes are submitted — computation runs via a calcfunction.
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)
        spec.input('potential_profile', valid_type=orm.SinglefileData,
                   help='XVG file from gmx potential (ComputeMembranePotentialWorkChain output).')
        spec.input('output_parameters', valid_type=orm.Dict,
                   help='OrcaOptWorkChain output_parameters (atomcharges, atomcoords, atomnos).')
        spec.input('protocol', valid_type=orm.Dict,
                   help='Protocol dict with tracy.membrane_normal_axis, tracy.charges_model, '
                        'tracy.z_scan_nm.')
        spec.output('electrostatic_energy_report', valid_type=orm.Dict,
                    help='E(z) profile and min/max for both dipole orientations.')
        spec.outline(
            cls.setup,
            cls.run_compute,
            cls.results,
        )

    def setup(self):
        self.ctx.tracy_conf = self.inputs.protocol.get_dict().get('tracy', {})

    def run_compute(self):
        self.ctx.report = compute_electrostatic_energy(
            self.inputs.potential_profile,
            self.inputs.output_parameters,
            self.inputs.protocol,
        )

    def results(self):
        self.out('electrostatic_energy_report', self.ctx.report)
