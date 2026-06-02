"""MoleculeChargeDistributionWorkChain: engine-agnostic molecular charge pipeline."""

from __future__ import annotations

import os
import tempfile

from aiida import orm
from aiida.engine import ExitCode, ToContext, WorkChain, if_


class MoleculeChargeDistributionWorkChain(WorkChain):
    """Compute per-atom charge distributions for a molecule.

    Pipeline: conformer generation → (optional) pre-optimisation → geometry
    optimisation + charge calculation.

    The engine for each step is selected via ``protocol.tracy``:

    - ``conformer_engine``: which conformer generator to use (default: ``rdkit``)
    - ``expected_engine``: which QC code to use for pre-opt and opt (default: ``orca``)

    The current implementations are:
    - conformers: RDKit ETKDG (``tracy.calculations.conformers.generate_conformers``)
    - pre-opt + opt: ORCA (``OrcaPreoptWorkChain``, ``OrcaOptWorkChain``)

    Adding a new engine means implementing new WorkChains and adding one branch to
    ``setup`` — this WorkChain does not change.

    Inputs
    ------
    smiles      : Str         — SMILES to generate conformers from (omit if ``conformers`` provided)
    conformers  : FolderData  — pre-generated conformers (omit if ``smiles`` provided)
    protocol    : Dict        — full protocol dict
    code        : AbstractCode — QC code (e.g. orca@remote)
    options     : Dict        — scheduler resources (optional)

    Outputs
    -------
    relaxed_structure  : StructureData — lowest-energy DFT-relaxed geometry
    output_parameters  : Dict          — ORCA output (includes atomcharges['resp'])
    charge_report      : Dict          — provenance metadata
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)

        spec.input('smiles',     valid_type=orm.Str,         required=False)
        spec.input('conformers', valid_type=orm.FolderData,  required=False)
        spec.input('protocol',   valid_type=orm.Dict)
        spec.input('code',       valid_type=orm.AbstractCode)
        spec.input('options',    valid_type=orm.Dict,        required=False)

        spec.outline(
            cls.setup,
            if_(cls.should_generate_conformers)(cls.run_conformer_gen),
            if_(cls.should_run_preopt)(
                cls.run_preopt,
                cls.inspect_preopt,
            ),
            cls.prepare_opt_inputs,
            cls.run_opt,
            cls.inspect_opt,
            cls.results,
        )

        spec.output('relaxed_structure',  valid_type=orm.StructureData)
        spec.output('output_parameters',  valid_type=orm.Dict)
        spec.output('charge_report',      valid_type=orm.Dict)

        spec.exit_code(400, 'ERROR_UNSUPPORTED_CONFORMER_ENGINE',
                       message='Unsupported conformer generation engine.')
        spec.exit_code(401, 'ERROR_UNSUPPORTED_ENGINE',
                       message='Unsupported QC engine for pre-opt / opt.')
        spec.exit_code(402, 'ERROR_MISSING_INPUT',
                       message='Neither smiles nor conformers input was provided.')
        spec.exit_code(403, 'ERROR_PREOPT_FAILED',
                       message='Pre-optimisation WorkChain failed.')
        spec.exit_code(404, 'ERROR_OPT_FAILED',
                       message='Geometry optimisation WorkChain failed.')

    # -------------------------------------------------------------------------

    def setup(self) -> ExitCode | None:
        if 'smiles' not in self.inputs and 'conformers' not in self.inputs:
            return self.exit_codes.ERROR_MISSING_INPUT

        protocol = self.inputs.protocol.get_dict()
        self.ctx.protocol = protocol
        tracy_conf = protocol.get('tracy', {})

        conformer_engine = tracy_conf.get('conformer_engine', 'rdkit')
        if conformer_engine == 'rdkit':
            from tracy.calculations.conformers import generate_conformers
            self.ctx.conformer_fn = generate_conformers
        else:
            self.report(f"Unsupported conformer engine: {conformer_engine!r}")
            return self.exit_codes.ERROR_UNSUPPORTED_CONFORMER_ENGINE

        engine = tracy_conf.get('expected_engine', 'orca')
        if engine == 'orca':
            from tracy.workflows.orca_preopt import OrcaPreoptWorkChain
            from tracy.workflows.orca_opt import OrcaOptWorkChain
            self.ctx.preopt_wc_cls = OrcaPreoptWorkChain
            self.ctx.opt_wc_cls = OrcaOptWorkChain
        else:
            self.report(f"Unsupported QC engine: {engine!r}")
            return self.exit_codes.ERROR_UNSUPPORTED_ENGINE

        self.ctx.run_preopt = tracy_conf.get('run_preopt', True)
        self.ctx.opt_structures = {}

        self.report(
            f"Setup: conformer_engine={conformer_engine}, engine={engine}, "
            f"run_preopt={self.ctx.run_preopt}"
        )

    def should_generate_conformers(self) -> bool:
        return 'smiles' in self.inputs and 'conformers' not in self.inputs

    def should_run_preopt(self) -> bool:
        return bool(self.ctx.run_preopt)

    def run_conformer_gen(self):
        p = self.ctx.protocol.get('tracy', {})
        conformers = self.ctx.conformer_fn(
            smiles=self.inputs.smiles,
            n_conformers=orm.Int(p.get('n_conformers', 20)),
            random_seed=orm.Int(p.get('random_seed', 42)),
        )
        self.ctx.conformers = conformers
        self.report(f"Conformer generation complete: {len(conformers.list_object_names())} files")

    def run_preopt(self):
        conformers = (
            self.ctx.conformers if 'conformers' in self.ctx
            else self.inputs.conformers
        )
        p = self.ctx.protocol.get('tracy', {})
        orca_conf = self.ctx.protocol.get('orca', {}).get('preopt', {})

        preopt_dict: dict = {
            'charge': p.get('charge', 0),
            'multiplicity': p.get('multiplicity', 1),
            'method': orca_conf.get('method', 'XTB2'),
            'top_k': p.get('preopt_top_k', 5),
        }
        if 'input_blocks' in orca_conf:
            preopt_dict['input_blocks'] = orca_conf['input_blocks']
        preopt_params = orm.Dict(preopt_dict)

        inputs = {
            'conformers': conformers,
            'orca_code': self.inputs.code,
            'parameters': preopt_params,
        }
        if 'options' in self.inputs:
            inputs['options'] = self.inputs.options

        wc = self.submit(self.ctx.preopt_wc_cls, **inputs)
        self.report(f"Submitted {self.ctx.preopt_wc_cls.__name__} (pk={wc.pk})")
        return ToContext(preopt_wc=wc)

    def inspect_preopt(self) -> ExitCode | None:
        wc = self.ctx.preopt_wc
        if not wc.is_finished_ok:
            self.report(f"Pre-opt failed (exit {wc.exit_status}).")
            return self.exit_codes.ERROR_PREOPT_FAILED
        self.ctx.opt_structures = dict(wc.outputs.relaxed_structures)
        self.report(f"Pre-opt OK: {len(self.ctx.opt_structures)} structures for DFT opt.")

    def prepare_opt_inputs(self):
        """Populate ctx.opt_structures when preopt was skipped."""
        if self.ctx.opt_structures:
            return
        conformers = (
            self.ctx.conformers if 'conformers' in self.ctx
            else self.inputs.conformers
        )
        self.ctx.opt_structures = _xyz_folder_to_structures(conformers)
        self.report(
            f"Prepared {len(self.ctx.opt_structures)} structures directly from conformers."
        )

    def run_opt(self):
        p = self.ctx.protocol.get('tracy', {})
        orca_conf = self.ctx.protocol.get('orca', {}).get('opt', {})

        opt_dict: dict = {
            'charge': p.get('charge', 0),
            'multiplicity': p.get('multiplicity', 1),
            'method': orca_conf.get('method', 'B3LYP'),
            'basis': orca_conf.get('basis', 'def2-SVP'),
            'dispersion': orca_conf.get('dispersion', 'D3BJ'),
            'resp_keyword': orca_conf.get('resp_keyword', 'CHELPG'),
        }
        if 'input_blocks' in orca_conf:
            opt_dict['input_blocks'] = orca_conf['input_blocks']
        opt_params = orm.Dict(opt_dict)

        inputs = {
            'structures': self.ctx.opt_structures,
            'orca_code': self.inputs.code,
            'parameters': opt_params,
        }
        if 'options' in self.inputs:
            inputs['options'] = self.inputs.options

        wc = self.submit(self.ctx.opt_wc_cls, **inputs)
        self.report(f"Submitted {self.ctx.opt_wc_cls.__name__} (pk={wc.pk})")
        return ToContext(opt_wc=wc)

    def inspect_opt(self) -> ExitCode | None:
        wc = self.ctx.opt_wc
        if not wc.is_finished_ok:
            self.report(f"Opt failed (exit {wc.exit_status}).")
            return self.exit_codes.ERROR_OPT_FAILED
        self.report("Opt+RESP OK.")

    def results(self):
        wc = self.ctx.opt_wc
        self.out('relaxed_structure', wc.outputs.relaxed_structure)
        self.out('output_parameters', wc.outputs.output_parameters)

        opt_report = wc.outputs.opt_report.get_dict()
        preopt_pk = getattr(self.ctx.get('preopt_wc', None), 'pk', None)
        self.out('charge_report', orm.Dict({
            'preopt_pk': preopt_pk,
            'opt_pk': wc.pk,
            'best_key': opt_report.get('best_key'),
            'best_energy': opt_report.get('best_energy'),
        }).store())


def _xyz_folder_to_structures(folder: orm.FolderData) -> dict[str, orm.StructureData]:
    """Convert all XYZ files in a FolderData to stored StructureData nodes."""
    from ase.io import read as ase_read

    xyz_files = sorted(
        name for name in folder.list_object_names()
        if name.endswith('.xyz')
    )
    structures = {}
    with tempfile.TemporaryDirectory() as tmpdir:
        folder.base.repository.copy_tree(tmpdir)
        for name in xyz_files:
            key = name[:-4]
            atoms = ase_read(os.path.join(tmpdir, name), format='xyz')
            structure = orm.StructureData(ase=atoms)
            structure.store()
            structures[key] = structure
    return structures
