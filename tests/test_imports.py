"""Verify that all public modules import cleanly."""

from __future__ import annotations


def test_import_tracy():
    import tracy

    assert hasattr(tracy, "__version__")
    assert isinstance(tracy.__version__, str)


def test_import_workflows():
    from tracy.workflows import BuildMembraneWorkChain

    assert BuildMembraneWorkChain is not None


def test_import_data_gromacs():
    from tracy.data.gromacs import validate_gromacs_input_bundle

    assert callable(validate_gromacs_input_bundle)


def test_import_adapters_charmm_gui():
    from tracy.adapters.charmm_gui import (
        collect_charmm_gui_metadata,
        extract_gromacs_input_bundle,
        find_gromacs_directory,
    )

    assert callable(find_gromacs_directory)
    assert callable(extract_gromacs_input_bundle)
    assert callable(collect_charmm_gui_metadata)


def test_import_utils():
    from tracy.utils.files import list_all_file_paths
    from tracy.utils.validation import check_protocol_section, require_keys

    assert callable(require_keys)
    assert callable(check_protocol_section)
    assert callable(list_all_file_paths)
