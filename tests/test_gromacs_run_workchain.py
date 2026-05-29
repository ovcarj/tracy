"""Process-spec tests for GromacsRunWorkChain."""

from __future__ import annotations

import pytest
from aiida import orm
from aiida.engine import WorkChain

from tracy.workflows.gromacs_run import GromacsRunWorkChain


def test_is_workchain_subclass():
    assert issubclass(GromacsRunWorkChain, WorkChain)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def test_has_structure_input():
    assert "structure" in GromacsRunWorkChain.spec().inputs


def test_structure_is_required():
    port = GromacsRunWorkChain.spec().inputs["structure"]
    assert port.required is True
    assert issubclass(port.valid_type, orm.SinglefileData)


def test_has_topology_input():
    assert "topology" in GromacsRunWorkChain.spec().inputs


def test_topology_is_required():
    port = GromacsRunWorkChain.spec().inputs["topology"]
    assert port.required is True
    assert issubclass(port.valid_type, orm.SinglefileData)


def test_has_toppar_input():
    assert "toppar" in GromacsRunWorkChain.spec().inputs


def test_toppar_is_required():
    port = GromacsRunWorkChain.spec().inputs["toppar"]
    assert port.required is True
    assert issubclass(port.valid_type, orm.FolderData)


def test_has_mdp_file_input():
    port = GromacsRunWorkChain.spec().inputs["mdp_file"]
    assert port.required is True
    assert issubclass(port.valid_type, orm.SinglefileData)


def test_has_gromacs_code_input():
    port = GromacsRunWorkChain.spec().inputs["gromacs_code"]
    assert port.required is True


def test_index_file_is_optional():
    port = GromacsRunWorkChain.spec().inputs["index_file"]
    assert port.required is False


def test_checkpoint_input_is_optional():
    port = GromacsRunWorkChain.spec().inputs["checkpoint"]
    assert port.required is False


def test_options_is_optional():
    port = GromacsRunWorkChain.spec().inputs["options"]
    assert port.required is False


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


def test_has_output_structure():
    port = GromacsRunWorkChain.spec().outputs["output_structure"]
    assert issubclass(port.valid_type, orm.SinglefileData)


def test_has_trajectory_output():
    port = GromacsRunWorkChain.spec().outputs["trajectory"]
    assert issubclass(port.valid_type, orm.SinglefileData)


def test_has_energy_output():
    port = GromacsRunWorkChain.spec().outputs["energy"]
    assert issubclass(port.valid_type, orm.SinglefileData)


def test_has_log_output():
    port = GromacsRunWorkChain.spec().outputs["log"]
    assert issubclass(port.valid_type, orm.SinglefileData)


def test_checkpoint_output_is_optional():
    port = GromacsRunWorkChain.spec().outputs["checkpoint"]
    assert port.required is False


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


def test_exit_code_grompp_failed():
    codes = GromacsRunWorkChain.spec().exit_codes
    assert hasattr(codes, "ERROR_GROMPP_FAILED")
    assert codes.ERROR_GROMPP_FAILED.status == 300


def test_exit_code_mdrun_failed():
    codes = GromacsRunWorkChain.spec().exit_codes
    assert hasattr(codes, "ERROR_MDRUN_FAILED")
    assert codes.ERROR_MDRUN_FAILED.status == 301
