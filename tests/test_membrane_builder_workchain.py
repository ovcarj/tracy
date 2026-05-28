"""WorkChain process-spec tests for BuildMembraneWorkChain.

These tests inspect the declared spec (inputs, outputs, exit codes) without
executing the WorkChain or connecting to CHARMM-GUI.
"""

from __future__ import annotations

import pytest
from aiida import orm
from aiida.engine import WorkChain

from tracy.workflows.membrane_builder import BuildMembraneWorkChain


# ---------------------------------------------------------------------------
# Class-level checks
# ---------------------------------------------------------------------------


def test_is_workchain_subclass():
    assert issubclass(BuildMembraneWorkChain, WorkChain)


# ---------------------------------------------------------------------------
# Input spec
# ---------------------------------------------------------------------------


def test_has_protocol_input():
    assert "protocol" in BuildMembraneWorkChain.spec().inputs


def test_protocol_is_required():
    port = BuildMembraneWorkChain.spec().inputs["protocol"]
    assert port.required is True


def test_protocol_valid_type_is_dict():
    port = BuildMembraneWorkChain.spec().inputs["protocol"]
    assert issubclass(port.valid_type, orm.Dict)


def test_has_charmm_gui_output_input():
    assert "charmm_gui_output" in BuildMembraneWorkChain.spec().inputs


def test_charmm_gui_output_is_optional():
    port = BuildMembraneWorkChain.spec().inputs["charmm_gui_output"]
    assert port.required is False


def test_charmm_gui_output_valid_type_is_folder_data():
    port = BuildMembraneWorkChain.spec().inputs["charmm_gui_output"]
    # Optional ports store valid_type as (Class, NoneType) tuple.
    vt = port.valid_type
    types = vt if isinstance(vt, tuple) else (vt,)
    assert orm.FolderData in types


# ---------------------------------------------------------------------------
# Output spec
# ---------------------------------------------------------------------------


def test_has_charmm_gui_output_output():
    assert "charmm_gui_output" in BuildMembraneWorkChain.spec().outputs


def test_has_gromacs_input_bundle_output():
    assert "gromacs_input_bundle" in BuildMembraneWorkChain.spec().outputs


def test_has_system_metadata_output():
    assert "system_metadata" in BuildMembraneWorkChain.spec().outputs


def test_has_validation_report_output():
    assert "validation_report" in BuildMembraneWorkChain.spec().outputs


def test_gromacs_input_bundle_type():
    port = BuildMembraneWorkChain.spec().outputs["gromacs_input_bundle"]
    assert issubclass(port.valid_type, orm.FolderData)


def test_system_metadata_type():
    port = BuildMembraneWorkChain.spec().outputs["system_metadata"]
    assert issubclass(port.valid_type, orm.Dict)


def test_validation_report_type():
    port = BuildMembraneWorkChain.spec().outputs["validation_report"]
    assert issubclass(port.valid_type, orm.Dict)


# ---------------------------------------------------------------------------
# Exit code spec
# ---------------------------------------------------------------------------


def test_exit_code_missing_charmm_gui_output():
    codes = BuildMembraneWorkChain.spec().exit_codes
    assert hasattr(codes, "ERROR_MISSING_CHARMM_GUI_OUTPUT")
    assert codes.ERROR_MISSING_CHARMM_GUI_OUTPUT.status == 400


def test_exit_code_extraction_failed():
    codes = BuildMembraneWorkChain.spec().exit_codes
    assert hasattr(codes, "ERROR_GROMACS_BUNDLE_EXTRACTION_FAILED")
    assert codes.ERROR_GROMACS_BUNDLE_EXTRACTION_FAILED.status == 401


def test_exit_code_bundle_invalid():
    codes = BuildMembraneWorkChain.spec().exit_codes
    assert hasattr(codes, "ERROR_GROMACS_BUNDLE_INVALID")
    assert codes.ERROR_GROMACS_BUNDLE_INVALID.status == 402
