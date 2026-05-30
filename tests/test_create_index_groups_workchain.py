"""Spec tests for CreateIndexGroupsWorkChain."""

from __future__ import annotations

from aiida import orm
from aiida.engine import WorkChain

from tracy.workflows.create_index_groups import CreateIndexGroupsWorkChain


def test_is_workchain_subclass():
    assert issubclass(CreateIndexGroupsWorkChain, WorkChain)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def test_has_tpr_file_input():
    port = CreateIndexGroupsWorkChain.spec().inputs["tpr_file"]
    assert port.required is True
    assert issubclass(port.valid_type, orm.SinglefileData)


def test_index_file_is_optional():
    port = CreateIndexGroupsWorkChain.spec().inputs["index_file"]
    assert port.required is False


def test_has_selections_input():
    port = CreateIndexGroupsWorkChain.spec().inputs["selections"]
    assert port.required is True
    assert issubclass(port.valid_type, orm.List)


def test_has_protocol_input():
    port = CreateIndexGroupsWorkChain.spec().inputs["protocol"]
    assert port.required is True
    assert issubclass(port.valid_type, orm.Dict)


def test_has_code_input():
    port = CreateIndexGroupsWorkChain.spec().inputs["code"]
    assert port.required is True


def test_options_is_optional():
    port = CreateIndexGroupsWorkChain.spec().inputs["options"]
    assert port.required is False


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


def test_has_index_file_output():
    port = CreateIndexGroupsWorkChain.spec().outputs["index_file"]
    assert issubclass(port.valid_type, orm.SinglefileData)


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


def test_exit_code_unsupported_engine():
    codes = CreateIndexGroupsWorkChain.spec().exit_codes
    assert hasattr(codes, "ERROR_UNSUPPORTED_ENGINE")
    assert codes.ERROR_UNSUPPORTED_ENGINE.status == 520


def test_exit_code_select_groups_failed():
    codes = CreateIndexGroupsWorkChain.spec().exit_codes
    assert hasattr(codes, "ERROR_SELECT_GROUPS_FAILED")
    assert codes.ERROR_SELECT_GROUPS_FAILED.status == 521
