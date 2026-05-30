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
from aiida.engine import calcfunction
from aiida.plugins import CalculationFactory

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
        topology   — SinglefileData (.top)
        toppar     — FolderData    (toppar/ directory)
        index      — SinglefileData (.ndx), only if present

    Files are discovered by extension rather than hardcoded names, except for
    the toppar/ directory whose name is load-bearing (referenced by topol.top
    #include paths and must match the remote directory created by grompp).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        bundle.base.repository.copy_tree(tmpdir)
        root = Path(tmpdir)

        result: dict = {
            "structure": orm.SinglefileData(file=str(_find_unique(root, "*.gro", "input structure"))),
            "topology":  orm.SinglefileData(file=str(_find_unique(root, "*.top", "topology file"))),
        }

        toppar_dir = root / "toppar"
        if not toppar_dir.is_dir():
            raise ValueError(
                "No 'toppar/' directory found in bundle. "
                "The directory name is required to match the #include paths in topol.top."
            )
        toppar = orm.FolderData()
        toppar.put_object_from_tree(str(toppar_dir))
        result["toppar"] = toppar

        ndx_files = sorted(p for p in root.glob("*.ndx") if p.is_file())
        if len(ndx_files) > 1:
            raise ValueError(f"Multiple .ndx files found in bundle: {[f.name for f in ndx_files]}")
        if ndx_files:
            result["index"] = orm.SinglefileData(file=str(ndx_files[0]))

        return result


def _find_unique(root: Path, pattern: str, description: str) -> Path:
    """Return the single file in *root* matching *pattern*, or raise ValueError."""
    matches = sorted(p for p in root.glob(pattern) if p.is_file())
    if not matches:
        raise ValueError(f"No {description} ({pattern}) found in bundle.")
    if len(matches) > 1:
        raise ValueError(
            f"Multiple {description} files found in bundle: {[f.name for f in matches]}. "
            "Expected exactly one."
        )
    return matches[0]


# ---------------------------------------------------------------------------
# MDP utilities
# ---------------------------------------------------------------------------

def read_mdp_param(mdp_file: orm.SinglefileData, key: str, default: str = "") -> str:
    """Return the value of a single MDP key, or *default* if not found.

    Key matching is case-insensitive and treats hyphens and underscores as
    equivalent (GROMACS accepts both).
    """
    key_norm = key.strip().lower().replace("-", "_")
    with mdp_file.open(mode="r") as fh:
        for line in fh:
            code = line.split(";")[0]
            if "=" not in code:
                continue
            k, _, v = code.partition("=")
            if k.strip().lower().replace("-", "_") == key_norm:
                return v.strip()
    return default


def _apply_mdp_overrides(content: str, overrides: dict) -> str:
    """Return MDP content with key-value pairs replaced or appended."""
    lines = content.splitlines()
    patched: list[str] = []
    applied: set[str] = set()

    for line in lines:
        comment_pos = line.find(";")
        code = line[:comment_pos] if comment_pos >= 0 else line
        tail = line[comment_pos:] if comment_pos >= 0 else ""

        if "=" in code:
            raw_key = code.split("=")[0].strip()
            key_norm = raw_key.lower().replace("-", "_")
            for ov_key, ov_val in overrides.items():
                if ov_key.lower().replace("-", "_") == key_norm:
                    patched.append(f"{raw_key} = {ov_val}{tail}")
                    applied.add(ov_key)
                    break
            else:
                patched.append(line)
        else:
            patched.append(line)

    for key, val in overrides.items():
        if key not in applied:
            patched.append(f"{key} = {val}")

    return "\n".join(patched)


@calcfunction
def patch_mdp(mdp_file: orm.SinglefileData, overrides: orm.Dict) -> orm.SinglefileData:
    """Apply key-value overrides to a GROMACS MDP file, preserving provenance.

    Keys are matched case-insensitively with hyphens/underscores treated as
    equivalent.  Existing keys have their values replaced; keys not present in
    the original are appended at the end.
    """
    import io
    with mdp_file.open(mode="r") as fh:
        content = fh.read()
    patched = _apply_mdp_overrides(content, overrides.get_dict())
    return orm.SinglefileData(io.BytesIO(patched.encode()), filename=mdp_file.filename)
