"""ComputeMembranePotentialWorkChain: gmx trjconv → gmx potential."""

from __future__ import annotations

from aiida import orm
from aiida.engine import ExitCode, ToContext, WorkChain


class ComputeMembranePotentialWorkChain(WorkChain):
    """Compute the electrostatic potential profile across a membrane.

    Runs two sequential GROMACS analysis steps:
      1. ``gmx trjconv`` — centres the membrane and fixes PBC
      2. ``gmx potential`` — integrates Poisson's equation along the membrane
         normal to produce a φ(z) profile

    Both steps use the same registered ``gmx`` code and are always run serial.

    Inputs
    ------
    tpr_file              : SinglefileData — .tpr from the production GromacsRunWorkChain
    trajectory_compressed : SinglefileData — .xtc from the production run
    index_file            : SinglefileData — .ndx (optional)
    protocol              : Dict           — tracy protocol (see below)
    code                  : AbstractCode   — registered gmx code
    options               : Dict           — scheduler options (optional)

    Protocol keys (all under ``tracy``):
      membrane_normal_axis     : axis for potential (default: z)
      potential_slices         : number of z-slices (default: 100)
      trjconv_center_group     : index group to centre on (default: "Membrane")
      trjconv_output_group     : index group to write (default: "System")
      potential_charge_group   : index group for potential analysis (default: "System")
      potential_symmetrize     : apply -symm (default: false; asymmetric bilayers)
      potential_correct        : apply -correct charge correction (default: true)

    Outputs
    -------
    potential_profile : SinglefileData — potential.xvg
    potential_report  : Dict           — analysis metadata
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

        spec.outline(
            cls.setup,
            cls.run_trjconv,
            cls.run_potential,
            cls.results,
        )

        spec.output("potential_profile", valid_type=orm.SinglefileData)
        spec.output("potential_report",  valid_type=orm.Dict)

        spec.exit_code(500, "ERROR_TRJCONV_FAILED",  message="gmx trjconv failed.")
        spec.exit_code(501, "ERROR_POTENTIAL_FAILED", message="gmx potential failed.")

    # -------------------------------------------------------------------------

    def setup(self) -> None:
        tracy_conf = self.inputs.protocol.get_dict().get("tracy", {})
        self.ctx.axis         = tracy_conf.get("membrane_normal_axis", "z").upper()
        self.ctx.n_slices     = tracy_conf.get("potential_slices", 100)
        self.ctx.center_group = tracy_conf.get("trjconv_center_group", "Membrane")
        self.ctx.output_group = tracy_conf.get("trjconv_output_group", "System")
        self.ctx.charge_group = tracy_conf.get("potential_charge_group", "System")
        self.ctx.symmetrize   = tracy_conf.get("potential_symmetrize", False)
        self.ctx.correct      = tracy_conf.get("potential_correct", True)
        self.report(
            f"Setup: axis={self.ctx.axis}, slices={self.ctx.n_slices}, "
            f"center={self.ctx.center_group!r}, charge={self.ctx.charge_group!r}, "
            f"symm={self.ctx.symmetrize}, correct={self.ctx.correct}"
        )

    def run_trjconv(self):
        from tracy.calculations.trjconv import TrjconvCalculation

        inputs = {
            "code":         self.inputs.code,
            "trajectory":   self.inputs.trajectory_compressed,
            "tpr_file":     self.inputs.tpr_file,
            "center_group": orm.Str(self.ctx.center_group),
            "output_group": orm.Str(self.ctx.output_group),
            "metadata":     {"options": self._serial_options()},
        }
        if "index_file" in self.inputs:
            inputs["index_file"] = self.inputs.index_file

        calc = self.submit(TrjconvCalculation, **inputs)
        self.report(f"Submitted TrjconvCalculation (pk={calc.pk})")
        return ToContext(trjconv=calc)

    def run_potential(self) -> ExitCode | None:
        if not self.ctx.trjconv.is_finished_ok:
            self.report(f"trjconv failed with exit status {self.ctx.trjconv.exit_status}")
            return self.exit_codes.ERROR_TRJCONV_FAILED

        from tracy.calculations.potential import PotentialCalculation

        inputs = {
            "code":         self.inputs.code,
            "trajectory":   self.ctx.trjconv.outputs.trajectory,
            "tpr_file":     self.inputs.tpr_file,
            "charge_group": orm.Str(self.ctx.charge_group),
            "n_slices":     orm.Int(self.ctx.n_slices),
            "axis":         orm.Str(self.ctx.axis),
            "symmetrize":   orm.Bool(self.ctx.symmetrize),
            "correct":      orm.Bool(self.ctx.correct),
            "metadata":     {"options": self._serial_options()},
        }
        if "index_file" in self.inputs:
            inputs["index_file"] = self.inputs.index_file

        calc = self.submit(PotentialCalculation, **inputs)
        self.report(f"Submitted PotentialCalculation (pk={calc.pk})")
        return ToContext(potential=calc)

    def results(self) -> ExitCode | None:
        if not self.ctx.potential.is_finished_ok:
            self.report(f"gmx potential failed with exit status {self.ctx.potential.exit_status}")
            return self.exit_codes.ERROR_POTENTIAL_FAILED

        self.out("potential_profile", self.ctx.potential.outputs.potential_xvg)
        self.out("potential_report", orm.Dict({
            "axis":         self.ctx.axis,
            "slices":       self.ctx.n_slices,
            "center_group": self.ctx.center_group,
            "output_group": self.ctx.output_group,
            "charge_group": self.ctx.charge_group,
            "symmetrize":   self.ctx.symmetrize,
            "correct":      self.ctx.correct,
            "source_tool":  "gmx potential",
        }).store())
        self.report("ComputeMembranePotentialWorkChain finished successfully.")

    # -------------------------------------------------------------------------

    def _serial_options(self) -> dict:
        """Build scheduler options with withmpi forced to False."""
        base = self.inputs.options.get_dict() if "options" in self.inputs else {}
        return {**base, "withmpi": False}
