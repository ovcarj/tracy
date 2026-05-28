"""Tests for validate_gromacs_input_bundle."""

from __future__ import annotations

from pathlib import Path

import pytest

from tracy.data.gromacs import validate_gromacs_input_bundle


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_bundle(tmp_path: Path) -> Path:
    """Minimal valid GROMACS input bundle on the filesystem."""
    (tmp_path / "step5_input.gro").write_text("GROMACS structure placeholder")
    (tmp_path / "topol.top").write_text("[ defaults ]\n1 2 yes 0.5 0.8333")
    toppar = tmp_path / "toppar"
    toppar.mkdir()
    (toppar / "LIPID.itp").write_text("[ moleculetype ]\nLIPID 3")
    (tmp_path / "step6.0_minimization.mdp").write_text("integrator = steep\nnsteps = 5000")
    (tmp_path / "step6.1_equilibration.mdp").write_text("integrator = md\nnsteps = 50000")
    (tmp_path / "step7_production.mdp").write_text("integrator = md\nnsteps = 500000")
    (tmp_path / "index.ndx").write_text("[ System ]\n1 2 3 4")
    return tmp_path


# ---------------------------------------------------------------------------
# Valid bundle
# ---------------------------------------------------------------------------


def test_valid_bundle_is_valid(valid_bundle: Path):
    report = validate_gromacs_input_bundle(valid_bundle)
    assert report["valid"] is True
    assert report["errors"] == []


def test_valid_bundle_has_structures(valid_bundle: Path):
    report = validate_gromacs_input_bundle(valid_bundle)
    assert "step5_input.gro" in report["files"]["structures"]


def test_valid_bundle_has_topologies(valid_bundle: Path):
    report = validate_gromacs_input_bundle(valid_bundle)
    assert "topol.top" in report["files"]["topologies"]


def test_valid_bundle_has_mdp_files(valid_bundle: Path):
    report = validate_gromacs_input_bundle(valid_bundle)
    assert len(report["files"]["mdp_files"]) == 3


def test_valid_bundle_has_itp_files(valid_bundle: Path):
    report = validate_gromacs_input_bundle(valid_bundle)
    assert "LIPID.itp" in report["files"]["itp_files"]


def test_valid_bundle_has_index_file(valid_bundle: Path):
    report = validate_gromacs_input_bundle(valid_bundle)
    assert "index.ndx" in report["files"]["index_files"]


# ---------------------------------------------------------------------------
# Missing required files
# ---------------------------------------------------------------------------


def test_missing_topology(valid_bundle: Path):
    (valid_bundle / "topol.top").unlink()
    report = validate_gromacs_input_bundle(valid_bundle)
    assert report["valid"] is False
    assert any("topology" in e.lower() for e in report["errors"])


def test_missing_structure(valid_bundle: Path):
    (valid_bundle / "step5_input.gro").unlink()
    report = validate_gromacs_input_bundle(valid_bundle)
    assert report["valid"] is False
    assert any("structure" in e.lower() for e in report["errors"])


def test_missing_mdp_files(valid_bundle: Path):
    for mdp in valid_bundle.glob("*.mdp"):
        mdp.unlink()
    report = validate_gromacs_input_bundle(valid_bundle)
    assert report["valid"] is False
    assert any("mdp" in e.lower() for e in report["errors"])


def test_empty_folder(tmp_path: Path):
    report = validate_gromacs_input_bundle(tmp_path)
    assert report["valid"] is False
    assert len(report["errors"]) >= 3  # structure, topology, and mdp all missing


# ---------------------------------------------------------------------------
# Warnings (missing optional files)
# ---------------------------------------------------------------------------


def test_missing_itp_produces_warning(valid_bundle: Path):
    for itp in valid_bundle.rglob("*.itp"):
        itp.unlink()
    report = validate_gromacs_input_bundle(valid_bundle)
    assert report["valid"] is True  # itp is optional
    assert any(".itp" in w for w in report["warnings"])


def test_missing_ndx_produces_warning(valid_bundle: Path):
    (valid_bundle / "index.ndx").unlink()
    report = validate_gromacs_input_bundle(valid_bundle)
    assert report["valid"] is True  # ndx is optional
    assert any(".ndx" in w for w in report["warnings"])


# ---------------------------------------------------------------------------
# FolderData input
# ---------------------------------------------------------------------------


def test_accepts_folder_data(valid_bundle: Path):
    """validate_gromacs_input_bundle also accepts an AiiDA FolderData."""
    from aiida import orm

    folder = orm.FolderData()
    folder.put_object_from_tree(str(valid_bundle))
    report = validate_gromacs_input_bundle(folder)
    assert report["valid"] is True


# ---------------------------------------------------------------------------
# Type error
# ---------------------------------------------------------------------------


def test_type_error_on_wrong_input():
    with pytest.raises(TypeError):
        validate_gromacs_input_bundle("not_a_path_or_folder_data")
