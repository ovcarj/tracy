"""MembraneElectrostaticsWorkChain: end-to-end membrane pipeline.

Chains BuildMembraneWorkChain → RunMembraneMDWorkChain →
ComputeMembranePotentialWorkChain in one daemon-managed submission.

A single unified protocol dict is passed to all three sub-WorkChains;
each reads the keys it needs and ignores the rest.

Optional skip inputs allow re-entry at any stage:
  - ``gromacs_input_bundle`` provided → skip CHARMM-GUI build
  - ``tpr_file`` + ``trajectory_compressed`` provided → skip MD entirely
"""

from __future__ import annotations

from aiida import orm
from aiida.engine import ExitCode, ToContext, WorkChain, if_


class MembraneElectrostaticsWorkChain(WorkChain):
    """Build membrane, run MD, compute φ(z) — in one submission.

    Inputs
    ------
    protocol              : Dict           — unified protocol (all stages)
    code                  : AbstractCode   — GROMACS code
    options               : Dict           — scheduler options for MD calcs (optional)
    analysis_options      : Dict           — scheduler options for lightweight analysis calcs
                                             (trjconv, gmx select, gmx potential); overrides
                                             ``options`` for those calcs.  Use this to avoid
                                             queuing minutes-long analysis jobs behind days-long
                                             production runs.  If omitted, ``options`` is used
                                             for all stages.
    gromacs_input_bundle  : FolderData     — skip CHARMM-GUI build (optional)
    tpr_file              : SinglefileData — skip MD; supply with trajectory_compressed (optional)
    trajectory_compressed : SinglefileData — skip MD; supply with tpr_file (optional)
    index_file            : SinglefileData — .ndx override for potential step (optional)

    Outputs
    -------
    gromacs_input_bundle  : FolderData        — only when built by this WorkChain
    md_report             : Dict              — only when MD was run
    potential_profile     : SinglefileData    — total φ(z) .xvg
    potential_report      : Dict              — analysis metadata
    potential_components  : namespace         — per-component .xvg files (dynamic)
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)

        spec.input("protocol",              valid_type=orm.Dict)
        spec.input("code",                  valid_type=orm.AbstractCode)
        spec.input("options",               valid_type=orm.Dict,            required=False)
        spec.input("analysis_options",      valid_type=orm.Dict,            required=False,
                   help="Scheduler options for lightweight analysis calcs (trjconv, gmx select, "
                        "gmx potential).  Overrides 'options' for those calcs so they can run on "
                        "a short-walltime queue or with fewer MPI ranks than the MD job.")
        spec.input("gromacs_input_bundle",  valid_type=orm.FolderData,      required=False)
        spec.input("tpr_file",              valid_type=orm.SinglefileData,  required=False)
        spec.input("trajectory_compressed", valid_type=orm.SinglefileData,  required=False)
        spec.input("index_file",            valid_type=orm.SinglefileData,  required=False)

        spec.outline(
            cls.setup,
            if_(cls.should_build)(
                cls.run_build,
                cls.inspect_build,
            ),
            if_(cls.should_run_md)(
                cls.run_md,
                cls.inspect_md,
            ),
            cls.run_potential,
            cls.inspect_potential,
            cls.results,
        )

        spec.output("gromacs_input_bundle",  valid_type=orm.FolderData,     required=False)
        spec.output("md_report",             valid_type=orm.Dict,           required=False)
        spec.output("potential_profile",     valid_type=orm.SinglefileData)
        spec.output("potential_report",      valid_type=orm.Dict)
        spec.output_namespace("potential_components", valid_type=orm.SinglefileData,
                               required=False, dynamic=True)

        spec.exit_code(510, "ERROR_BUILD_FAILED",
                       message="BuildMembraneWorkChain failed.")
        spec.exit_code(511, "ERROR_MD_FAILED",
                       message="RunMembraneMDWorkChain failed.")
        spec.exit_code(512, "ERROR_POTENTIAL_FAILED",
                       message="ComputeMembranePotentialWorkChain failed.")
        spec.exit_code(513, "ERROR_NO_TRAJECTORY",
                       message="Production step has no trajectory_compressed output. "
                               "Set nstxout-compressed > 0 in the production MDP override.")

    # -------------------------------------------------------------------------
    # Predicates
    # -------------------------------------------------------------------------

    def setup(self) -> None:
        protocol = self.inputs.protocol.get_dict()
        self.ctx.protocol = protocol
        self.report(
            f"MembraneElectrostaticsWorkChain starting. "
            f"build={'skip' if 'gromacs_input_bundle' in self.inputs else 'yes'}, "
            f"md={'skip' if 'trajectory_compressed' in self.inputs else 'yes'}"
        )

    def should_build(self) -> bool:
        return "gromacs_input_bundle" not in self.inputs

    def should_run_md(self) -> bool:
        return "trajectory_compressed" not in self.inputs

    # -------------------------------------------------------------------------
    # Stage 1: CHARMM-GUI membrane build
    # -------------------------------------------------------------------------

    def run_build(self):
        from tracy.workflows.membrane_builder import BuildMembraneWorkChain
        wc = self.submit(BuildMembraneWorkChain, protocol=self.inputs.protocol)
        self.report(f"Submitted BuildMembraneWorkChain pk={wc.pk}")
        return ToContext(build_wc=wc)

    def inspect_build(self) -> ExitCode | None:
        wc = self.ctx.build_wc
        if not wc.is_finished_ok:
            self.report(f"BuildMembraneWorkChain failed (exit {wc.exit_status})")
            return self.exit_codes.ERROR_BUILD_FAILED
        self.ctx.gromacs_input_bundle = wc.outputs.gromacs_input_bundle
        self.out("gromacs_input_bundle", wc.outputs.gromacs_input_bundle)
        self.report("BuildMembraneWorkChain finished OK.")

    # -------------------------------------------------------------------------
    # Stage 2: GROMACS MD
    # -------------------------------------------------------------------------

    def run_md(self):
        from tracy.workflows.membrane_md import RunMembraneMDWorkChain

        if "gromacs_input_bundle" in self.inputs:
            bundle = self.inputs.gromacs_input_bundle
        else:
            bundle = self.ctx.gromacs_input_bundle

        inputs = {
            "md_input_bundle": bundle,
            "protocol":        self.inputs.protocol,
            "code":            self.inputs.code,
        }
        if "options" in self.inputs:
            inputs["options"] = self.inputs.options

        wc = self.submit(RunMembraneMDWorkChain, **inputs)
        self.report(f"Submitted RunMembraneMDWorkChain pk={wc.pk}")
        return ToContext(md_wc=wc)

    def inspect_md(self) -> ExitCode | None:
        wc = self.ctx.md_wc
        if not wc.is_finished_ok:
            self.report(f"RunMembraneMDWorkChain failed (exit {wc.exit_status})")
            if hasattr(wc.outputs, "md_report"):
                self.out("md_report", wc.outputs.md_report)
            return self.exit_codes.ERROR_MD_FAILED

        self.out("md_report", wc.outputs.md_report)

        # Log quality warnings from any step (quality check runs inline in RunMembraneMDWorkChain)
        report = wc.outputs.md_report.get_dict()
        for step in report.get("steps_run", []):
            quality = step.get("quality", {})
            if quality and not quality.get("passed", True):
                for w in quality.get("warnings", []):
                    self.report(f"MD quality warning [{step['name']}]: {w}")

        # Find the production (last completed) GromacsRunWorkChain.
        report = wc.outputs.md_report.get_dict()
        production_pk = report["steps_run"][-1]["pk"]
        prod_wc = orm.load_node(production_pk)

        if not hasattr(prod_wc.outputs, "trajectory_compressed"):
            self.report(
                "Production GromacsRunWorkChain has no trajectory_compressed output. "
                "Add nstxout-compressed > 0 to the production MDP override."
            )
            return self.exit_codes.ERROR_NO_TRAJECTORY

        self.ctx.tpr_file              = prod_wc.outputs.tpr_file
        self.ctx.trajectory_compressed = prod_wc.outputs.trajectory_compressed

        # Propagate the index file: explicit input wins, then production step input.
        if "index_file" in self.inputs:
            self.ctx.index_file = self.inputs.index_file
        else:
            index_file = getattr(prod_wc.inputs, "index_file", None)
            if index_file is not None:
                self.ctx.index_file = index_file

        self.report(
            f"RunMembraneMDWorkChain finished OK. "
            f"Production step pk={production_pk}."
        )

    # -------------------------------------------------------------------------
    # Stage 3: electrostatic potential
    # -------------------------------------------------------------------------

    def run_potential(self):
        from tracy.workflows.electrostatics import ComputeMembranePotentialWorkChain

        if "tpr_file" in self.inputs:
            tpr_file              = self.inputs.tpr_file
            trajectory_compressed = self.inputs.trajectory_compressed
        else:
            tpr_file              = self.ctx.tpr_file
            trajectory_compressed = self.ctx.trajectory_compressed

        inputs = {
            "tpr_file":              tpr_file,
            "trajectory_compressed": trajectory_compressed,
            "protocol":              self.inputs.protocol,
            "code":                  self.inputs.code,
        }
        if "analysis_options" in self.inputs:
            inputs["analysis_options"] = self.inputs.analysis_options
        elif "options" in self.inputs:
            inputs["options"] = self.inputs.options

        index_file = getattr(self.ctx, "index_file", None)
        if index_file is None and "index_file" in self.inputs:
            index_file = self.inputs.index_file
        if index_file is not None:
            inputs["index_file"] = index_file

        if hasattr(self.ctx, "md_wc") and hasattr(self.ctx.md_wc.outputs, "md_report"):
            inputs["md_report"] = self.ctx.md_wc.outputs.md_report

        wc = self.submit(ComputeMembranePotentialWorkChain, **inputs)
        self.report(f"Submitted ComputeMembranePotentialWorkChain pk={wc.pk}")
        return ToContext(potential_wc=wc)

    def inspect_potential(self) -> ExitCode | None:
        wc = self.ctx.potential_wc
        if not wc.is_finished_ok:
            self.report(f"ComputeMembranePotentialWorkChain failed (exit {wc.exit_status})")
            return self.exit_codes.ERROR_POTENTIAL_FAILED
        self.report("ComputeMembranePotentialWorkChain finished OK.")

    # -------------------------------------------------------------------------
    # Collect outputs
    # -------------------------------------------------------------------------

    def results(self) -> None:
        wc = self.ctx.potential_wc
        self.out("potential_profile", wc.outputs.potential_profile)
        self.out("potential_report",  wc.outputs.potential_report)
        if hasattr(wc.outputs, "potential_components"):
            for label, node in wc.outputs.potential_components.items():
                self.out(f"potential_components.{label}", node)
        self.report("MembraneElectrostaticsWorkChain finished successfully.")
