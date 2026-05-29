"""GromacsRunWorkChain: one grompp + mdrun pair."""

from __future__ import annotations

from pathlib import Path

from aiida import orm
from aiida.engine import ExitCode, ToContext, WorkChain
from aiida.plugins import CalculationFactory, DataFactory


class GromacsRunWorkChain(WorkChain):
    """Run a single GROMACS grompp + mdrun pair.

    Generic and reusable — knows nothing about membranes or CHARMM-GUI.
    Output filenames are derived from the MDP stem so stored nodes are
    identifiable in the AiiDA provenance graph.

    Inputs
    ------
    structure    : SinglefileData  — input .gro structure
    topology     : SinglefileData  — topol.top
    toppar       : FolderData      — toppar/ force-field directory
    mdp_file     : SinglefileData  — .mdp parameter file
    index_file   : SinglefileData  — .ndx index file (optional)
    checkpoint   : SinglefileData  — .cpt continuation checkpoint (optional)
    gromacs_code : AbstractCode    — registered gmx code
    options      : Dict            — scheduler resource options (optional)

    Outputs
    -------
    output_structure : SinglefileData — .gro from mdrun
    trajectory       : SinglefileData — .trr from mdrun
    energy           : SinglefileData — .edr from mdrun
    log              : SinglefileData — .log from mdrun
    checkpoint       : SinglefileData — .cpt from mdrun (optional)
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)

        spec.input("structure",    valid_type=orm.SinglefileData)
        spec.input("topology",     valid_type=orm.SinglefileData)
        spec.input("toppar",       valid_type=orm.FolderData)
        spec.input("mdp_file",     valid_type=orm.SinglefileData)
        spec.input("index_file",   valid_type=orm.SinglefileData, required=False)
        spec.input("checkpoint",   valid_type=orm.SinglefileData, required=False)
        spec.input("gromacs_code", valid_type=orm.AbstractCode)
        spec.input("options",      valid_type=orm.Dict, required=False)

        spec.outline(
            cls.setup,
            cls.run_grompp,
            cls.run_mdrun,
            cls.results,
        )

        spec.output("output_structure", valid_type=orm.SinglefileData)
        spec.output("trajectory",       valid_type=orm.SinglefileData)
        spec.output("energy",           valid_type=orm.SinglefileData)
        spec.output("log",              valid_type=orm.SinglefileData)
        spec.output("checkpoint",       valid_type=orm.SinglefileData, required=False)

        spec.exit_code(300, "ERROR_GROMPP_FAILED", message="grompp calculation failed.")
        spec.exit_code(301, "ERROR_MDRUN_FAILED",  message="mdrun calculation failed.")

    def setup(self) -> None:
        GromppParameters = DataFactory("gromacs.grompp")
        MdrunParameters  = DataFactory("gromacs.mdrun")

        stem = Path(self.inputs.mdp_file.filename).stem
        self.ctx.step_stem = stem

        self.ctx.grompp_params = GromppParameters(dict={"o": f"{stem}.tpr"})
        self.ctx.mdrun_params = MdrunParameters(dict={
            "c":   f"{stem}_out.gro",
            "e":   f"{stem}.edr",
            "g":   f"{stem}.log",
            "o":   f"{stem}.trr",
            "cpo": f"{stem}.cpt",
        })
        self.report(f"GromacsRunWorkChain setup: step={stem}")

    def run_grompp(self):
        GromppCalculation = CalculationFactory("gromacs.grompp")

        inputs = {
            "code":       self.inputs.gromacs_code,
            "mdpfile":    self.inputs.mdp_file,
            "grofile":    self.inputs.structure,
            "topfile":    self.inputs.topology,
            "parameters": self.ctx.grompp_params,
            "itp_dirs":   {"toppar": self.inputs.toppar},
        }
        if "index_file" in self.inputs:
            inputs["n_file"] = self.inputs.index_file
        if "options" in self.inputs:
            inputs["metadata"] = {"options": self.inputs.options.get_dict()}

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
        self.out("trajectory",       self.ctx.mdrun.outputs.trrfile)
        self.out("energy",           self.ctx.mdrun.outputs.enfile)
        self.out("log",              self.ctx.mdrun.outputs.logfile)

        if "cpo_file" in self.ctx.mdrun.outputs:
            self.out("checkpoint", self.ctx.mdrun.outputs.cpo_file)

        self.report(f"GromacsRunWorkChain finished: {self.ctx.step_stem}")
