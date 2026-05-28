"""Tests for the CHARMM-GUI output adapter."""

from __future__ import annotations

from pathlib import Path

import pytest
from aiida import orm

from tracy.adapters.charmm_gui import (
    collect_charmm_gui_metadata,
    extract_gromacs_input_bundle,
    find_gromacs_directory,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def charmm_gui_folder(tmp_path: Path) -> orm.FolderData:
    """Fake CHARMM-GUI Quick Bilayer output: job_dir/gromacs/..."""
    job_dir = tmp_path / "charmm_gui_job_12345"
    gromacs = job_dir / "gromacs"
    toppar = gromacs / "toppar"
    toppar.mkdir(parents=True)

    (gromacs / "step5_input.gro").write_text("GROMACS structure")
    (gromacs / "topol.top").write_text("[ defaults ]")
    (toppar / "LIPID.itp").write_text("[ moleculetype ]")
    (gromacs / "step6.0_minimization.mdp").write_text("integrator = steep")
    (gromacs / "step6.1_equilibration.mdp").write_text("integrator = md")
    (gromacs / "step7_production.mdp").write_text("integrator = md")
    (gromacs / "index.ndx").write_text("[ System ]")

    folder = orm.FolderData()
    folder.put_object_from_tree(str(tmp_path))
    return folder


@pytest.fixture
def charmm_gui_folder_no_gromacs(tmp_path: Path) -> orm.FolderData:
    """Fake CHARMM-GUI output that contains only a NAMD directory."""
    namd = tmp_path / "charmm_gui_job_99999" / "namd"
    namd.mkdir(parents=True)
    (namd / "par_all36_lipid.prm").write_text("NAMD parameters")

    folder = orm.FolderData()
    folder.put_object_from_tree(str(tmp_path))
    return folder


@pytest.fixture
def charmm_gui_folder_nested(tmp_path: Path) -> orm.FolderData:
    """GROMACS directory nested two levels deep (job_dir/output/gromacs/...)."""
    gromacs = tmp_path / "job_abc" / "output" / "gromacs"
    gromacs.mkdir(parents=True)
    (gromacs / "step5_input.gro").write_text("structure")
    (gromacs / "topol.top").write_text("topology")
    (gromacs / "production.mdp").write_text("mdp")

    folder = orm.FolderData()
    folder.put_object_from_tree(str(tmp_path))
    return folder


# ---------------------------------------------------------------------------
# find_gromacs_directory
# ---------------------------------------------------------------------------


def test_find_gromacs_directory_returns_path(charmm_gui_folder: orm.FolderData):
    path = find_gromacs_directory(charmm_gui_folder)
    assert path is not None
    assert path.endswith("gromacs")


def test_find_gromacs_directory_nested(charmm_gui_folder_nested: orm.FolderData):
    path = find_gromacs_directory(charmm_gui_folder_nested)
    assert path is not None
    assert path.endswith("gromacs")


def test_find_gromacs_directory_missing(charmm_gui_folder_no_gromacs: orm.FolderData):
    path = find_gromacs_directory(charmm_gui_folder_no_gromacs)
    assert path is None


# ---------------------------------------------------------------------------
# extract_gromacs_input_bundle
# ---------------------------------------------------------------------------


def test_extract_returns_folder_data(charmm_gui_folder: orm.FolderData):
    bundle = extract_gromacs_input_bundle(charmm_gui_folder)
    assert bundle is not None
    assert isinstance(bundle, orm.FolderData)


def test_extract_bundle_contains_structure(charmm_gui_folder: orm.FolderData):
    bundle = extract_gromacs_input_bundle(charmm_gui_folder)
    all_names = _all_filenames(bundle)
    assert "step5_input.gro" in all_names


def test_extract_bundle_contains_topology(charmm_gui_folder: orm.FolderData):
    bundle = extract_gromacs_input_bundle(charmm_gui_folder)
    all_names = _all_filenames(bundle)
    assert "topol.top" in all_names


def test_extract_bundle_contains_itp(charmm_gui_folder: orm.FolderData):
    bundle = extract_gromacs_input_bundle(charmm_gui_folder)
    all_names = _all_filenames(bundle)
    assert "LIPID.itp" in all_names


def test_extract_bundle_contains_mdp(charmm_gui_folder: orm.FolderData):
    bundle = extract_gromacs_input_bundle(charmm_gui_folder)
    all_names = _all_filenames(bundle)
    mdp_files = [n for n in all_names if n.endswith(".mdp")]
    assert len(mdp_files) >= 1


def test_extract_returns_none_when_no_gromacs(charmm_gui_folder_no_gromacs: orm.FolderData):
    bundle = extract_gromacs_input_bundle(charmm_gui_folder_no_gromacs)
    assert bundle is None


# ---------------------------------------------------------------------------
# collect_charmm_gui_metadata
# ---------------------------------------------------------------------------


def test_metadata_is_dict(charmm_gui_folder: orm.FolderData):
    meta = collect_charmm_gui_metadata(charmm_gui_folder)
    assert isinstance(meta, dict)


def test_metadata_records_job_dir(charmm_gui_folder: orm.FolderData):
    meta = collect_charmm_gui_metadata(charmm_gui_folder)
    assert "charmm_gui_job_dir" in meta
    assert "12345" in meta["charmm_gui_job_dir"]


def test_metadata_records_available_engines(charmm_gui_folder: orm.FolderData):
    meta = collect_charmm_gui_metadata(charmm_gui_folder)
    assert "available_md_engines" in meta
    assert "gromacs" in meta["available_md_engines"]


def test_metadata_no_gromacs(charmm_gui_folder_no_gromacs: orm.FolderData):
    """Metadata collection never raises even when there is no gromacs directory."""
    meta = collect_charmm_gui_metadata(charmm_gui_folder_no_gromacs)
    assert isinstance(meta, dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _all_filenames(folder_data: orm.FolderData) -> set[str]:
    """Return the set of bare filenames (no directory prefix) in a FolderData."""
    names: set[str] = set()
    for _dirpath, _dirs, filenames in folder_data.base.repository.walk():
        names.update(filenames)
    return names
