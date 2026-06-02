"""OrcaPreoptWorkChain: parallel XTB pre-optimisation of conformers via ORCA."""

from __future__ import annotations

import os
import tempfile

from aiida import orm
from aiida.engine import ExitCode, ToContext, WorkChain
from aiida.plugins import WorkflowFactory

OrcaBaseWorkChain = WorkflowFactory('orca.base')


class OrcaPreoptWorkChain(WorkChain):
    """Pre-optimise conformers in parallel using XTB via ORCA.

    Accepts a FolderData of XYZ conformer files (e.g. from ``generate_conformers``),
    submits one ``OrcaBaseWorkChain`` per conformer, ranks by final energy, and
    returns the top-K relaxed structures.

    This is the ORCA-specific implementation of the pre-optimisation step.
    ``MoleculeChargeDistributionWorkChain`` dispatches to it based on
    ``protocol.tracy.expected_engine``.
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)

        spec.input('conformers',  valid_type=orm.FolderData)
        spec.input('orca_code',   valid_type=orm.AbstractCode)
        spec.input('parameters',  valid_type=orm.Dict)
        spec.input('options',     valid_type=orm.Dict, required=False)

        spec.outline(
            cls.setup,
            cls.run_preopt,
            cls.inspect_results,
            cls.results,
        )

        spec.output_namespace('relaxed_structures', dynamic=True)
        spec.output('energies',      valid_type=orm.List)
        spec.output('preopt_report', valid_type=orm.Dict)

        spec.exit_code(410, 'ERROR_NO_CONFORMERS',
                       message='FolderData contains no XYZ conformer files.')
        spec.exit_code(411, 'ERROR_INSUFFICIENT_CONVERGED',
                       message='Fewer than top_k XTB jobs converged successfully.')

    def setup(self) -> ExitCode | None:
        xyz_files = sorted(
            name for name in self.inputs.conformers.list_object_names()
            if name.endswith('.xyz')
        )
        if not xyz_files:
            return self.exit_codes.ERROR_NO_CONFORMERS

        p = self.inputs.parameters.get_dict()
        self.ctx.top_k = p.get('top_k', 5)
        solvent = p.get('solvent')  # None = vacuum
        keywords = [p.get('method', 'XTB2'), 'OPT']
        if solvent:
            keywords.append(f'ALPB({solvent})')
        orca_dict: dict = {
            'charge': p.get('charge', 0),
            'multiplicity': p.get('multiplicity', 1),
            'input_keywords': keywords,
        }
        if 'input_blocks' in p:
            orca_dict['input_blocks'] = p['input_blocks']
        self.ctx.orca_params = orm.Dict(orca_dict)
        self.ctx.orca_params.store()
        self.ctx.solvent = solvent

        self.ctx.structures = {}
        with tempfile.TemporaryDirectory() as tmpdir:
            self.inputs.conformers.base.repository.copy_tree(tmpdir)
            for name in xyz_files:
                key = name[:-4]
                structure = _xyz_to_structure(os.path.join(tmpdir, name))
                structure.store()
                self.ctx.structures[key] = structure

        solvent_label = solvent or 'vacuum'
        self.report(f"Setup: {len(self.ctx.structures)} conformers, top_k={self.ctx.top_k}, solvent={solvent_label}")

    def run_preopt(self):
        options = self.inputs.options.get_dict() if 'options' in self.inputs else {}

        calcs = {}
        for key, structure in self.ctx.structures.items():
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
        for key in sorted(self.ctx.structures.keys()):
            wc = self.ctx[key]
            if not wc.is_finished_ok:
                self.report(f"{key}: XTB failed (exit {wc.exit_status}), skipping.")
                continue
            params = wc.outputs.output_parameters.get_dict()
            energies = params.get('scfenergies', [])
            if not energies or not params.get('optdone', False):
                self.report(f"{key}: optimization did not converge, skipping.")
                continue
            if not hasattr(wc.outputs, 'relaxed_structure'):
                self.report(f"{key}: no relaxed_structure output, skipping.")
                continue
            results.append({
                'key': key,
                'energy': float(energies[-1]),
                'structure': wc.outputs.relaxed_structure,
            })

        if len(results) < self.ctx.top_k:
            self.report(f"Only {len(results)} converged, need {self.ctx.top_k}.")
            return self.exit_codes.ERROR_INSUFFICIENT_CONVERGED

        results.sort(key=lambda r: r['energy'])
        self.ctx.top_results = results[:self.ctx.top_k]
        self.report(
            f"{len(results)} converged; top {self.ctx.top_k} energies: "
            f"{[r['energy'] for r in self.ctx.top_results]}"
        )

    def results(self):
        for i, r in enumerate(self.ctx.top_results):
            self.out(f'relaxed_structures.conformer_{i}', r['structure'])

        self.out('energies', orm.List(list=[r['energy'] for r in self.ctx.top_results]).store())
        self.out('preopt_report', orm.Dict({
            'n_submitted': len(self.ctx.structures),
            'n_converged': len([
                k for k in self.ctx.structures
                if self.ctx[k].is_finished_ok
            ]),
            'top_k': self.ctx.top_k,
            'top_k_keys': [r['key'] for r in self.ctx.top_results],
            'solvent': self.ctx.solvent,
        }).store())


def _xyz_to_structure(path: str) -> orm.StructureData:
    """Read an XYZ file and return an AiiDA StructureData."""
    from ase.io import read as ase_read
    atoms = ase_read(path, format='xyz')
    return orm.StructureData(ase=atoms)
