"""GROMACS log file parser and step quality check calcfunction."""

from __future__ import annotations

import re

from aiida import orm
from aiida.engine import calcfunction


def parse_gromacs_log_summary(log_content: str) -> dict:
    """Extract key statistics from the end of a GROMACS .log file.

    Returns a dict with the following keys (all optional — minimization logs
    lack temperature/pressure averages):
      simulation_time_ps                 — from 'Energy conservation' line (value is in ps;
                                          GROMACS 2021 reports ps but labels the unit as 'ns')
      conserved_energy_drift_kJmolps_per_atom
      n_steps, n_frames                  — from 'Statistics over' line
      avg_temperature_K                  — average from AVERAGES section
      avg_pressure_bar                   — isotropic average
      avg_potential_kJmol
    """
    result: dict = {}

    m = re.search(
        r"Energy conservation over simulation part #\d+ of length ([\d.]+) ns",
        log_content,
    )
    if m:
        result["simulation_time_ps"] = float(m.group(1))

    m = re.search(
        r"Conserved energy drift:\s*([-+]?\d[\d.]*(?:[eE][-+]?\d+)?)\s*kJ/mol/ps per atom",
        log_content,
    )
    if m:
        result["conserved_energy_drift_kJmolps_per_atom"] = float(m.group(1))

    avg_start = log_content.find("A V E R A G E S")
    if avg_start == -1:
        return result

    avg_end = log_content.find("M E G A - F L O P S", avg_start)
    avg_section = log_content[avg_start:avg_end] if avg_end != -1 else log_content[avg_start:]

    m = re.search(r"Statistics over\s+(\d+)\s+steps using\s+(\d+)\s+frames", avg_section)
    if m:
        result["n_steps"] = int(m.group(1))
        result["n_frames"] = int(m.group(2))

    lines = avg_section.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        # "    Temperature Pressure (bar)   Constr. rmsd" header
        if (
            stripped.startswith("Temperature")
            and "Pressure (bar)" in stripped
            and i + 1 < len(lines)
        ):
            values = lines[i + 1].split()
            if len(values) >= 2:
                result["avg_temperature_K"] = float(values[0])
                result["avg_pressure_bar"] = float(values[1])
            break

    for i, line in enumerate(lines):
        stripped = line.strip()
        # "     Dih. Rest.      Potential    Kinetic En.   Total Energy  Conserved En."
        if "Potential" in stripped and "Kinetic En." in stripped and i + 1 < len(lines):
            values = lines[i + 1].split()
            if len(values) >= 2:
                result["avg_potential_kJmol"] = float(values[1])
            break

    return result


@calcfunction
def check_step_quality(log: orm.SinglefileData, protocol: orm.Dict) -> orm.Dict:
    """Parse a GromacsRunWorkChain log and flag potential equilibration issues.

    Checks applied (warnings only — does not abort the workflow):
      - |avg_T - target_T| > 15 K
      - |avg_P| > 500 bar  (generous; membrane NPT has large fluctuations)
      - |conserved_energy_drift| > 0.01 kJ/mol/ps/atom  (standard threshold)

    Returns {"passed": bool, "warnings": [...], "summary": <parse_result>}.
    """
    with log.open(mode="r") as fh:
        content = fh.read()

    summary = parse_gromacs_log_summary(content)
    warnings: list[str] = []

    pconf = protocol.get_dict()
    target_T = (
        pconf.get("charmm_gui", {}).get("quick_bilayer", {}).get("temperature", 310.15)
    )

    if "avg_temperature_K" in summary:
        delta_T = abs(summary["avg_temperature_K"] - target_T)
        if delta_T > 15.0:
            warnings.append(
                f"avg_temperature {summary['avg_temperature_K']:.2f} K deviates "
                f"{delta_T:.1f} K from target {target_T} K"
            )

    if "avg_pressure_bar" in summary:
        if abs(summary["avg_pressure_bar"]) > 500.0:
            warnings.append(
                f"avg_pressure {summary['avg_pressure_bar']:.1f} bar exceeds ±500 bar threshold"
            )

    if "conserved_energy_drift_kJmolps_per_atom" in summary:
        drift = abs(summary["conserved_energy_drift_kJmolps_per_atom"])
        if drift > 0.01:
            warnings.append(
                f"conserved_energy_drift {summary['conserved_energy_drift_kJmolps_per_atom']:.2e} "
                f"kJ/mol/ps/atom exceeds 0.01 threshold"
            )

    return orm.Dict({"passed": len(warnings) == 0, "warnings": warnings, "summary": summary})
