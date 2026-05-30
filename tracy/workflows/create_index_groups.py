"""CreateIndexGroupsWorkChain: create new named atom groups and append to an index file."""

from __future__ import annotations

from aiida import orm
from aiida.engine import ExitCode, ToContext, WorkChain


class CreateIndexGroupsWorkChain(WorkChain):
    """Create new named atom groups from selection strings and append them to an index file.

    The CHARMM-GUI index file typically contains only ``MEMB``, ``SOLV``, and
    ``SYSTEM``.  This WorkChain adds user-defined groups (e.g. ``Water``, ``ION``)
    by selecting atoms from the topology, then merging with the original index.

    The existing groups are never modified::

        Before:  [ MEMB ]  [ SOLV ]  [ SYSTEM ]
        After:   [ MEMB ]  [ SOLV ]  [ SYSTEM ]  [ Water ]  [ ION ]

    Engine dispatch
    ---------------
    ``setup`` reads ``protocol.tracy.expected_engine`` and stores engine-specific
    adapter functions in context.  Currently only ``"gromacs"`` is supported
    (uses ``SelectGroupsCalculation`` / ``gmx select``).

    Inputs
    ------
    tpr_file   : SinglefileData — topology reference for atom information
    index_file : SinglefileData — existing .ndx to append to (optional)
    selections : List           — gmx-select selection strings
    protocol   : Dict           — tracy protocol (``expected_engine`` key)
    code       : AbstractCode   — registered gmx code
    options    : Dict           — scheduler options (optional)

    Outputs
    -------
    index_file : SinglefileData — combined .ndx with original + new groups
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)

        spec.input("tpr_file",   valid_type=orm.SinglefileData)
        spec.input("index_file", valid_type=orm.SinglefileData, required=False)
        spec.input("selections", valid_type=orm.List,
                   help='List of gmx-select strings, e.g. [\'"Water" resname TIP3\']')
        spec.input("protocol",   valid_type=orm.Dict)
        spec.input("code",       valid_type=orm.AbstractCode)
        spec.input("options",    valid_type=orm.Dict, required=False)

        spec.outline(
            cls.setup,
            cls.run_select_groups,
            cls.merge,
            cls.results,
        )

        spec.output("index_file", valid_type=orm.SinglefileData,
                    help="Combined .ndx: original groups + newly created groups")

        spec.exit_code(520, "ERROR_UNSUPPORTED_ENGINE",
                       message="Engine is not supported for index group creation.")
        spec.exit_code(521, "ERROR_SELECT_GROUPS_FAILED",
                       message="SelectGroups calculation failed.")

    # -------------------------------------------------------------------------

    def setup(self) -> ExitCode | None:
        tracy_conf = self.inputs.protocol.get_dict().get("tracy", {})
        engine = tracy_conf.get("expected_engine", "gromacs")

        if engine == "gromacs":
            from tracy.adapters.gromacs import submit_select_groups
            self.ctx.submit_select_groups = submit_select_groups
        else:
            self.report(f"Unsupported engine for index group creation: {engine!r}")
            return self.exit_codes.ERROR_UNSUPPORTED_ENGINE

        self.ctx.engine = engine
        self.report(
            f"Setup: engine={engine}, "
            f"selections={self.inputs.selections.get_list()}"
        )

    def run_select_groups(self):
        calc = self.ctx.submit_select_groups(
            self,
            tpr_file=self.inputs.tpr_file,
            index_file=self.inputs.get("index_file"),
            selections=self.inputs.selections,
            options=self._serial_options(),
        )
        self.report(f"Submitted SelectGroupsCalculation (pk={calc.pk})")
        return ToContext(select_groups=calc)

    def merge(self) -> ExitCode | None:
        calc = self.ctx.select_groups
        if not calc.is_finished_ok:
            self.report(f"SelectGroups failed with exit status {calc.exit_status}")
            return self.exit_codes.ERROR_SELECT_GROUPS_FAILED

        from tracy.utils.index import merge_index_files

        if "index_file" in self.inputs:
            merged = merge_index_files(self.inputs.index_file, calc.outputs.index_file)
        else:
            merged = calc.outputs.index_file

        self.ctx.merged_index = merged
        self.report("Index files merged.")

    def results(self) -> None:
        self.out("index_file", self.ctx.merged_index)
        self.report("CreateIndexGroupsWorkChain finished successfully.")

    # -------------------------------------------------------------------------

    def _serial_options(self) -> dict:
        base = self.inputs.options.get_dict() if "options" in self.inputs else {}
        return {**base, "withmpi": False}
