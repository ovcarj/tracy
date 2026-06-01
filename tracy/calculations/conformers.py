"""RDKit ETKDG conformer generation as an AiiDA calcfunction."""

from __future__ import annotations

import os
import tempfile

from aiida import orm
from aiida.engine import calcfunction


@calcfunction
def generate_conformers(
    smiles: orm.Str,
    n_conformers: orm.Int,
    random_seed: orm.Int,
) -> orm.FolderData:
    """Generate 3D conformers from a SMILES string using RDKit ETKDG.

    Requires the ``tracy[rdkit]`` optional extra (``rdkit>=2023.3``).
    Returns a FolderData containing ``conformer_0.xyz``, ``conformer_1.xyz``, …
    May produce fewer files than ``n_conformers`` if embedding fails for some.
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
    except ImportError:
        raise ImportError(
            "RDKit is required for conformer generation. "
            "Install with: pip install tracy[rdkit]"
        )

    mol = Chem.MolFromSmiles(smiles.value)
    if mol is None:
        raise ValueError(f"Invalid SMILES string: {smiles.value!r}")
    mol = Chem.AddHs(mol)

    params = AllChem.ETKDGv3()
    params.randomSeed = random_seed.value

    conf_ids = AllChem.EmbedMultipleConfs(mol, numConfs=n_conformers.value, params=params)

    if not conf_ids:
        raise RuntimeError(
            f"RDKit could not embed any conformers for SMILES: {smiles.value!r}. "
            "Try a different SMILES or increase n_conformers."
        )

    folder = orm.FolderData()
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, conf_id in enumerate(conf_ids):
            path = os.path.join(tmpdir, f"conformer_{i}.xyz")
            _write_xyz(mol, conf_id, path)
            folder.put_object_from_file(path, f"conformer_{i}.xyz")

    return folder


def _write_xyz(mol, conf_id: int, path: str) -> None:
    """Write a single RDKit conformer to an XYZ file."""
    conf = mol.GetConformer(conf_id)
    n_atoms = mol.GetNumAtoms()
    with open(path, "w") as f:
        f.write(f"{n_atoms}\n\n")
        for atom in mol.GetAtoms():
            idx = atom.GetIdx()
            pos = conf.GetAtomPosition(idx)
            symbol = atom.GetSymbol()
            f.write(f"{symbol:<2}  {pos.x:12.6f}  {pos.y:12.6f}  {pos.z:12.6f}\n")
