"""GROMACS adapter.

Isolates all knowledge about the structure of a CHARMM-GUI GROMACS bundle.
WorkChain code should call these functions rather than inspecting FolderData
paths directly.
"""

from __future__ import annotations

import re
import tempfile
from collections import defaultdict
from pathlib import Path

from aiida import orm

_MDP_RE = re.compile(r"^step(\d+)(?:\.(\d+))?_([^.]+)\.mdp$")


def build_step_manifest(bundle: orm.FolderData | Path) -> list[dict]:
    """Parse a CHARMM-GUI GROMACS bundle and return an ordered list of steps.

    Each entry in the list:

        {
            "name":    "minimization",          # from MDP filename
            "order":   0,                       # 0-indexed run order
            "mdp":     "step6.0_minimization.mdp",
            "step_id": "step6.0",               # prefix for naming output files
        }

    Raises ValueError if no MDP files are found or the sequence has gaps.
    """
    if isinstance(bundle, orm.FolderData):
        filenames = bundle.list_object_names()
    elif isinstance(bundle, Path):
        filenames = [p.name for p in bundle.iterdir() if p.is_file()]
    else:
        raise TypeError(f"Expected FolderData or Path, got {type(bundle).__name__}")

    parsed = []
    for filename in filenames:
        m = _MDP_RE.match(filename)
        if m is None:
            continue
        major = int(m.group(1))
        minor = int(m.group(2)) if m.group(2) is not None else None
        name = m.group(3)
        parsed.append({"name": name, "major": major, "minor": minor, "mdp": filename})

    if not parsed:
        raise ValueError(
            "No MDP files matching the CHARMM-GUI step naming convention "
            "(step<N>[.<M>]_<name>.mdp) were found in the bundle."
        )

    parsed.sort(key=lambda s: (s["major"], s["minor"] if s["minor"] is not None else float("inf")))
    _validate_step_sequence(parsed)

    return [
        {
            "name": s["name"],
            "order": i,
            "mdp": s["mdp"],
            "step_id": f"step{s['major']}" + (f".{s['minor']}" if s["minor"] is not None else ""),
        }
        for i, s in enumerate(parsed)
    ]


def _validate_step_sequence(steps: list[dict]) -> None:
    """Raise ValueError if minor step numbers within a major are non-consecutive."""
    by_major: dict[int, list[int]] = defaultdict(list)
    for step in steps:
        if step["minor"] is not None:
            by_major[step["major"]].append(step["minor"])

    for major, minors in sorted(by_major.items()):
        minors_sorted = sorted(minors)
        expected = list(range(len(minors_sorted)))
        if minors_sorted != expected:
            raise ValueError(
                f"Step sequence for step{major} has gaps: "
                f"found minors {minors_sorted}, expected {expected}."
            )


def prepare_gromacs_run_inputs(bundle: orm.FolderData) -> dict:
    """Extract typed AiiDA nodes from a CHARMM-GUI GROMACS bundle.

    Returns a dict with keys:
        structure  — SinglefileData (.gro)
        topology   — SinglefileData (topol.top)
        toppar     — FolderData    (toppar/ directory)
        index      — SinglefileData (.ndx), only if present

    These map directly to GromacsRunWorkChain inputs.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        bundle.base.repository.copy_tree(tmpdir)
        root = Path(tmpdir)

        result: dict = {
            "structure": orm.SinglefileData(file=str(root / "step5_input.gro")),
            "topology": orm.SinglefileData(file=str(root / "topol.top")),
        }

        toppar = orm.FolderData()
        toppar.put_object_from_tree(str(root / "toppar"))
        result["toppar"] = toppar

        ndx = root / "index.ndx"
        if ndx.exists():
            result["index"] = orm.SinglefileData(file=str(ndx))

        return result
