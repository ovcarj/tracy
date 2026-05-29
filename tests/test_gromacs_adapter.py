"""Tests for tracy.adapters.gromacs."""

from __future__ import annotations

from pathlib import Path

import pytest
from aiida import orm

from tracy.adapters.gromacs import build_step_manifest, prepare_gromacs_run_inputs

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "gromacs_bundle"


# ---------------------------------------------------------------------------
# build_step_manifest — Path input (no AiiDA needed)
# ---------------------------------------------------------------------------


def test_manifest_returns_list():
    manifest = build_step_manifest(FIXTURE_DIR)
    assert isinstance(manifest, list)


def test_manifest_length():
    manifest = build_step_manifest(FIXTURE_DIR)
    assert len(manifest) == 8  # 1 min + 6 equil + 1 prod


def test_manifest_order_is_zero_indexed():
    manifest = build_step_manifest(FIXTURE_DIR)
    assert [s["order"] for s in manifest] == list(range(len(manifest)))


def test_manifest_first_step_is_minimization():
    manifest = build_step_manifest(FIXTURE_DIR)
    assert manifest[0]["name"] == "minimization"
    assert manifest[0]["mdp"] == "step6.0_minimization.mdp"
    assert manifest[0]["step_id"] == "step6.0"


def test_manifest_last_step_is_production():
    manifest = build_step_manifest(FIXTURE_DIR)
    assert manifest[-1]["name"] == "production"
    assert manifest[-1]["mdp"] == "step7_production.mdp"
    assert manifest[-1]["step_id"] == "step7"


def test_manifest_equilibration_steps():
    manifest = build_step_manifest(FIXTURE_DIR)
    equil = [s for s in manifest if s["name"] == "equilibration"]
    assert len(equil) == 6
    assert equil[0]["mdp"] == "step6.1_equilibration.mdp"
    assert equil[-1]["mdp"] == "step6.6_equilibration.mdp"


def test_manifest_all_keys_present():
    manifest = build_step_manifest(FIXTURE_DIR)
    for step in manifest:
        assert "name" in step
        assert "order" in step
        assert "mdp" in step
        assert "step_id" in step


def test_manifest_no_mdp_files_raises(tmp_path):
    (tmp_path / "topol.top").write_text("")
    (tmp_path / "step5_input.gro").write_text("")
    with pytest.raises(ValueError, match="No MDP files"):
        build_step_manifest(tmp_path)


def test_manifest_gap_in_sequence_raises(tmp_path):
    (tmp_path / "step6.0_minimization.mdp").write_text("")
    (tmp_path / "step6.2_equilibration.mdp").write_text("")  # gap: missing 6.1
    with pytest.raises(ValueError, match="gaps"):
        build_step_manifest(tmp_path)


def test_manifest_single_step(tmp_path):
    (tmp_path / "step6.0_minimization.mdp").write_text("")
    manifest = build_step_manifest(tmp_path)
    assert len(manifest) == 1
    assert manifest[0]["name"] == "minimization"
    assert manifest[0]["order"] == 0


def test_manifest_accepts_folder_data():
    bundle = orm.FolderData()
    bundle.put_object_from_tree(str(FIXTURE_DIR))
    manifest = build_step_manifest(bundle)
    assert len(manifest) == 8


def test_manifest_type_error_on_wrong_input():
    with pytest.raises(TypeError):
        build_step_manifest("not-a-valid-input")


# ---------------------------------------------------------------------------
# prepare_gromacs_run_inputs — requires AiiDA FolderData
# ---------------------------------------------------------------------------


def _make_bundle():
    bundle = orm.FolderData()
    bundle.put_object_from_tree(str(FIXTURE_DIR))
    return bundle


def test_prepare_returns_dict():
    result = prepare_gromacs_run_inputs(_make_bundle())
    assert isinstance(result, dict)


def test_prepare_has_structure():
    result = prepare_gromacs_run_inputs(_make_bundle())
    assert "structure" in result
    assert isinstance(result["structure"], orm.SinglefileData)
    assert result["structure"].filename == "step5_input.gro"


def test_prepare_has_topology():
    result = prepare_gromacs_run_inputs(_make_bundle())
    assert "topology" in result
    assert isinstance(result["topology"], orm.SinglefileData)
    assert result["topology"].filename == "topol.top"


def test_prepare_has_toppar():
    result = prepare_gromacs_run_inputs(_make_bundle())
    assert "toppar" in result
    assert isinstance(result["toppar"], orm.FolderData)


def test_prepare_toppar_contains_itp_files():
    result = prepare_gromacs_run_inputs(_make_bundle())
    names = result["toppar"].list_object_names()
    assert any(n.endswith(".itp") for n in names)


def test_prepare_has_index():
    result = prepare_gromacs_run_inputs(_make_bundle())
    assert "index" in result
    assert isinstance(result["index"], orm.SinglefileData)
    assert result["index"].filename == "index.ndx"


def test_prepare_no_index_when_absent(tmp_path):
    (tmp_path / "step5_input.gro").write_text("gro content")
    (tmp_path / "topol.top").write_text("top content")
    (tmp_path / "toppar").mkdir()
    (tmp_path / "toppar" / "ff.itp").write_text("")
    bundle = orm.FolderData()
    bundle.put_object_from_tree(str(tmp_path))
    result = prepare_gromacs_run_inputs(bundle)
    assert "index" not in result
