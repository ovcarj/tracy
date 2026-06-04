"""ComputeMembranePotentialWorkChain: trajectory preprocessing → gmx potential."""

from __future__ import annotations

import re

from aiida import orm
from aiida.engine import ExitCode, ToContext, WorkChain, append_, if_


def _group_to_label(group: str) -> str:
    """Sanitize a GROMACS group name to a valid AiiDA output port label."""
    label = re.sub(r"[^A-Za-z0-9_]", "_", group)
    if label and label[0].isdigit():
        label = "_" + label
    return label or "_group"


class ComputeMembranePotentialWorkChain(WorkChain):
    """Compute the electrostatic potential profile across a membrane.

    Pipeline:
      1. Trajectory preprocessing (centring + PBC fix) — engine-specific
      2. Optionally create new index groups (e.g. Water, ION) from selections
      3. ``gmx potential`` for total group + per-component groups in parallel

    Engine dispatch
    ---------------
    ``setup`` reads ``protocol.tracy.expected_engine`` (default ``"gromacs"``)
    and stores engine-specific adapter functions in context.

    Inputs
    ------
    tpr_file              : SinglefileData — .tpr from the production GromacsRunWorkChain
    trajectory_compressed : SinglefileData — .xtc from the production run
    index_file            : SinglefileData — .ndx (optional)
    protocol              : Dict           — tracy protocol (see below)
    code                  : AbstractCode   — registered gmx code
    options               : Dict           — scheduler options (optional)

    Protocol keys (all under ``tracy``):
      expected_engine          : MD engine (default: "gromacs")
      membrane_normal_axis     : axis for potential (default: z)
      potential_slices         : number of z-slices (default: 100)
      trjconv_center_group     : index group to centre on (default: "Membrane")
      trjconv_output_group     : index group to write (default: "System")
      potential_charge_group   : index group for total potential (default: "System")
      potential_component_groups : list of additional groups to decompose (default: [])
      new_index_groups         : list of gmx-select strings to create new groups (default: [])
      potential_symmetrize     : record symmetry intent for post-processing (no GROMACS flag)
      potential_correct        : apply -correct charge correction (default: true)

    Outputs
    -------
    potential_profile    : SinglefileData        — potential.xvg for total group
    potential_report     : Dict                  — analysis metadata
    potential_components : namespace of SinglefileData — one .xvg per component group
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)

        spec.input("tpr_file",              valid_type=orm.SinglefileData)
        spec.input("trajectory_compressed", valid_type=orm.SinglefileData)
        spec.input("index_file",            valid_type=orm.SinglefileData, required=False)
        spec.input("protocol",              valid_type=orm.Dict)
        spec.input("code",                  valid_type=orm.AbstractCode)
        spec.input("options",               valid_type=orm.Dict, required=False)
        spec.input("md_report",             valid_type=orm.Dict,           required=False,
                   help="RunMembraneMDWorkChain md_report; embedded in potential_report for provenance.")
        spec.input("total_simulation_time_ps", valid_type=orm.Float,       required=False,
                   help="Total production MD time in ps. Required for convergence check when "
                        "potential_convergence_check: true and md_report is absent.")

        spec.outline(
            cls.setup,
            cls.run_preprocessing,
            if_(cls.should_create_index_groups)(
                cls.run_create_index_groups,
            ),
            cls.run_potential_calculations,
            if_(cls.should_run_convergence_check)(
                cls.run_convergence_calculations,
            ),
            cls.results,
        )

        spec.output("potential_profile", valid_type=orm.SinglefileData)
        spec.output("potential_report",  valid_type=orm.Dict)
        spec.output_namespace("potential_components", valid_type=orm.SinglefileData,
                               required=False, dynamic=True)
        spec.output("potential_convergence_50", valid_type=orm.SinglefileData, required=False,
                    help="φ(z) profile from first 50% of trajectory (convergence check).")
        spec.output("potential_convergence_75", valid_type=orm.SinglefileData, required=False,
                    help="φ(z) profile from first 75% of trajectory (convergence check).")

        spec.exit_code(500, "ERROR_TRJCONV_FAILED",    message="Trajectory preprocessing failed.")
        spec.exit_code(501, "ERROR_POTENTIAL_FAILED",  message="gmx potential failed.")
        spec.exit_code(502, "ERROR_UNSUPPORTED_ENGINE", message="Engine is not supported.")
        spec.exit_code(503, "ERROR_CREATE_INDEX_GROUPS_FAILED",
                       message="CreateIndexGroupsWorkChain failed.")

    # -------------------------------------------------------------------------

    def setup(self) -> ExitCode | None:
        tracy_conf = self.inputs.protocol.get_dict().get("tracy", {})
        engine = tracy_conf.get("expected_engine", "gromacs")

        if engine == "gromacs":
            from tracy.adapters.gromacs import (
                submit_potential_preprocessing,
                submit_potential_calculation,
            )
            self.ctx.submit_preprocessing  = submit_potential_preprocessing
            self.ctx.submit_potential_calc = submit_potential_calculation
        else:
            self.report(f"Unsupported engine: {engine!r}")
            return self.exit_codes.ERROR_UNSUPPORTED_ENGINE

        self.ctx.engine           = engine
        self.ctx.axis             = tracy_conf.get("membrane_normal_axis", "z").upper()
        self.ctx.n_slices         = tracy_conf.get("potential_slices", 100)
        self.ctx.center_group     = tracy_conf.get("trjconv_center_group", "Membrane")
        self.ctx.output_group     = tracy_conf.get("trjconv_output_group", "System")
        self.ctx.charge_group     = tracy_conf.get("potential_charge_group", "System")
        self.ctx.component_groups = tracy_conf.get("potential_component_groups", [])
        self.ctx.new_index_groups = tracy_conf.get("new_index_groups", [])
        self.ctx.symmetrize       = tracy_conf.get("potential_symmetrize", False)
        self.ctx.correct          = tracy_conf.get("potential_correct", True)
        self.ctx.index_file       = self.inputs.get("index_file")
        self.ctx.convergence_check = tracy_conf.get("potential_convergence_check", True)

        # Resolve total simulation time for convergence check (ps)
        self.ctx.total_sim_time_ps = None
        if "total_simulation_time_ps" in self.inputs:
            self.ctx.total_sim_time_ps = self.inputs.total_simulation_time_ps.value
        elif "md_report" in self.inputs:
            steps = self.inputs.md_report.get_dict().get("steps_run", [])
            if steps:
                summary = steps[-1].get("quality", {}).get("summary", {})
                sim_ps = summary.get("simulation_time_ps")
                if sim_ps is not None:
                    self.ctx.total_sim_time_ps = float(sim_ps)

        self.report(
            f"Setup: engine={engine}, axis={self.ctx.axis}, slices={self.ctx.n_slices}, "
            f"center={self.ctx.center_group!r}, charge={self.ctx.charge_group!r}, "
            f"components={self.ctx.component_groups}, "
            f"new_groups={self.ctx.new_index_groups}, "
            f"symm={self.ctx.symmetrize}, correct={self.ctx.correct}, "
            f"convergence_check={self.ctx.convergence_check}, "
            f"total_sim_time_ps={self.ctx.total_sim_time_ps}"
        )

    def run_preprocessing(self) -> ToContext:
        calc = self.ctx.submit_preprocessing(
            self,
            trajectory=self.inputs.trajectory_compressed,
            tpr_file=self.inputs.tpr_file,
            center_group=self.ctx.center_group,
            output_group=self.ctx.output_group,
            index_file=self.ctx.index_file,
            options=self._serial_options(),
        )
        self.report(f"Submitted preprocessing calc (pk={calc.pk})")
        return ToContext(preprocessing=calc)

    def should_create_index_groups(self) -> bool:
        return bool(self.ctx.new_index_groups)

    def run_create_index_groups(self) -> ExitCode | ToContext | None:
        if not self.ctx.preprocessing.is_finished_ok:
            self.report(
                f"Preprocessing failed with exit status "
                f"{self.ctx.preprocessing.exit_status}"
            )
            return self.exit_codes.ERROR_TRJCONV_FAILED

        from tracy.workflows.create_index_groups import CreateIndexGroupsWorkChain

        inputs = {
            "tpr_file":   self.inputs.tpr_file,
            "selections": orm.List(self.ctx.new_index_groups),
            "protocol":   self.inputs.protocol,
            "code":       self.inputs.code,
        }
        if self.ctx.index_file is not None:
            inputs["index_file"] = self.ctx.index_file
        if "options" in self.inputs:
            inputs["options"] = self.inputs.options

        wc = self.submit(CreateIndexGroupsWorkChain, **inputs)
        self.report(f"Submitted CreateIndexGroupsWorkChain (pk={wc.pk})")
        return ToContext(create_index_groups=wc)

    def run_potential_calculations(self) -> ExitCode | None:
        if not self.ctx.preprocessing.is_finished_ok:
            self.report(
                f"Preprocessing failed with exit status "
                f"{self.ctx.preprocessing.exit_status}"
            )
            return self.exit_codes.ERROR_TRJCONV_FAILED

        if self.should_create_index_groups():
            wc = self.ctx.create_index_groups
            if not wc.is_finished_ok:
                self.report(
                    f"CreateIndexGroupsWorkChain failed with exit status {wc.exit_status}"
                )
                return self.exit_codes.ERROR_CREATE_INDEX_GROUPS_FAILED
            self.ctx.index_file = wc.outputs.index_file

        all_groups = [self.ctx.charge_group] + list(self.ctx.component_groups)
        for group in all_groups:
            calc = self.ctx.submit_potential_calc(
                self,
                trajectory=self.ctx.preprocessing.outputs.trajectory,
                tpr_file=self.inputs.tpr_file,
                charge_group=group,
                n_slices=self.ctx.n_slices,
                axis=self.ctx.axis,
                symmetrize=self.ctx.symmetrize,
                correct=self.ctx.correct,
                index_file=self.ctx.index_file,
                options=self._serial_options(),
            )
            self.report(f"Submitted potential calc for group {group!r} (pk={calc.pk})")
            self.to_context(potential_calcs=append_(calc))

    def should_run_convergence_check(self) -> bool:
        return bool(self.ctx.convergence_check and self.ctx.total_sim_time_ps is not None)

    def run_convergence_calculations(self) -> ToContext:
        """Submit two additional gmx potential jobs truncated at 50% and 75% of total time."""
        t_total = self.ctx.total_sim_time_ps
        trajectory = self.ctx.preprocessing.outputs.trajectory
        kwargs = dict(
            trajectory=trajectory,
            tpr_file=self.inputs.tpr_file,
            charge_group=self.ctx.charge_group,
            n_slices=self.ctx.n_slices,
            axis=self.ctx.axis,
            symmetrize=self.ctx.symmetrize,
            correct=self.ctx.correct,
            index_file=self.ctx.index_file,
            options=self._serial_options(),
        )
        calc_50 = self.ctx.submit_potential_calc(self, end_time_ps=0.50 * t_total, **kwargs)
        calc_75 = self.ctx.submit_potential_calc(self, end_time_ps=0.75 * t_total, **kwargs)
        self.report(
            f"Submitted convergence checks: 50% (pk={calc_50.pk}), 75% (pk={calc_75.pk})"
        )
        return ToContext(convergence_calc_50=calc_50, convergence_calc_75=calc_75)

    def results(self) -> ExitCode | None:
        all_groups = [self.ctx.charge_group] + list(self.ctx.component_groups)
        calcs = self.ctx.potential_calcs

        for group, calc in zip(all_groups, calcs):
            if not calc.is_finished_ok:
                self.report(
                    f"gmx potential for group {group!r} failed "
                    f"with exit status {calc.exit_status}"
                )
                return self.exit_codes.ERROR_POTENTIAL_FAILED

        self.out("potential_profile", calcs[0].outputs.potential_xvg)

        component_labels = {g: _group_to_label(g) for g in self.ctx.component_groups}
        for group, calc in zip(self.ctx.component_groups, calcs[1:]):
            self.out(f"potential_components.{component_labels[group]}", calc.outputs.potential_xvg)

        additivity = None
        if self.ctx.component_groups:
            from tracy.calculations.potential_analysis import validate_component_additivity
            component_xvgs = {
                component_labels[g]: calc.outputs.potential_xvg
                for g, calc in zip(self.ctx.component_groups, calcs[1:])
            }
            additivity_node = validate_component_additivity(calcs[0].outputs.potential_xvg,
                                                            **component_xvgs)
            additivity = additivity_node.get_dict()
            self.report(
                f"Additivity check: max_residual={additivity['max_residual_V']:.4f} V, "
                f"mean_residual={additivity['mean_residual_V']:.4f} V"
            )

        convergence = None
        if self.should_run_convergence_check():
            import numpy as np
            from tracy.calculations.electrostatic_energy import parse_xvg_potential

            def _xvg_residuals(xvg_100, xvg_trunc):
                with xvg_100.open(mode="r") as f:
                    z100, phi100 = parse_xvg_potential(f.read())
                with xvg_trunc.open(mode="r") as f:
                    z_tr, phi_tr = parse_xvg_potential(f.read())
                phi_interp = np.interp(z100, z_tr, phi_tr)
                residual = np.abs(phi100 - phi_interp)
                return float(residual.max()), float(residual.mean())

            xvg_100 = calcs[0].outputs.potential_xvg
            c50 = self.ctx.convergence_calc_50
            c75 = self.ctx.convergence_calc_75
            if c50.is_finished_ok and c75.is_finished_ok:
                max_50, mean_50 = _xvg_residuals(xvg_100, c50.outputs.potential_xvg)
                max_75, mean_75 = _xvg_residuals(xvg_100, c75.outputs.potential_xvg)
                convergence = {
                    "max_50_100_V":  max_50,
                    "mean_50_100_V": mean_50,
                    "max_75_100_V":  max_75,
                    "mean_75_100_V": mean_75,
                    "total_simulation_time_ps": self.ctx.total_sim_time_ps,
                }
                self.report(
                    f"Convergence check: |φ_100−φ_50|_max={max_50:.4f} V, "
                    f"|φ_100−φ_75|_max={max_75:.4f} V"
                )
                self.out("potential_convergence_50", c50.outputs.potential_xvg)
                self.out("potential_convergence_75", c75.outputs.potential_xvg)
            else:
                self.report(
                    "Convergence check calculations did not finish OK; skipping convergence report."
                )

        report_dict = {
            "axis":             self.ctx.axis,
            "slices":           self.ctx.n_slices,
            "center_group":     self.ctx.center_group,
            "output_group":     self.ctx.output_group,
            "charge_group":     self.ctx.charge_group,
            "component_groups": list(self.ctx.component_groups),
            "component_labels": component_labels,
            "symmetrize":       self.ctx.symmetrize,
            "correct":          self.ctx.correct,
            "source_tool":      "gmx potential",
            "additivity":       additivity,
            "convergence":      convergence,
        }
        if "md_report" in self.inputs:
            report_dict["md_metadata"] = self.inputs.md_report.get_dict()

        self.out("potential_report", orm.Dict(report_dict).store())
        self.report("ComputeMembranePotentialWorkChain finished successfully.")

    # -------------------------------------------------------------------------

    def _serial_options(self) -> dict:
        base = self.inputs.options.get_dict() if "options" in self.inputs else {}
        return {**base, "withmpi": False}
