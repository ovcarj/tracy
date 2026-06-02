"""Process-spec tests for OrcaOptWorkChain."""

from __future__ import annotations

import pytest
from aiida import orm
from aiida.engine import WorkChain

from tracy.workflows.orca_opt import OrcaOptWorkChain


# ---------------------------------------------------------------------------
# Solvent keyword logic (pure-Python, no AiiDA profile needed)
# ---------------------------------------------------------------------------


def _build_opt_keywords(
    method: str, basis: str, dispersion: str, resp_keyword: str, solvent: str | None
) -> list[str]:
    """Mirror the keyword-building logic from OrcaOptWorkChain.setup()."""
    keywords = [method, basis, dispersion, 'OPT', resp_keyword]
    if solvent:
        keywords.append(f'CPCM({solvent})')
    return keywords


def test_vacuum_opt_keywords():
    kw = _build_opt_keywords('B3LYP', 'def2-SVP', 'D3BJ', 'RESP', None)
    assert kw == ['B3LYP', 'def2-SVP', 'D3BJ', 'OPT', 'RESP']
    assert not any('CPCM' in k for k in kw)


def test_water_opt_adds_cpcm():
    kw = _build_opt_keywords('B3LYP', 'def2-SVP', 'D3BJ', 'RESP', 'Water')
    assert 'CPCM(Water)' in kw


def test_arbitrary_solvent_opt():
    kw = _build_opt_keywords('B3LYP', 'def2-SVP', 'D3BJ', 'RESP', 'DMSO')
    assert 'CPCM(DMSO)' in kw


def test_is_workchain_subclass():
    assert issubclass(OrcaOptWorkChain, WorkChain)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def test_has_structures_namespace():
    assert 'structures' in OrcaOptWorkChain.spec().inputs


def test_structures_is_dynamic():
    port = OrcaOptWorkChain.spec().inputs['structures']
    assert port.dynamic is True


def test_has_orca_code_input():
    port = OrcaOptWorkChain.spec().inputs['orca_code']
    assert port.required is True


def test_has_parameters_input():
    port = OrcaOptWorkChain.spec().inputs['parameters']
    assert port.required is True
    assert issubclass(port.valid_type, orm.Dict)


def test_options_is_optional():
    port = OrcaOptWorkChain.spec().inputs['options']
    assert port.required is False


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


def test_has_relaxed_structure_output():
    port = OrcaOptWorkChain.spec().outputs['relaxed_structure']
    assert port.required is True
    assert issubclass(port.valid_type, orm.StructureData)


def test_has_output_parameters():
    port = OrcaOptWorkChain.spec().outputs['output_parameters']
    assert issubclass(port.valid_type, orm.Dict)


def test_has_all_results_namespace():
    port = OrcaOptWorkChain.spec().outputs['all_results']
    assert port.dynamic is True


def test_has_opt_report_output():
    port = OrcaOptWorkChain.spec().outputs['opt_report']
    assert issubclass(port.valid_type, orm.Dict)


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


def test_exit_code_no_structures():
    codes = OrcaOptWorkChain.spec().exit_codes
    assert hasattr(codes, 'ERROR_NO_STRUCTURES')
    assert codes.ERROR_NO_STRUCTURES.status == 420


def test_exit_code_no_converged_structures():
    codes = OrcaOptWorkChain.spec().exit_codes
    assert hasattr(codes, 'ERROR_NO_CONVERGED_STRUCTURES')
    assert codes.ERROR_NO_CONVERGED_STRUCTURES.status == 421
