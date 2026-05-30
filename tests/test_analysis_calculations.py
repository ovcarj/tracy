"""Spec tests for TrjconvCalculation, PotentialCalculation, SelectGroupsCalculation."""

from __future__ import annotations

from aiida import orm
from aiida.engine import CalcJob

from tracy.calculations.trjconv import TrjconvCalculation
from tracy.calculations.potential import PotentialCalculation
from tracy.calculations.select_groups import SelectGroupsCalculation


# ---------------------------------------------------------------------------
# TrjconvCalculation
# ---------------------------------------------------------------------------


def test_trjconv_is_calcjob():
    assert issubclass(TrjconvCalculation, CalcJob)


def test_trjconv_required_inputs():
    spec = TrjconvCalculation.spec()
    assert spec.inputs["trajectory"].required is True
    assert spec.inputs["tpr_file"].required is True
    assert spec.inputs["center_group"].required is True


def test_trjconv_optional_inputs():
    spec = TrjconvCalculation.spec()
    assert spec.inputs["index_file"].required is False
    assert spec.inputs["output_group"].required is False


def test_trjconv_has_trajectory_output():
    spec = TrjconvCalculation.spec()
    assert "trajectory" in spec.outputs


def test_trjconv_exit_code():
    codes = TrjconvCalculation.spec().exit_codes
    assert hasattr(codes, "ERROR_MISSING_OUTPUT_FILES")
    assert codes.ERROR_MISSING_OUTPUT_FILES.status == 300


def test_trjconv_parser_name_default():
    spec = TrjconvCalculation.spec()
    assert spec.inputs["metadata"]["options"]["parser_name"].default == "tracy.trjconv"


def test_trjconv_withmpi_default_false():
    spec = TrjconvCalculation.spec()
    assert spec.inputs["metadata"]["options"]["withmpi"].default is False


# ---------------------------------------------------------------------------
# PotentialCalculation
# ---------------------------------------------------------------------------


def test_potential_is_calcjob():
    assert issubclass(PotentialCalculation, CalcJob)


def test_potential_required_inputs():
    spec = PotentialCalculation.spec()
    assert spec.inputs["trajectory"].required is True
    assert spec.inputs["tpr_file"].required is True


def test_potential_optional_inputs():
    spec = PotentialCalculation.spec()
    assert spec.inputs["index_file"].required is False
    assert spec.inputs["charge_group"].required is False
    assert spec.inputs["n_slices"].required is False
    assert spec.inputs["symmetrize"].required is False
    assert spec.inputs["correct"].required is False


def test_potential_has_xvg_output():
    spec = PotentialCalculation.spec()
    assert "potential_xvg" in spec.outputs


def test_potential_exit_code():
    codes = PotentialCalculation.spec().exit_codes
    assert hasattr(codes, "ERROR_MISSING_OUTPUT_FILES")
    assert codes.ERROR_MISSING_OUTPUT_FILES.status == 300


def test_potential_parser_name_default():
    spec = PotentialCalculation.spec()
    assert spec.inputs["metadata"]["options"]["parser_name"].default == "tracy.potential"


def test_potential_withmpi_default_false():
    spec = PotentialCalculation.spec()
    assert spec.inputs["metadata"]["options"]["withmpi"].default is False


# ---------------------------------------------------------------------------
# SelectGroupsCalculation
# ---------------------------------------------------------------------------


def test_select_groups_is_calcjob():
    assert issubclass(SelectGroupsCalculation, CalcJob)


def test_select_groups_required_inputs():
    spec = SelectGroupsCalculation.spec()
    assert spec.inputs["tpr_file"].required is True
    assert spec.inputs["selections"].required is True


def test_select_groups_optional_inputs():
    spec = SelectGroupsCalculation.spec()
    assert spec.inputs["index_file"].required is False


def test_select_groups_has_index_output():
    spec = SelectGroupsCalculation.spec()
    assert "index_file" in spec.outputs
    assert issubclass(spec.outputs["index_file"].valid_type, orm.SinglefileData)


def test_select_groups_exit_code():
    codes = SelectGroupsCalculation.spec().exit_codes
    assert hasattr(codes, "ERROR_MISSING_OUTPUT_FILES")
    assert codes.ERROR_MISSING_OUTPUT_FILES.status == 300


def test_select_groups_parser_name_default():
    spec = SelectGroupsCalculation.spec()
    assert spec.inputs["metadata"]["options"]["parser_name"].default == "tracy.select_groups"


def test_select_groups_withmpi_default_false():
    spec = SelectGroupsCalculation.spec()
    assert spec.inputs["metadata"]["options"]["withmpi"].default is False
