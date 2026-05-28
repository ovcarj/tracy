"""CHARMM-GUI output adapter.

Isolates all assumptions about the structure of CHARMM-GUI output folders.
WorkChain code should call these functions rather than inspecting FolderData
paths directly.

The adapter does not submit AiiDA calculations; it only inspects and transforms
output data.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from aiida import orm


def find_gromacs_directory(folder_data: orm.FolderData) -> str | None:
    """Return the relative path to the GROMACS-ready directory inside a CHARMM-GUI output folder.

    CHARMM-GUI archives typically unpack to a structure such as::

        charmm_gui_job_<id>/
            gromacs/
                step5_input.gro
                topol.top
                toppar/
                    *.itp
                *.mdp

    This function walks the full repository tree and returns the first directory
    whose name is ``gromacs`` (case-insensitive).

    Returns:
        Relative path string (e.g. ``'charmm_gui_job_12345/gromacs'``), or
        ``None`` if no such directory is found.
    """
    for dirpath, _dirnames, _filenames in folder_data.base.repository.walk():
        path_str = str(dirpath)
        if path_str == ".":
            continue
        parts = path_str.split("/")
        if parts[-1].lower() == "gromacs":
            return path_str
    return None


def extract_gromacs_input_bundle(folder_data: orm.FolderData) -> orm.FolderData | None:
    """Create a FolderData containing the files needed for GROMACS MD.

    Locates the GROMACS-ready sub-directory inside the CHARMM-GUI output and
    wraps its contents in a new, **unstored** ``FolderData`` with the GROMACS
    files at the root level.

    Returns:
        Unstored ``FolderData`` whose root contains the GROMACS inputs, or
        ``None`` if no GROMACS directory can be found.
    """
    gromacs_rel = find_gromacs_directory(folder_data)
    if gromacs_rel is None:
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        folder_data.base.repository.copy_tree(tmpdir)
        gromacs_path = Path(tmpdir) / gromacs_rel
        bundle = orm.FolderData()
        bundle.put_object_from_tree(str(gromacs_path))
        return bundle


def collect_charmm_gui_metadata(folder_data: orm.FolderData) -> dict:
    """Return a plain dict with best-effort metadata parsed from the CHARMM-GUI output.

    This function never raises; it returns an empty dict when no structured
    information can be extracted.  The returned dict is safe to merge into
    ``system_metadata`` without further transformation.
    """
    metadata: dict = {}

    top_level = folder_data.list_object_names()
    if len(top_level) == 1:
        job_dir = top_level[0]
        if "job" in job_dir.lower() or job_dir.lower().startswith("charmm"):
            metadata["charmm_gui_job_dir"] = job_dir

    available_engines: list[str] = []
    for dirpath, _dirnames, _filenames in folder_data.base.repository.walk():
        path_str = str(dirpath)
        if path_str == ".":
            continue
        parts = path_str.split("/")
        engine_name = parts[-1].lower()
        if engine_name in {"gromacs", "namd", "amber", "openmm", "charmm"}:
            available_engines.append(engine_name)

    if available_engines:
        metadata["available_md_engines"] = sorted(set(available_engines))

    return metadata
