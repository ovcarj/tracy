"""Tests for generate_conformers calcfunction."""

from __future__ import annotations

import importlib.util

import pytest

rdkit_missing = importlib.util.find_spec("rdkit") is None
pytestmark = pytest.mark.skipif(rdkit_missing, reason="rdkit not installed")

GLYCINE_SMILES = "NCC(=O)O"
GLYCINE_N_ATOMS = 10  # with explicit H


def test_generate_conformers_returns_folder_data():
    from aiida import orm
    from aiida.orm import FolderData
    from tracy.calculations.conformers import generate_conformers

    result = generate_conformers(
        smiles=orm.Str(GLYCINE_SMILES),
        n_conformers=orm.Int(3),
        random_seed=orm.Int(42),
    )
    assert isinstance(result, FolderData)


def test_generate_conformers_file_count():
    from aiida import orm
    from tracy.calculations.conformers import generate_conformers

    result = generate_conformers(
        smiles=orm.Str(GLYCINE_SMILES),
        n_conformers=orm.Int(5),
        random_seed=orm.Int(42),
    )
    xyz_files = [n for n in result.list_object_names() if n.endswith(".xyz")]
    assert len(xyz_files) == 5


def test_generate_conformers_file_names():
    from aiida import orm
    from tracy.calculations.conformers import generate_conformers

    result = generate_conformers(
        smiles=orm.Str(GLYCINE_SMILES),
        n_conformers=orm.Int(3),
        random_seed=orm.Int(0),
    )
    assert set(result.list_object_names()) == {
        "conformer_0.xyz",
        "conformer_1.xyz",
        "conformer_2.xyz",
    }


def test_generate_conformers_xyz_format():
    from aiida import orm
    from tracy.calculations.conformers import generate_conformers

    result = generate_conformers(
        smiles=orm.Str(GLYCINE_SMILES),
        n_conformers=orm.Int(1),
        random_seed=orm.Int(42),
    )
    content = result.get_object_content("conformer_0.xyz")
    lines = content.strip().splitlines()
    n_atoms = int(lines[0].strip())
    assert n_atoms == GLYCINE_N_ATOMS
    data_lines = [l for l in lines[2:] if l.strip()]
    assert len(data_lines) == GLYCINE_N_ATOMS
    # each data line: symbol + 3 floats
    parts = data_lines[0].split()
    assert len(parts) == 4
    float(parts[1])
    float(parts[2])
    float(parts[3])


def test_generate_conformers_reproducible():
    from aiida import orm
    from tracy.calculations.conformers import generate_conformers

    r1 = generate_conformers(
        smiles=orm.Str(GLYCINE_SMILES),
        n_conformers=orm.Int(1),
        random_seed=orm.Int(99),
    )
    r2 = generate_conformers(
        smiles=orm.Str(GLYCINE_SMILES),
        n_conformers=orm.Int(1),
        random_seed=orm.Int(99),
    )
    assert r1.get_object_content("conformer_0.xyz") == r2.get_object_content("conformer_0.xyz")


def test_generate_conformers_invalid_smiles():
    from aiida import orm
    from tracy.calculations.conformers import generate_conformers

    with pytest.raises(ValueError, match="Invalid SMILES"):
        generate_conformers(
            smiles=orm.Str("not-a-valid-smiles!!!"),
            n_conformers=orm.Int(1),
            random_seed=orm.Int(0),
        )
