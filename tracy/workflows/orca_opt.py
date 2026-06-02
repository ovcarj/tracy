"""OrcaOptWorkChain: parallel DFT geometry optimisation + RESP charges via ORCA."""

from __future__ import annotations

from aiida import orm
from aiida.engine import ExitCode, ToContext, WorkChain
from aiida.plugins import WorkflowFactory

OrcaBaseWorkChain = WorkflowFactory('orca.base')


class OrcaOptWorkChain(WorkChain):
    """Optimise structures with DFT and compute RESP charges via ORCA.

    Accepts a dynamic namespace of StructureData nodes (e.g. from
    ``OrcaPreoptWorkChain.relaxed_structures``), submits one
    ``OrcaBaseWorkChain`` per structure with both ``OPT`` and a RESP keyword
    (default: ``CHELPG``), then returns the lowest-energy result.

    This is the ORCA-specific implementation of the geometry-optimisation +
    charge-calculation step.  ``MoleculeChargeDistributionWorkChain`` dispatches
    to it based on ``protocol.tracy.expected_engine``.
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)

        spec.input_namespace('structures', dynamic=True)
        spec.input('orca_code',  valid_type=orm.AbstractCode)
        spec.input('parameters', valid_type=orm.Dict)
        spec.input('options',    valid_type=orm.Dict, required=False)

        spec.outline(
            cls.setup,
            cls.run_opt,
            cls.inspect_results,
            cls.results,
        )

        spec.output('relaxed_structure',  valid_type=orm.StructureData)
        spec.output('output_parameters',  valid_type=orm.Dict)
        spec.output_namespace('all_results', dynamic=True)
        spec.output('opt_report', valid_type=orm.Dict)

        spec.exit_code(420, 'ERROR_NO_STRUCTURES',
                       message='No input structures provided.')
        spec.exit_code(421, 'ERROR_NO_CONVERGED_STRUCTURES',
                       message='No DFT geometry optimisation converged with RESP charges.')

    def setup(self) -> ExitCode | None:
        if not self.inputs.structures:
            return self.exit_codes.ERROR_NO_STRUCTURES

        p = self.inputs.parameters.get_dict()
        method       = p.get('method', 'B3LYP')
        basis        = p.get('basis', 'def2-SVP')
        dispersion   = p.get('dispersion', 'D3BJ')
        resp_keyword = p.get('resp_keyword', 'CHELPG')

        self.ctx.orca_params = orm.Dict({
            'charge': p.get('charge', 0),
            'multiplicity': p.get('multiplicity', 1),
            'input_keywords': [method, basis, dispersion, 'OPT', resp_keyword],
        })
        self.ctx.orca_params.store()
        self.report(
            f"Setup: {len(self.inputs.structures)} structures, "
            f"method={method}/{basis}, RESP keyword={resp_keyword}"
        )

    def run_opt(self):
        options = self.inputs.options.get_dict() if 'options' in self.inputs else {}

        calcs = {}
        for key, structure in self.inputs.structures.items():
            orca_inputs = {
                'structure': structure,
                'parameters': self.ctx.orca_params,
                'code': self.inputs.orca_code,
            }
            if options:
                orca_inputs['metadata'] = {'options': options}
            wc = self.submit(OrcaBaseWorkChain, orca=orca_inputs)
            self.report(f"Submitted OrcaBaseWorkChain for {key} (pk={wc.pk})")
            calcs[key] = wc

        return ToContext(**calcs)

    def inspect_results(self) -> ExitCode | None:
        results = []
        for key in sorted(self.inputs.structures.keys()):
            wc = self.ctx[key]
            if not wc.is_finished_ok:
                self.report(f"{key}: DFT opt failed (exit {wc.exit_status}), skipping.")
                continue
            params = wc.outputs.output_parameters.get_dict()
            if not params.get('optdone', False):
                self.report(f"{key}: geometry did not converge, skipping.")
                continue
            atomcharges = params.get('atomcharges', {})
            if 'resp' not in atomcharges:
                self.report(f"{key}: RESP charges absent from output, skipping.")
                continue
            if not hasattr(wc.outputs, 'relaxed_structure'):
                self.report(f"{key}: no relaxed_structure output, skipping.")
                continue
            energies = params.get('scfenergies', [])
            results.append({
                'key': key,
                'energy': float(energies[-1]),
                'output_parameters': wc.outputs.output_parameters,
                'relaxed_structure': wc.outputs.relaxed_structure,
            })

        if not results:
            return self.exit_codes.ERROR_NO_CONVERGED_STRUCTURES

        results.sort(key=lambda r: r['energy'])
        self.ctx.best = results[0]
        self.ctx.all_opt_results = results
        self.report(
            f"{len(results)}/{len(self.inputs.structures)} converged; "
            f"best energy: {results[0]['energy']} (key={results[0]['key']})"
        )

    def results(self):
        self.out('relaxed_structure', self.ctx.best['relaxed_structure'])
        self.out('output_parameters', self.ctx.best['output_parameters'])

        for r in self.ctx.all_opt_results:
            self.out(f"all_results.{r['key']}", r['output_parameters'])

        self.out('opt_report', orm.Dict({
            'n_submitted': len(self.inputs.structures),
            'n_converged': len(self.ctx.all_opt_results),
            'best_key': self.ctx.best['key'],
            'best_energy': self.ctx.best['energy'],
        }).store())
