"""General-purpose validation utilities."""

from __future__ import annotations


def require_keys(d: dict, keys: list[str], label: str = "dict") -> list[str]:
    """Return a list of error strings for any required keys missing from *d*."""
    return [f"Missing required key {k!r} in {label}." for k in keys if k not in d]


def check_protocol_section(protocol: dict, section: str, required_keys: list[str]) -> list[str]:
    """Return errors if *section* is absent from *protocol* or is missing required keys."""
    if section not in protocol:
        return [f"Protocol is missing the '{section}' section."]
    return require_keys(protocol[section], required_keys, label=f"protocol['{section}']")
