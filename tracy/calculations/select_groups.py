"""SelectGroupsCalculation: gmx select to create new named atom groups."""

from __future__ import annotations

from aiida.common import CalcInfo, CodeInfo
from aiida.engine import CalcJob, ExitCode
from aiida.orm import List, SinglefileData
from aiida.parsers import Parser


_OUTPUT_NDX = "new_groups.ndx"
_STDOUT     = "select_groups.out"


class SelectGroupsCalculation(CalcJob):
    """Run ``gmx select`` to create new named atom groups from selection strings.

    The output index file contains ONLY the newly created groups.  Use
    ``merge_index_files`` (``tracy.utils.index``) to combine with an existing
    index file if the original groups must be preserved.

    Selection strings use the GROMACS selection syntax, e.g.::

        '"Water" resname TIP3'
        '"ION" resname POT CLA'

    Force-field–specific residue names must be supplied by the caller via the
    ``selections`` input — tracy does not hard-code any residue names.
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)

        spec.inputs["metadata"]["options"]["parser_name"].default = "tracy.select_groups"
        spec.inputs["metadata"]["options"]["withmpi"].default = False

        spec.input("tpr_file",   valid_type=SinglefileData,
                   help="Topology reference (.tpr) for atom/residue information")
        spec.input("index_file", valid_type=SinglefileData, required=False,
                   help="Existing .ndx — makes its groups available as references in selections")
        spec.input("selections", valid_type=List,
                   help='List of gmx-select selection strings, e.g. [\'"Water" resname TIP3\']')

        spec.output("index_file", valid_type=SinglefileData,
                    help="Output .ndx containing ONLY the newly created groups")

        spec.exit_code(300, "ERROR_MISSING_OUTPUT_FILES",
                       message="gmx select did not produce the expected index file.")

    def prepare_for_submission(self, folder):
        selections = self.inputs.selections.get_list()
        select_str = "; ".join(selections)

        input_files = [
            (self.inputs.tpr_file.uuid, self.inputs.tpr_file.filename,
             self.inputs.tpr_file.filename),
        ]
        if "index_file" in self.inputs:
            ndx = self.inputs.index_file
            input_files.append((ndx.uuid, ndx.filename, ndx.filename))

        cmdline = [
            "select",
            "-s", self.inputs.tpr_file.filename,
            "-on", _OUTPUT_NDX,
            "-select", select_str,
        ]
        if "index_file" in self.inputs:
            cmdline += ["-n", self.inputs.index_file.filename]

        codeinfo = CodeInfo()
        codeinfo.cmdline_params = cmdline
        codeinfo.code_uuid = self.inputs.code.uuid
        codeinfo.stdout_name = _STDOUT
        codeinfo.withmpi = False

        calcinfo = CalcInfo()
        calcinfo.codes_info = [codeinfo]
        calcinfo.local_copy_list = input_files
        calcinfo.retrieve_list = [_STDOUT, _OUTPUT_NDX]
        return calcinfo


class SelectGroupsParser(Parser):
    """Parse output of SelectGroupsCalculation."""

    def parse(self, **kwargs):
        files_retrieved = self.retrieved.list_object_names()

        if _OUTPUT_NDX not in files_retrieved:
            self.logger.error(f"Expected {_OUTPUT_NDX!r}, retrieved: {files_retrieved}")
            return self.exit_codes.ERROR_MISSING_OUTPUT_FILES

        with self.retrieved.open(_OUTPUT_NDX, "rb") as fh:
            self.out("index_file", SinglefileData(file=fh, filename=_OUTPUT_NDX))

        return ExitCode(0)
