"""Process-spec tests for RunMembraneMDWorkChain."""

from __future__ import annotations
from types import SimpleNamespace
from unittest.mock import MagicMock

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


# ---------------------------------------------------------------------------
# initial_structure input
# ---------------------------------------------------------------------------


def test_has_initial_structure_input():
    assert "initial_structure" in RunMembraneMDWorkChain.spec().inputs


def test_initial_structure_is_optional():
    port = RunMembraneMDWorkChain.spec().inputs["initial_structure"]
    assert port.required is False
    valid = port.valid_type
    # AiiDA wraps optional types as (Type, NoneType); handle both forms
    if isinstance(valid, tuple):
        assert any(issubclass(t, orm.SinglefileData) for t in valid if isinstance(t, type))
    else:
        assert issubclass(valid, orm.SinglefileData)


# ---------------------------------------------------------------------------
# max_retries / inspect_step logic
# ---------------------------------------------------------------------------


def _make_wc(max_retries=2):
    """Return a minimal mock of RunMembraneMDWorkChain for inspect_step testing."""
    wc = MagicMock(spec=RunMembraneMDWorkChain)
    wc.ctx = SimpleNamespace(
        current_step_index=0,
        step_retries={},
        max_retries=max_retries,
        completed_steps=[],
        manifest=[{"name": "equilibration", "prefix": "equilibration_1",
                   "mdp": "step6.1.mdp", "step_id": "step6.1"}],
    )
    wc.exit_codes = RunMembraneMDWorkChain.spec().exit_codes
    wc.report = lambda msg: None
    wc.out = lambda *a, **kw: None
    # Bind the real inspect_step implementation
    wc.inspect_step = RunMembraneMDWorkChain.inspect_step.__get__(wc)
    return wc


def test_inspect_step_retries_on_failure():
    wc = _make_wc(max_retries=2)
    failed_child = MagicMock()
    failed_child.is_finished_ok = False
    failed_child.exit_status = 301
    wc.ctx.current_step_wc = failed_child

    result = wc.inspect_step()
    assert result is None  # first failure → retry, no exit code
    assert wc.ctx.step_retries[0] == 1


def test_inspect_step_returns_error_after_max_retries():
    wc = _make_wc(max_retries=1)
    wc.ctx.step_retries = {0: 1}  # already used 1 retry
    failed_child = MagicMock()
    failed_child.is_finished_ok = False
    failed_child.exit_status = 301
    wc.ctx.current_step_wc = failed_child

    result = wc.inspect_step()
    assert result == wc.exit_codes.ERROR_MD_STEP_FAILED


def test_inspect_step_no_retry_when_max_retries_zero():
    wc = _make_wc(max_retries=0)
    failed_child = MagicMock()
    failed_child.is_finished_ok = False
    failed_child.exit_status = 301
    wc.ctx.current_step_wc = failed_child

    result = wc.inspect_step()
    assert result == wc.exit_codes.ERROR_MD_STEP_FAILED
    assert wc.ctx.step_retries == {}  # counter never written when max_retries=0
