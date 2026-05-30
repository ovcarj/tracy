"""PotentialCalculation: gmx potential for electrostatic potential profiles."""

from __future__ import annotations

from aiida.common import CalcInfo, CodeInfo
from aiida.engine import CalcJob, ExitCode
from aiida.orm import Bool, Int, SinglefileData, Str
from aiida.parsers import Parser


_OUTPUT_XVG = "potential.xvg"
_STDOUT = "potential.out"


class PotentialCalculation(CalcJob):
    """Run ``gmx potential`` to compute the electrostatic potential profile.

    Averages charge density over the xy plane at each z-slice and integrates
    Poisson's equation twice to obtain φ(z).  Always runs serial (withmpi=False).
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)

        spec.inputs["metadata"]["options"]["parser_name"].default = "tracy.potential"
        spec.inputs["metadata"]["options"]["withmpi"].default = False

        spec.input("trajectory",   valid_type=SinglefileData, help="Centred input .xtc trajectory")
        spec.input("tpr_file",     valid_type=SinglefileData, help="Input .tpr run file")
        spec.input("index_file",   valid_type=SinglefileData, required=False, help="Index file (.ndx)")
        spec.input("charge_group", valid_type=Str, default=lambda: Str("System"),
                   help="Index group to analyse")
        spec.input("n_slices",     valid_type=Int,  default=lambda: Int(100),
                   help="Number of slices along the membrane normal")
        spec.input("axis",         valid_type=Str,  default=lambda: Str("Z"),
                   help="Membrane normal axis (X, Y, or Z)")
        spec.input("symmetrize",   valid_type=Bool, default=lambda: Bool(False),
                   help="Record symmetry intent in potential_report for post-processing. "
                        "gmx potential 2021 has no -symm flag; averaging is done at plot time.")
        spec.input("correct",      valid_type=Bool, default=lambda: Bool(True),
                   help="Apply -correct flag (charge correction, recommended)")

        spec.output("potential_xvg", valid_type=SinglefileData, help="Potential profile (.xvg)")

        spec.outputs.dynamic = True
        spec.exit_code(300, "ERROR_MISSING_OUTPUT_FILES",
                       message="gmx potential did not produce the expected potential.xvg file.")

    def prepare_for_submission(self, folder):
        # stdin: one group selection
        with folder.open("stdin.txt", "w") as fh:
            fh.write(f"{self.inputs.charge_group.value}\n")

        input_files = [
            (self.inputs.trajectory.uuid, self.inputs.trajectory.filename, self.inputs.trajectory.filename),
            (self.inputs.tpr_file.uuid, self.inputs.tpr_file.filename, self.inputs.tpr_file.filename),
        ]
        if "index_file" in self.inputs:
            ndx = self.inputs.index_file
            input_files.append((ndx.uuid, ndx.filename, ndx.filename))

        cmdline = [
            "potential",
            "-f", self.inputs.trajectory.filename,
            "-s", self.inputs.tpr_file.filename,
            "-o", _OUTPUT_XVG,
            "-d", self.inputs.axis.value,
            "-sl", str(self.inputs.n_slices.value),
        ]
        if "index_file" in self.inputs:
            cmdline += ["-n", self.inputs.index_file.filename]
        if self.inputs.correct.value:
            cmdline.append("-correct")

        codeinfo = CodeInfo()
        codeinfo.cmdline_params = cmdline
        codeinfo.code_uuid = self.inputs.code.uuid
        codeinfo.stdout_name = _STDOUT
        codeinfo.stdin_name = "stdin.txt"
        codeinfo.withmpi = False

        calcinfo = CalcInfo()
        calcinfo.codes_info = [codeinfo]
        calcinfo.local_copy_list = input_files
        calcinfo.retrieve_list = [_STDOUT, _OUTPUT_XVG]
        return calcinfo


class PotentialParser(Parser):
    """Parse output of PotentialCalculation."""

    def parse(self, **kwargs):
        files_retrieved = self.retrieved.list_object_names()

        if _OUTPUT_XVG not in files_retrieved:
            self.logger.error(f"Expected {_OUTPUT_XVG!r}, retrieved: {files_retrieved}")
            return self.exit_codes.ERROR_MISSING_OUTPUT_FILES

        with self.retrieved.open(_OUTPUT_XVG, "rb") as fh:
            self.out("potential_xvg", SinglefileData(file=fh, filename=_OUTPUT_XVG))

        return ExitCode(0)
