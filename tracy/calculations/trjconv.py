"""TrjconvCalculation: gmx trjconv for PBC-fixing and membrane centring."""

from __future__ import annotations

from aiida.common import CalcInfo, CodeInfo
from aiida.engine import CalcJob, ExitCode
from aiida.orm import SinglefileData, Str
from aiida.parsers import Parser


_OUTPUT_XTC = "centred.xtc"
_STDOUT = "trjconv.out"


class TrjconvCalculation(CalcJob):
    """Run ``gmx trjconv`` to centre the membrane and fix PBC.

    Writes group-selection stdin non-interactively.  Analysis tools are
    always run serial (withmpi=False) regardless of the registered code.
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)

        spec.inputs["metadata"]["options"]["parser_name"].default = "tracy.trjconv"
        spec.inputs["metadata"]["options"]["withmpi"].default = False

        spec.input("trajectory",   valid_type=SinglefileData, help="Input .xtc trajectory")
        spec.input("tpr_file",     valid_type=SinglefileData, help="Input .tpr run file")
        spec.input("index_file",   valid_type=SinglefileData, required=False, help="Index file (.ndx)")
        spec.input("center_group", valid_type=Str, help="Index group to centre on (e.g. 'Membrane')")
        spec.input("output_group", valid_type=Str, default=lambda: Str("System"),
                   help="Index group to write out (e.g. 'System')")

        spec.output("trajectory", valid_type=SinglefileData, help="Centred output .xtc")

        spec.outputs.dynamic = True
        spec.exit_code(300, "ERROR_MISSING_OUTPUT_FILES",
                       message="gmx trjconv did not produce the expected output .xtc file.")

    def prepare_for_submission(self, folder):
        # stdin: two group selections (centre group, output group)
        with folder.open("stdin.txt", "w") as fh:
            fh.write(f"{self.inputs.center_group.value}\n{self.inputs.output_group.value}\n")

        input_files = [
            (self.inputs.trajectory.uuid, self.inputs.trajectory.filename, self.inputs.trajectory.filename),
            (self.inputs.tpr_file.uuid, self.inputs.tpr_file.filename, self.inputs.tpr_file.filename),
        ]
        if "index_file" in self.inputs:
            ndx = self.inputs.index_file
            input_files.append((ndx.uuid, ndx.filename, ndx.filename))

        cmdline = [
            "trjconv",
            "-f", self.inputs.trajectory.filename,
            "-s", self.inputs.tpr_file.filename,
            "-o", _OUTPUT_XTC,
            "-center", "-boxcenter", "rect", "-pbc", "mol",
        ]
        if "index_file" in self.inputs:
            cmdline += ["-n", self.inputs.index_file.filename]

        codeinfo = CodeInfo()
        codeinfo.cmdline_params = cmdline
        codeinfo.code_uuid = self.inputs.code.uuid
        codeinfo.stdout_name = _STDOUT
        codeinfo.stdin_name = "stdin.txt"
        codeinfo.withmpi = False

        calcinfo = CalcInfo()
        calcinfo.codes_info = [codeinfo]
        calcinfo.local_copy_list = input_files
        calcinfo.retrieve_list = [_STDOUT, _OUTPUT_XTC]
        return calcinfo


class TrjconvParser(Parser):
    """Parse output of TrjconvCalculation."""

    def parse(self, **kwargs):
        files_retrieved = self.retrieved.list_object_names()

        if _OUTPUT_XTC not in files_retrieved:
            self.logger.error(f"Expected {_OUTPUT_XTC!r}, retrieved: {files_retrieved}")
            return self.exit_codes.ERROR_MISSING_OUTPUT_FILES

        with self.retrieved.open(_OUTPUT_XTC, "rb") as fh:
            self.out("trajectory", SinglefileData(file=fh, filename=_OUTPUT_XTC))

        return ExitCode(0)
