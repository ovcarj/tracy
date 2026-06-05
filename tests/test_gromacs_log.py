"""Tests for the GROMACS log parser and step quality check.

Pure-function tests require no AiiDA profile.
"""

from __future__ import annotations

import pytest

from tracy.calculations.gromacs_log import parse_gromacs_log_summary


# ---------------------------------------------------------------------------
# Synthetic log snippets
# ---------------------------------------------------------------------------

_MD_LOG_AVERAGES = """\
Energy conservation over simulation part #1 of length 100 ns, time 0 to 100000 ns
  Conserved energy drift: -2.50e-03 kJ/mol/ps per atom


\t<======  ###############  ==>
\t<====  A V E R A G E S  ====>
\t<==  ###############  ======>

\tStatistics over 100001 steps using 1001 frames

   Energies (kJ/mol)
           Bond            U-B    Proper Dih.  Improper Dih.          LJ-14
    2.79495e+03    1.50888e+04    1.11247e+04    1.18174e+02    1.92479e+03
     Coulomb-14        LJ (SR)   Coulomb (SR)   Coul. recip. Position Rest.
    1.14054e+04   -2.23970e+02   -1.32254e+05    6.65669e+02    8.36837e+01
     Dih. Rest.      Potential    Kinetic En.   Total Energy  Conserved En.
    1.29145e+02   -8.91425e+04    3.50780e+04   -5.40645e+04   -6.48715e+04
    Temperature Pressure (bar)   Constr. rmsd
    3.10237e+02   -8.61505e+02    0.00000e+00

\tM E G A - F L O P S   A C C O U N T I N G
"""

_MINIMIZATION_LOG = """\
           Bond            U-B    Proper Dih.
    5.18030e+02    8.00375e+03    1.13357e+04
     Dih. Rest.      Potential Pressure (bar)   Constr. rmsd
    3.65659e+01   -9.46259e+04    1.49822e+04    0.00000e+00
"""


# ---------------------------------------------------------------------------
# parse_gromacs_log_summary
# ---------------------------------------------------------------------------


def test_parse_simulation_time():
    result = parse_gromacs_log_summary(_MD_LOG_AVERAGES)
    assert abs(result["simulation_time_ps"] - 100.0) < 1e-9


def test_parse_simulation_time_scientific_notation():
    # GROMACS 2021 uses 1e+06 for long runs (1 μs)
    log = "Energy conservation over simulation part #1 of length 1e+06 ns, time 0 to 1e+06 ns\n"
    result = parse_gromacs_log_summary(log)
    assert abs(result["simulation_time_ps"] - 1e6) < 1.0


def test_parse_conserved_energy_drift():
    result = parse_gromacs_log_summary(_MD_LOG_AVERAGES)
    assert abs(result["conserved_energy_drift_kJmolps_per_atom"] - (-2.50e-3)) < 1e-9


def test_parse_n_steps_and_frames():
    result = parse_gromacs_log_summary(_MD_LOG_AVERAGES)
    assert result["n_steps"] == 100001
    assert result["n_frames"] == 1001


def test_parse_avg_temperature():
    result = parse_gromacs_log_summary(_MD_LOG_AVERAGES)
    assert abs(result["avg_temperature_K"] - 310.237) < 1e-3


def test_parse_avg_pressure():
    result = parse_gromacs_log_summary(_MD_LOG_AVERAGES)
    assert abs(result["avg_pressure_bar"] - (-861.505)) < 1e-2


def test_parse_avg_potential():
    result = parse_gromacs_log_summary(_MD_LOG_AVERAGES)
    assert abs(result["avg_potential_kJmol"] - (-89142.5)) < 1.0


def test_minimization_log_returns_empty_summary():
    result = parse_gromacs_log_summary(_MINIMIZATION_LOG)
    assert "avg_temperature_K" not in result
    assert "avg_pressure_bar" not in result
    assert "n_steps" not in result


def test_minimization_log_has_no_averages_section():
    result = parse_gromacs_log_summary(_MINIMIZATION_LOG)
    assert result == {}


# ---------------------------------------------------------------------------
# check_step_quality (requires AiiDA profile for calcfunction)
# ---------------------------------------------------------------------------


def test_quality_check_passes_for_good_md(aiida_profile):
    import io
    from aiida import orm
    from tracy.calculations.gromacs_log import check_step_quality

    log = orm.SinglefileData(io.BytesIO(_MD_LOG_AVERAGES.encode()), filename="test.log")
    log.store()

    # Target T = 310.15 K, avg is 310.237 K → within 15 K; drift -2.5e-3 > 0.01 threshold
    protocol = orm.Dict({"charmm_gui": {"quick_bilayer": {"temperature": 310.15}}})
    protocol.store()

    result = check_step_quality(log, protocol)
    d = result.get_dict()
    assert "passed" in d
    assert "warnings" in d
    assert "summary" in d
    # Pressure -861 bar exceeds ±500 bar threshold → should warn; drift -2.5e-3 < 0.01 → fine
    assert not d["passed"]
    assert any("pressure" in w.lower() for w in d["warnings"])


def test_quality_check_minimization_passes(aiida_profile):
    import io
    from aiida import orm
    from tracy.calculations.gromacs_log import check_step_quality

    log = orm.SinglefileData(io.BytesIO(_MINIMIZATION_LOG.encode()), filename="min.log")
    log.store()
    protocol = orm.Dict({})
    protocol.store()

    result = check_step_quality(log, protocol)
    d = result.get_dict()
    assert d["passed"] is True
    assert d["warnings"] == []
