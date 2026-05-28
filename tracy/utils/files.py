"""File and repository utilities."""

from __future__ import annotations


def list_all_file_paths(folder_data: "orm.FolderData") -> list[str]:
    """Return all relative file paths stored in a FolderData.

    Returns paths using forward slashes, with no leading slash.
    Directories are not included.
    """
    paths: list[str] = []
    for dirpath, _dirnames, filenames in folder_data.base.repository.walk():
        path_str = str(dirpath)
        for fname in filenames:
            if path_str == ".":
                paths.append(fname)
            else:
                paths.append(f"{path_str}/{fname}")
    return sorted(paths)
