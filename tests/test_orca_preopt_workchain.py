"""Process-spec tests for OrcaPreoptWorkChain."""

from __future__ import annotations

import pytest
from aiida import orm
from aiida.engine import WorkChain

pytest.importorskip("aiida_orca", reason="aiida-orca not installed")
from tracy.workflows.orca_preopt import OrcaPreoptWorkChain


# ---------------------------------------------------------------------------
# Solvent keyword logic (pure-Python, no AiiDA profile needed)
# ---------------------------------------------------------------------------


def _build_preopt_keywords(method: str, solvent: str | None) -> list[str]:
    """Mirror the keyword-building logic from OrcaPreoptWorkChain.setup()."""
    keywords = [method, 'OPT']
    if solvent:
        keywords.append(f'ALPB({solvent})')
    return keywords


def test_vacuum_preopt_keywords():
    kw = _build_preopt_keywords('XTB2', None)
    assert kw == ['XTB2', 'OPT']
    assert not any('ALPB' in k for k in kw)


def test_water_preopt_adds_alpb():
    kw = _build_preopt_keywords('XTB2', 'Water')
    assert 'ALPB(Water)' in kw


def test_arbitrary_solvent_preopt():
    kw = _build_preopt_keywords('XTB2', 'Methanol')
    assert 'ALPB(Methanol)' in kw


def test_is_workchain_subclass():
    assert issubclass(OrcaPreoptWorkChain, WorkChain)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def test_has_conformers_input():
    port = OrcaPreoptWorkChain.spec().inputs['conformers']
    assert port.required is True
    assert issubclass(port.valid_type, orm.FolderData)


def test_has_orca_code_input():
    port = OrcaPreoptWorkChain.spec().inputs['orca_code']
    assert port.required is True


def test_has_parameters_input():
    port = OrcaPreoptWorkChain.spec().inputs['parameters']
    assert port.required is True
    assert issubclass(port.valid_type, orm.Dict)


def test_options_is_optional():
    port = OrcaPreoptWorkChain.spec().inputs['options']
    assert port.required is False


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


def test_has_relaxed_structures_namespace():
    assert 'relaxed_structures' in OrcaPreoptWorkChain.spec().outputs


def test_relaxed_structures_is_dynamic():
    port = OrcaPreoptWorkChain.spec().outputs['relaxed_structures']
    assert port.dynamic is True


def test_has_energies_output():
    port = OrcaPreoptWorkChain.spec().outputs['energies']
    assert issubclass(port.valid_type, orm.List)


def test_has_preopt_report_output():
    port = OrcaPreoptWorkChain.spec().outputs['preopt_report']
    assert issubclass(port.valid_type, orm.Dict)


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


def test_exit_code_no_conformers():
    codes = OrcaPreoptWorkChain.spec().exit_codes
    assert hasattr(codes, 'ERROR_NO_CONFORMERS')
    assert codes.ERROR_NO_CONFORMERS.status == 410


def test_exit_code_insufficient_converged():
    codes = OrcaPreoptWorkChain.spec().exit_codes
    assert hasattr(codes, 'ERROR_INSUFFICIENT_CONVERGED')
    assert codes.ERROR_INSUFFICIENT_CONVERGED.status == 411
