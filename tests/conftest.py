"""Shared pytest fixtures for tracy tests."""

import pytest


@pytest.fixture(scope="session", autouse=True)
def aiida_profile():
    """Load the default AiiDA profile for all tests that need ORM access."""
    from aiida.manage import load_profile

    load_profile()
