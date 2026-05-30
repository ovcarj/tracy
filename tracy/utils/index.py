"""Index file utilities."""

from __future__ import annotations

import io

from aiida import orm
from aiida.engine import calcfunction


@calcfunction
def merge_index_files(base_ndx: orm.SinglefileData,
                      new_ndx: orm.SinglefileData) -> orm.SinglefileData:
    """Append the groups from *new_ndx* to *base_ndx*, preserving all originals.

    The GROMACS index format is plain text:
        [ group_name ]
        atom_idx_1 atom_idx_2 ...

    Returns a new SinglefileData with the combined content.
    """
    with base_ndx.open(mode="r") as fh:
        base_content = fh.read()
    with new_ndx.open(mode="r") as fh:
        new_content = fh.read()

    combined = base_content.rstrip("\n") + "\n" + new_content
    return orm.SinglefileData(io.BytesIO(combined.encode()), filename="index.ndx")
