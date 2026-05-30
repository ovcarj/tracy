"""GromacsRunWorkChain: one grompp + mdrun pair."""

from __future__ import annotations

from pathlib import Path

from aiida import orm
from aiida.engine import ExitCode, ToContext, WorkChain
from aiida.plugins import CalculationFactory, DataFactory


class GromacsRunWorkChain(WorkChain):
    """Run a single GROMACS grompp + mdrun pair.

    Generic and reusable — knows nothing about membranes or CHARMM-GUI.
    Output filenames are prefixed with ``output_prefix`` (defaults to the MDP
    file stem) so stored nodes are identifiable in the AiiDA provenance graph.

    Inputs
    ------
    structure     : SinglefileData  — input .gro structure
    topology      : SinglefileData  — topol.top
    toppar        : FolderData      — toppar/ force-field directory
    mdp_file      : SinglefileData  — .mdp parameter file
    index_file    : SinglefileData  — .ndx index file (optional)
    checkpoint    : SinglefileData  — .cpt continuation checkpoint (optional)
    gromacs_code  : AbstractCode    — registered gmx code
    options       : Dict            — scheduler resource options (optional)
    output_prefix : Str             — filename prefix for outputs (optional)

    Outputs
    -------
    output_structure     : SinglefileData — .gro from mdrun
    trajectory           : SinglefileData — .trr from mdrun
    energy               : SinglefileData — .edr from mdrun
    log                  : SinglefileData — .log from mdrun
    tpr_file             : SinglefileData — .tpr from grompp
    trajectory_compressed: SinglefileData — .xtc when nstxout-compressed > 0 (optional)
    checkpoint           : SinglefileData — .cpt for dynamics steps (optional)
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)

        spec.input("structure",    valid_type=orm.SinglefileData)
        spec.input("topology",     valid_type=orm.SinglefileData)
        spec.input("toppar",       valid_type=orm.FolderData)
        spec.input("mdp_file",     valid_type=orm.SinglefileData)
        spec.input("index_file",    valid_type=orm.SinglefileData, required=False)
        spec.input("checkpoint",    valid_type=orm.SinglefileData, required=False)
        spec.input("gromacs_code",  valid_type=orm.AbstractCode)
        spec.input("options",       valid_type=orm.Dict, required=False)
        spec.input("output_prefix", valid_type=orm.Str,  required=False,
                   help="Prefix for output filenames. Defaults to the MDP file stem.")

        spec.outline(
            cls.setup,
            cls.run_grompp,
            cls.run_mdrun,
            cls.results,
        )

        spec.output("output_structure",      valid_type=orm.SinglefileData)
        spec.output("trajectory",            valid_type=orm.SinglefileData, required=False)
        spec.output("energy",                valid_type=orm.SinglefileData)
        spec.output("log",                   valid_type=orm.SinglefileData)
        spec.output("tpr_file",              valid_type=orm.SinglefileData)
        spec.output("trajectory_compressed", valid_type=orm.SinglefileData, required=False)
        spec.output("checkpoint",            valid_type=orm.SinglefileData, required=False)

        spec.exit_code(300, "ERROR_GROMPP_FAILED", message="grompp calculation failed.")
        spec.exit_code(301, "ERROR_MDRUN_FAILED",  message="mdrun calculation failed.")

    def setup(self) -> None:
        from tracy.adapters.gromacs import read_mdp_param
        GromppParameters = DataFactory("gromacs.grompp")
        MdrunParameters  = DataFactory("gromacs.mdrun")

        mdp_stem = Path(self.inputs.mdp_file.filename).stem
        prefix = self.inputs.output_prefix.value if "output_prefix" in self.inputs else mdp_stem
        self.ctx.step_stem = prefix

        integrator = read_mdp_param(self.inputs.mdp_file, "integrator", default="md").lower()
        is_minimization = integrator in {"steep", "cg", "l-bfgs"}
        nstxtc = int(read_mdp_param(self.inputs.mdp_file, "nstxout-compressed", default="0"))

        self.ctx.write_cpt = not is_minimization
        self.ctx.write_xtc = nstxtc > 0

        self.ctx.grompp_params = GromppParameters(dict={"o": f"{prefix}.tpr"})

        mdrun_dict = {
            "c": f"{prefix}.gro",
            "e": f"{prefix}.edr",
            "g": f"{prefix}.log",
            "o": f"{prefix}.trr",
        }
        if self.ctx.write_cpt:
            mdrun_dict["cpo"] = f"{prefix}.cpt"
        if self.ctx.write_xtc:
            mdrun_dict["x"] = f"{prefix}.xtc"

        self.ctx.mdrun_params = MdrunParameters(dict=mdrun_dict)
        self.report(f"GromacsRunWorkChain setup: step={prefix}, minimization={is_minimization}, xtc={self.ctx.write_xtc}")

    def run_grompp(self):
        GromppCalculation = CalculationFactory("gromacs.grompp")

        inputs = {
            "code":       self.inputs.gromacs_code,
            "mdpfile":    self.inputs.mdp_file,
            "grofile":    self.inputs.structure,
            "topfile":    self.inputs.topology,
            "r_file":     self.inputs.structure,
            "parameters": self.ctx.grompp_params,
            "itp_dirs":   {"toppar": self.inputs.toppar},
        }
        if "index_file" in self.inputs:
            inputs["n_file"] = self.inputs.index_file
        if "options" in self.inputs:
            # grompp is always serial; strip withmpi regardless of what options says
            grompp_options = {**self.inputs.options.get_dict(), "withmpi": False}
            inputs["metadata"] = {"options": grompp_options}

        calc = self.submit(GromppCalculation, **inputs)
        self.report(f"Submitted GromppCalculation (pk={calc.pk})")
        return ToContext(grompp=calc)

    def run_mdrun(self) -> ExitCode | None:
        if not self.ctx.grompp.is_finished_ok:
            self.report(f"grompp failed with exit status {self.ctx.grompp.exit_status}")
            return self.exit_codes.ERROR_GROMPP_FAILED

        MdrunCalculation = CalculationFactory("gromacs.mdrun")

        inputs = {
            "code":       self.inputs.gromacs_code,
            "tprfile":    self.ctx.grompp.outputs.tprfile,
            "parameters": self.ctx.mdrun_params,
        }
        if "checkpoint" in self.inputs:
            inputs["cpi_file"] = self.inputs.checkpoint
        if "index_file" in self.inputs:
            inputs["mn_file"] = self.inputs.index_file
        if "options" in self.inputs:
            inputs["metadata"] = {"options": self.inputs.options.get_dict()}

        calc = self.submit(MdrunCalculation, **inputs)
        self.report(f"Submitted MdrunCalculation (pk={calc.pk})")
        return ToContext(mdrun=calc)

    def results(self) -> ExitCode | None:
        if not self.ctx.mdrun.is_finished_ok:
            self.report(f"mdrun failed with exit status {self.ctx.mdrun.exit_status}")
            return self.exit_codes.ERROR_MDRUN_FAILED

        self.out("output_structure", self.ctx.mdrun.outputs.grofile)
        if "trrfile" in self.ctx.mdrun.outputs:
            self.out("trajectory", self.ctx.mdrun.outputs.trrfile)
        self.out("energy",           self.ctx.mdrun.outputs.enfile)
        self.out("log",              self.ctx.mdrun.outputs.logfile)
        self.out("tpr_file",         self.ctx.grompp.outputs.tprfile)

        if self.ctx.write_xtc and "x_file" in self.ctx.mdrun.outputs:
            self.out("trajectory_compressed", self.ctx.mdrun.outputs.x_file)
        if self.ctx.write_cpt and "cpo_file" in self.ctx.mdrun.outputs:
            self.out("checkpoint", self.ctx.mdrun.outputs.cpo_file)

        self.report(f"GromacsRunWorkChain finished: {self.ctx.step_stem}")
