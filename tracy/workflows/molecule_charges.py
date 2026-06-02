"""MoleculeChargeDistributionWorkChain: engine-agnostic molecular charge pipeline."""

from __future__ import annotations

import os
import tempfile

from aiida import orm
from aiida.engine import ExitCode, ToContext, WorkChain, if_


def _solvent_key(solvent: str | None) -> str:
    """Normalise a solvent name to a safe dict/output key."""
    return solvent.lower() if solvent else 'vacuum'


class MoleculeChargeDistributionWorkChain(WorkChain):
    """Compute per-atom charge distributions for a molecule.

    Pipeline: conformer generation → (optional) pre-optimisation → geometry
    optimisation + charge calculation.  When ``tracy.solvents`` lists multiple
    solvents, pre-opt and DFT-opt are submitted in parallel for each solvent;
    results are exposed under ``results.<solvent_key>.*``.

    The engine for each step is selected via ``protocol.tracy``:

    - ``conformer_engine``: which conformer generator to use (default: ``rdkit``)
    - ``expected_engine``: which QC code to use (default: ``orca``)
    - ``solvents``: list of solvents to compute (default: ``[null]`` = vacuum only)
      null → vacuum (no solvation keyword), string → ALPB/CPCM implicit solvent

    Adding a new engine means implementing new WorkChains and adding one branch to
    ``setup`` — this WorkChain does not change.

    Outputs
    -------
    results.<solvent_key>.relaxed_structure  : StructureData
    results.<solvent_key>.output_parameters  : Dict  (includes atomcharges)
    results.<solvent_key>.charge_report      : Dict
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

        spec.output_namespace('results', dynamic=True)
        # Populated as results.<solvent_key>.relaxed_structure / output_parameters / charge_report

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
        spec.exit_code(405, 'ERROR_PREOPT_FAILED_ALL_SOLVENTS',
                       message='Pre-optimisation failed for all solvents.')
        spec.exit_code(406, 'ERROR_OPT_FAILED_ALL_SOLVENTS',
                       message='Geometry optimisation failed for all solvents.')

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

        # solvents: list[str | None] — None means vacuum
        raw_solvents = tracy_conf.get('solvents', [None])
        self.ctx.solvents = raw_solvents
        self.ctx.solvent_keys = [_solvent_key(s) for s in raw_solvents]

        # opt_structures: {solvent_key: {conformer_key: StructureData}}
        self.ctx.opt_structures = {}

        self.report(
            f"Setup: conformer_engine={conformer_engine}, engine={engine}, "
            f"run_preopt={self.ctx.run_preopt}, solvents={self.ctx.solvent_keys}"
        )

    def should_generate_conformers(self) -> bool:
        return 'smiles' in self.inputs and 'conformers' not in self.inputs

    def should_run_preopt(self) -> bool:
        return bool(self.ctx.run_preopt)

    def run_conformer_gen(self):
        p = self.ctx.protocol.get('tracy', {})
        mol_charge = p.get('charge', 0)
        try:
            from rdkit import Chem
            mol = Chem.MolFromSmiles(self.inputs.smiles.value)
            if mol is not None:
                rdkit_charge = Chem.GetFormalCharge(mol)
                if rdkit_charge != mol_charge:
                    self.report(
                        f"WARNING: SMILES formal charge ({rdkit_charge}) does not match "
                        f"protocol.tracy.charge ({mol_charge}). "
                        f"ORCA will use charge={mol_charge}. Verify this is intentional."
                    )
        except ImportError:
            pass
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

        preopt_base: dict = {
            'charge': p.get('charge', 0),
            'multiplicity': p.get('multiplicity', 1),
            'method': orca_conf.get('method', 'XTB2'),
            'top_k': p.get('preopt_top_k', 5),
        }
        if 'input_blocks' in orca_conf:
            preopt_base['input_blocks'] = orca_conf['input_blocks']

        calcs = {}
        for raw_s, key in zip(self.ctx.solvents, self.ctx.solvent_keys):
            params = orm.Dict({**preopt_base, 'solvent': raw_s})
            inputs = {
                'conformers': conformers,
                'orca_code': self.inputs.code,
                'parameters': params,
            }
            if 'options' in self.inputs:
                inputs['options'] = self.inputs.options
            wc = self.submit(self.ctx.preopt_wc_cls, **inputs)
            self.report(f"Submitted {self.ctx.preopt_wc_cls.__name__} solvent={key} (pk={wc.pk})")
            calcs[f'preopt_wc_{key}'] = wc

        return ToContext(**calcs)

    def inspect_preopt(self) -> ExitCode | None:
        any_ok = False
        for key in self.ctx.solvent_keys:
            wc = self.ctx[f'preopt_wc_{key}']
            if not wc.is_finished_ok:
                self.report(f"Pre-opt solvent={key} failed (exit {wc.exit_status}), skipping.")
                continue
            self.ctx.opt_structures[key] = dict(wc.outputs.relaxed_structures)
            self.report(f"Pre-opt solvent={key} OK: {len(self.ctx.opt_structures[key])} structures.")
            any_ok = True

        if not any_ok:
            return self.exit_codes.ERROR_PREOPT_FAILED_ALL_SOLVENTS

    def prepare_opt_inputs(self):
        """Populate ctx.opt_structures for solvents where preopt was skipped or not run."""
        conformers = (
            self.ctx.conformers if 'conformers' in self.ctx
            else self.inputs.conformers
        )
        for key in self.ctx.solvent_keys:
            if key not in self.ctx.opt_structures:
                self.ctx.opt_structures[key] = _xyz_folder_to_structures(conformers)
                self.report(
                    f"Prepared {len(self.ctx.opt_structures[key])} structures "
                    f"from conformers for solvent={key}."
                )

    def run_opt(self):
        p = self.ctx.protocol.get('tracy', {})
        orca_conf = self.ctx.protocol.get('orca', {}).get('opt', {})

        opt_base: dict = {
            'charge': p.get('charge', 0),
            'multiplicity': p.get('multiplicity', 1),
            'method': orca_conf.get('method', 'B3LYP'),
            'basis': orca_conf.get('basis', 'def2-SVP'),
            'dispersion': orca_conf.get('dispersion', 'D3BJ'),
            'resp_keyword': orca_conf.get('resp_keyword', 'RESP'),
        }
        if 'charges_key' in orca_conf:
            opt_base['charges_key'] = orca_conf['charges_key']
        if 'input_blocks' in orca_conf:
            opt_base['input_blocks'] = orca_conf['input_blocks']

        calcs = {}
        for raw_s, key in zip(self.ctx.solvents, self.ctx.solvent_keys):
            if key not in self.ctx.opt_structures:
                self.report(f"No opt structures for solvent={key}, skipping.")
                continue
            params = orm.Dict({**opt_base, 'solvent': raw_s})
            inputs = {
                'structures': self.ctx.opt_structures[key],
                'orca_code': self.inputs.code,
                'parameters': params,
            }
            if 'options' in self.inputs:
                inputs['options'] = self.inputs.options
            wc = self.submit(self.ctx.opt_wc_cls, **inputs)
            self.report(f"Submitted {self.ctx.opt_wc_cls.__name__} solvent={key} (pk={wc.pk})")
            calcs[f'opt_wc_{key}'] = wc

        return ToContext(**calcs)

    def inspect_opt(self) -> ExitCode | None:
        any_ok = False
        for key in self.ctx.solvent_keys:
            ctx_key = f'opt_wc_{key}'
            if ctx_key not in self.ctx:
                continue
            wc = self.ctx[ctx_key]
            if not wc.is_finished_ok:
                self.report(f"Opt solvent={key} failed (exit {wc.exit_status}).")
                continue
            any_ok = True
            self.report(f"Opt solvent={key} OK.")

        if not any_ok:
            return self.exit_codes.ERROR_OPT_FAILED_ALL_SOLVENTS

    def results(self):
        for key in self.ctx.solvent_keys:
            ctx_key = f'opt_wc_{key}'
            if ctx_key not in self.ctx:
                continue
            wc = self.ctx[ctx_key]
            if not wc.is_finished_ok:
                continue

            self.out(f'results.{key}.relaxed_structure', wc.outputs.relaxed_structure)
            self.out(f'results.{key}.output_parameters', wc.outputs.output_parameters)

            opt_report = wc.outputs.opt_report.get_dict()
            preopt_wc = self.ctx.get(f'preopt_wc_{key}')
            preopt_pk = preopt_wc.pk if preopt_wc is not None else None
            self.out(f'results.{key}.charge_report', orm.Dict({
                'solvent': key,
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
