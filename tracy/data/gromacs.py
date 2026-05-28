"""GROMACS input bundle validation.

Keeps all GROMACS file-structure knowledge in one place so WorkChains and
adapters do not need to know about file extensions or expected file names.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Union

_STRUCTURE_EXTENSIONS = frozenset({".gro", ".pdb"})
_TOPOLOGY_EXTENSIONS = frozenset({".top"})
_ITP_EXTENSIONS = frozenset({".itp"})
_MDP_EXTENSIONS = frozenset({".mdp"})
_INDEX_EXTENSIONS = frozenset({".ndx"})


def validate_gromacs_input_bundle(folder: Union["orm.FolderData", Path]) -> dict:
    """Return a structured validation report for a GROMACS input bundle.

    Args:
        folder: An AiiDA ``FolderData`` or a ``pathlib.Path`` to a GROMACS directory.

    Returns:
        Dict with keys:
            valid (bool): True if all required file categories are present.
            errors (list[str]): Blocking issues (missing required files).
            warnings (list[str]): Non-blocking observations.
            files (dict): Categorised file lists found in the bundle.

    Raises:
        TypeError: If ``folder`` is neither a FolderData nor a Path.
    """
    try:
        from aiida import orm as _orm
        if isinstance(folder, _orm.FolderData):
            with tempfile.TemporaryDirectory() as tmpdir:
                folder.base.repository.copy_tree(tmpdir)
                return _validate_path(Path(tmpdir))
    except ImportError:
        pass

    if isinstance(folder, Path):
        return _validate_path(folder)

    raise TypeError(f"Expected FolderData or Path, got {type(folder)!r}")


def _validate_path(base: Path) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    file_paths = [p for p in base.rglob("*") if p.is_file()]

    structures = sorted(p.name for p in file_paths if p.suffix.lower() in _STRUCTURE_EXTENSIONS)
    topologies = sorted(p.name for p in file_paths if p.suffix.lower() in _TOPOLOGY_EXTENSIONS)
    itp_files = sorted(p.name for p in file_paths if p.suffix.lower() in _ITP_EXTENSIONS)
    mdp_files = sorted(p.name for p in file_paths if p.suffix.lower() in _MDP_EXTENSIONS)
    index_files = sorted(p.name for p in file_paths if p.suffix.lower() in _INDEX_EXTENSIONS)

    if not structures:
        errors.append("No structure file found (.gro or .pdb required).")

    if not topologies:
        errors.append("No topology file found (.top required).")

    if not mdp_files:
        errors.append("No MD parameter files found (.mdp required).")

    if not itp_files:
        warnings.append(
            "No include topology files (.itp) found; force-field parameters may be "
            "embedded directly in topol.top."
        )

    if not index_files:
        warnings.append("No index file (.ndx) found; GROMACS will use a default group index.")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "files": {
            "structures": structures,
            "topologies": topologies,
            "mdp_files": mdp_files,
            "itp_files": itp_files,
            "index_files": index_files,
        },
    }
