"""Process-spec tests for RunMembraneMDWorkChain."""

from __future__ import annotations

from aiida import orm
from aiida.engine import WorkChain

from tracy.workflows.membrane_md import RunMembraneMDWorkChain


def test_is_workchain_subclass():
    assert issubclass(RunMembraneMDWorkChain, WorkChain)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def test_has_md_input_bundle():
    assert "md_input_bundle" in RunMembraneMDWorkChain.spec().inputs


def test_md_input_bundle_is_required():
    port = RunMembraneMDWorkChain.spec().inputs["md_input_bundle"]
    assert port.required is True
    assert issubclass(port.valid_type, orm.FolderData)


def test_has_protocol_input():
    port = RunMembraneMDWorkChain.spec().inputs["protocol"]
    assert port.required is True
    assert issubclass(port.valid_type, orm.Dict)


def test_has_code_input():
    port = RunMembraneMDWorkChain.spec().inputs["code"]
    assert port.required is True


def test_options_is_optional():
    port = RunMembraneMDWorkChain.spec().inputs["options"]
    assert port.required is False


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


def test_has_md_results_output():
    port = RunMembraneMDWorkChain.spec().outputs["md_results"]
    assert issubclass(port.valid_type, orm.FolderData)


def test_has_md_report_output():
    port = RunMembraneMDWorkChain.spec().outputs["md_report"]
    assert issubclass(port.valid_type, orm.Dict)


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


def test_exit_code_unsupported_engine():
    codes = RunMembraneMDWorkChain.spec().exit_codes
    assert hasattr(codes, "ERROR_UNSUPPORTED_ENGINE")
    assert codes.ERROR_UNSUPPORTED_ENGINE.status == 400


def test_exit_code_manifest_invalid():
    codes = RunMembraneMDWorkChain.spec().exit_codes
    assert hasattr(codes, "ERROR_MANIFEST_INVALID")
    assert codes.ERROR_MANIFEST_INVALID.status == 401


def test_exit_code_md_step_failed():
    codes = RunMembraneMDWorkChain.spec().exit_codes
    assert hasattr(codes, "ERROR_MD_STEP_FAILED")
    assert codes.ERROR_MD_STEP_FAILED.status == 402
