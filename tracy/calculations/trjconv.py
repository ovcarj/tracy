"""TrjconvCalculation: gmx trjconv for PBC-fixing and membrane centring.

Two-pass strategy (defensive, recommended for asymmetric bilayers):
  Pass 1: -pbc mol -ur compact          — make molecules whole under PBC
  Pass 2: -center -pbc mol -ur compact  — centre on membrane group, re-wrap
"""

from __future__ import annotations

from aiida.common import CalcInfo, CodeInfo
from aiida.engine import CalcJob, ExitCode
from aiida.orm import SinglefileData, Str
from aiida.parsers import Parser


_INTERMEDIATE_XTC = "pbc_fixed.xtc"
_OUTPUT_XTC = "centred.xtc"
_STDOUT_PASS1 = "trjconv_pass1.out"
_STDOUT_PASS2 = "trjconv_pass2.out"


class TrjconvCalculation(CalcJob):
    """Run ``gmx trjconv`` to centre the membrane and fix PBC.

    Two sequential trjconv calls are submitted in the same job:
      1. Fix PBC (make molecules whole, compact unit cell) — output group only.
      2. Centre on the membrane group, re-wrap molecules — centre + output group.

    Analysis tools are always run serial (withmpi=False).
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)

        spec.inputs["metadata"]["options"]["parser_name"].default = "tracy.trjconv"
        spec.inputs["metadata"]["options"]["withmpi"].default = False

        spec.input("trajectory",   valid_type=SinglefileData, help="Input .xtc trajectory")
        spec.input("tpr_file",     valid_type=SinglefileData, help="Input .tpr run file")
        spec.input("index_file",   valid_type=SinglefileData, required=False, help="Index file (.ndx)")
        spec.input("center_group", valid_type=Str, help="Index group to centre on (e.g. 'MEMB')")
        spec.input("output_group", valid_type=Str, default=lambda: Str("System"),
                   help="Index group to write out (e.g. 'System')")

        spec.output("trajectory", valid_type=SinglefileData, help="Centred output .xtc")

        spec.outputs.dynamic = True
        spec.exit_code(300, "ERROR_MISSING_OUTPUT_FILES",
                       message="gmx trjconv did not produce the expected output .xtc file.")

    def prepare_for_submission(self, folder):
        # Pass 1 stdin: output group only (no centering prompt)
        with folder.open("stdin_pass1.txt", "w") as fh:
            fh.write(f"{self.inputs.output_group.value}\n")

        # Pass 2 stdin: centre group, then output group
        with folder.open("stdin_pass2.txt", "w") as fh:
            fh.write(f"{self.inputs.center_group.value}\n{self.inputs.output_group.value}\n")

        input_files = [
            (self.inputs.trajectory.uuid, self.inputs.trajectory.filename, self.inputs.trajectory.filename),
            (self.inputs.tpr_file.uuid, self.inputs.tpr_file.filename, self.inputs.tpr_file.filename),
        ]
        if "index_file" in self.inputs:
            ndx = self.inputs.index_file
            input_files.append((ndx.uuid, ndx.filename, ndx.filename))

        ndx_flag = ["-n", self.inputs.index_file.filename] if "index_file" in self.inputs else []

        # Pass 1: make molecules whole, compact unit cell
        codeinfo1 = CodeInfo()
        codeinfo1.cmdline_params = [
            "trjconv",
            "-f", self.inputs.trajectory.filename,
            "-s", self.inputs.tpr_file.filename,
            "-o", _INTERMEDIATE_XTC,
            "-pbc", "mol", "-ur", "compact",
            *ndx_flag,
        ]
        codeinfo1.code_uuid = self.inputs.code.uuid
        codeinfo1.stdout_name = _STDOUT_PASS1
        codeinfo1.stdin_name = "stdin_pass1.txt"
        codeinfo1.withmpi = False

        # Pass 2: centre on membrane group, re-wrap
        codeinfo2 = CodeInfo()
        codeinfo2.cmdline_params = [
            "trjconv",
            "-f", _INTERMEDIATE_XTC,
            "-s", self.inputs.tpr_file.filename,
            "-o", _OUTPUT_XTC,
            "-center", "-pbc", "mol", "-ur", "compact",
            *ndx_flag,
        ]
        codeinfo2.code_uuid = self.inputs.code.uuid
        codeinfo2.stdout_name = _STDOUT_PASS2
        codeinfo2.stdin_name = "stdin_pass2.txt"
        codeinfo2.withmpi = False

        calcinfo = CalcInfo()
        calcinfo.codes_info = [codeinfo1, codeinfo2]
        calcinfo.local_copy_list = input_files
        calcinfo.retrieve_list = [_STDOUT_PASS1, _STDOUT_PASS2, _OUTPUT_XTC]
        return calcinfo


class TrjconvParser(Parser):
    """Parse output of TrjconvCalculation."""

    def parse(self, **kwargs):
        files_retrieved = self.retrieved.list_object_names()

        if _OUTPUT_XTC not in files_retrieved:
            self.logger.error(
                f"Expected {_OUTPUT_XTC!r} (pass-2 output); retrieved: {files_retrieved}. "
                f"Check {_STDOUT_PASS1!r} and {_STDOUT_PASS2!r} for GROMACS errors."
            )
            return self.exit_codes.ERROR_MISSING_OUTPUT_FILES

        with self.retrieved.open(_OUTPUT_XTC, "rb") as fh:
            self.out("trajectory", SinglefileData(file=fh, filename=_OUTPUT_XTC))

        return ExitCode(0)
