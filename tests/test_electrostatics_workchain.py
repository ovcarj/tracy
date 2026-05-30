"""Process-spec tests for ComputeMembranePotentialWorkChain."""

from __future__ import annotations

from aiida import orm
from aiida.engine import WorkChain

from tracy.workflows.electrostatics import ComputeMembranePotentialWorkChain


def test_is_workchain_subclass():
    assert issubclass(ComputeMembranePotentialWorkChain, WorkChain)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def test_has_tpr_file_input():
    port = ComputeMembranePotentialWorkChain.spec().inputs["tpr_file"]
    assert port.required is True
    assert issubclass(port.valid_type, orm.SinglefileData)


def test_has_trajectory_compressed_input():
    port = ComputeMembranePotentialWorkChain.spec().inputs["trajectory_compressed"]
    assert port.required is True
    assert issubclass(port.valid_type, orm.SinglefileData)


def test_index_file_is_optional():
    port = ComputeMembranePotentialWorkChain.spec().inputs["index_file"]
    assert port.required is False


def test_has_protocol_input():
    port = ComputeMembranePotentialWorkChain.spec().inputs["protocol"]
    assert port.required is True
    assert issubclass(port.valid_type, orm.Dict)


def test_has_code_input():
    port = ComputeMembranePotentialWorkChain.spec().inputs["code"]
    assert port.required is True


def test_options_is_optional():
    port = ComputeMembranePotentialWorkChain.spec().inputs["options"]
    assert port.required is False


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


def test_has_potential_profile_output():
    port = ComputeMembranePotentialWorkChain.spec().outputs["potential_profile"]
    assert issubclass(port.valid_type, orm.SinglefileData)


def test_has_potential_report_output():
    port = ComputeMembranePotentialWorkChain.spec().outputs["potential_report"]
    assert issubclass(port.valid_type, orm.Dict)


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


def test_exit_code_trjconv_failed():
    codes = ComputeMembranePotentialWorkChain.spec().exit_codes
    assert hasattr(codes, "ERROR_TRJCONV_FAILED")
    assert codes.ERROR_TRJCONV_FAILED.status == 500


def test_exit_code_potential_failed():
    codes = ComputeMembranePotentialWorkChain.spec().exit_codes
    assert hasattr(codes, "ERROR_POTENTIAL_FAILED")
    assert codes.ERROR_POTENTIAL_FAILED.status == 501
