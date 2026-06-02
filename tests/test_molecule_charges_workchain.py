"""Process-spec tests for MoleculeChargeDistributionWorkChain."""

from __future__ import annotations

import pytest
from aiida import orm
from aiida.engine import WorkChain

from tracy.workflows.molecule_charges import MoleculeChargeDistributionWorkChain


def test_is_workchain_subclass():
    assert issubclass(MoleculeChargeDistributionWorkChain, WorkChain)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def test_smiles_is_optional():
    port = MoleculeChargeDistributionWorkChain.spec().inputs['smiles']
    assert port.required is False


def test_conformers_is_optional():
    port = MoleculeChargeDistributionWorkChain.spec().inputs['conformers']
    assert port.required is False


def test_protocol_is_required():
    port = MoleculeChargeDistributionWorkChain.spec().inputs['protocol']
    assert port.required is True
    assert issubclass(port.valid_type, orm.Dict)


def test_code_is_required():
    port = MoleculeChargeDistributionWorkChain.spec().inputs['code']
    assert port.required is True


def test_options_is_optional():
    port = MoleculeChargeDistributionWorkChain.spec().inputs['options']
    assert port.required is False


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


def test_has_relaxed_structure_output():
    port = MoleculeChargeDistributionWorkChain.spec().outputs['relaxed_structure']
    assert issubclass(port.valid_type, orm.StructureData)


def test_has_output_parameters():
    port = MoleculeChargeDistributionWorkChain.spec().outputs['output_parameters']
    assert issubclass(port.valid_type, orm.Dict)


def test_has_charge_report_output():
    port = MoleculeChargeDistributionWorkChain.spec().outputs['charge_report']
    assert issubclass(port.valid_type, orm.Dict)


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


def test_exit_code_unsupported_conformer_engine():
    codes = MoleculeChargeDistributionWorkChain.spec().exit_codes
    assert hasattr(codes, 'ERROR_UNSUPPORTED_CONFORMER_ENGINE')
    assert codes.ERROR_UNSUPPORTED_CONFORMER_ENGINE.status == 400


def test_exit_code_unsupported_engine():
    codes = MoleculeChargeDistributionWorkChain.spec().exit_codes
    assert hasattr(codes, 'ERROR_UNSUPPORTED_ENGINE')
    assert codes.ERROR_UNSUPPORTED_ENGINE.status == 401


def test_exit_code_missing_input():
    codes = MoleculeChargeDistributionWorkChain.spec().exit_codes
    assert hasattr(codes, 'ERROR_MISSING_INPUT')
    assert codes.ERROR_MISSING_INPUT.status == 402


def test_exit_code_preopt_failed():
    codes = MoleculeChargeDistributionWorkChain.spec().exit_codes
    assert hasattr(codes, 'ERROR_PREOPT_FAILED')
    assert codes.ERROR_PREOPT_FAILED.status == 403


def test_exit_code_opt_failed():
    codes = MoleculeChargeDistributionWorkChain.spec().exit_codes
    assert hasattr(codes, 'ERROR_OPT_FAILED')
    assert codes.ERROR_OPT_FAILED.status == 404
