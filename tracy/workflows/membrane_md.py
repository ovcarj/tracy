"""RunMembraneMDWorkChain: run the CHARMM-GUI MD protocol on a membrane bundle."""

from __future__ import annotations

import tempfile
from pathlib import Path

from aiida import orm
from aiida.engine import ExitCode, ToContext, WorkChain, while_


def _select_steps(manifest: list[dict], requested: list[str]) -> list[dict]:
    """Return an ordered subset of manifest entries matching the requested sequence.

    Each entry in *requested* consumes the next manifest step with that name.
    Repeating a name selects successive steps: ["equilibration", "equilibration"]
    picks step6.1 then step6.2.  Raises ValueError if a requested name has no
    remaining match in the manifest.
    """
    result = []
    search_from = 0
    for name in requested:
        for i in range(search_from, len(manifest)):
            if manifest[i]["name"] == name:
                result.append(manifest[i])
                search_from = i + 1
                break
        else:
            raise ValueError(
                f"No manifest step named '{name}' found after position {search_from}."
            )
    return result


def _assign_output_prefixes(manifest: list[dict]) -> list[dict]:
    """Add a unique 'prefix' key to each manifest step.

    Steps whose name is unique in the manifest keep the name as-is.
    Repeated names (e.g. six equilibration steps) get _1, _2, ... suffixes.
    """
    from collections import Counter
    name_counts = Counter(s["name"] for s in manifest)
    name_seen: Counter = Counter()
    result = []
    for step in manifest:
        name_seen[step["name"]] += 1
        if name_counts[step["name"]] > 1:
            prefix = f"{step['name']}_{name_seen[step['name']]}"
        else:
            prefix = step["name"]
        result.append({**step, "prefix": prefix})
    return result


class RunMembraneMDWorkChain(WorkChain):
    """Run GROMACS MD steps from a CHARMM-GUI membrane input bundle.

    Dispatches to the appropriate engine adapter based on
    ``protocol.tracy.expected_engine``.  Adding a new engine means adding a
    ``prepare_<engine>_run_inputs`` adapter function and one new branch in
    ``setup`` — this WorkChain does not change.

    Steps are driven by ``protocol.tracy.md_steps``, which filters the
    CHARMM-GUI manifest.  The output structure of each completed step is passed
    automatically to the next (checkpoints are intentionally not forwarded —
    see CLAUDE.md §6.9).

    Inputs
    ------
    md_input_bundle : FolderData   — CHARMM-GUI GROMACS bundle
    protocol        : Dict         — tracy protocol dict
    code            : AbstractCode — MD engine code (e.g. gmx@remote)
    options         : Dict         — scheduler resource options (optional)

    Outputs
    -------
    md_results : FolderData — output files from the last completed step
    md_report  : Dict       — step names run and final exit status
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)

        spec.input("md_input_bundle",   valid_type=orm.FolderData)
        spec.input("protocol",          valid_type=orm.Dict)
        spec.input("code",              valid_type=orm.AbstractCode)
        spec.input("options",           valid_type=orm.Dict,           required=False)
        spec.input("initial_structure", valid_type=orm.SinglefileData, required=False)

        spec.outline(
            cls.setup,
            while_(cls.should_run_next_step)(
                cls.run_next_step,
                cls.inspect_step,
            ),
            cls.results,
        )

        spec.output("md_results", valid_type=orm.FolderData)
        spec.output("md_report",  valid_type=orm.Dict)
        spec.output_namespace("step_quality", valid_type=orm.Dict,
                               required=False, dynamic=True,
                               help="Per-step quality check results keyed by step prefix.")

        spec.exit_code(400, "ERROR_UNSUPPORTED_ENGINE", message="MD engine is not supported.")
        spec.exit_code(401, "ERROR_MANIFEST_INVALID",   message="Could not build a valid step manifest.")
        spec.exit_code(402, "ERROR_MD_STEP_FAILED",     message="An MD step failed.")

    # -------------------------------------------------------------------------

    def setup(self) -> ExitCode | None:
        protocol = self.inputs.protocol.get_dict()
        self.ctx.protocol = protocol

        tracy_conf = protocol.get("tracy", {})
        engine = tracy_conf.get("expected_engine", "gromacs")

        if engine == "gromacs":
            from tracy.adapters.gromacs import build_step_manifest, prepare_gromacs_run_inputs
            prepare_fn = prepare_gromacs_run_inputs
        else:
            self.report(f"Unsupported engine: {engine!r}")
            return self.exit_codes.ERROR_UNSUPPORTED_ENGINE

        try:
            manifest = build_step_manifest(self.inputs.md_input_bundle)
        except Exception as exc:
            self.report(f"Failed to build step manifest: {exc}")
            return self.exit_codes.ERROR_MANIFEST_INVALID

        requested = tracy_conf.get("md_steps", ["minimization"])
        if not requested:
            self.report("md_steps is empty — nothing to run.")
            return self.exit_codes.ERROR_MANIFEST_INVALID
        try:
            manifest = _select_steps(manifest, requested)
        except ValueError as exc:
            self.report(f"Invalid md_steps: {exc}")
            return self.exit_codes.ERROR_MANIFEST_INVALID

        self.ctx.manifest = _assign_output_prefixes(manifest)
        self.ctx.run_inputs = prepare_fn(self.inputs.md_input_bundle)
        self.ctx.engine = engine
        self.ctx.current_step_index = 0
        self.ctx.completed_steps = []
        self.ctx.max_retries = tracy_conf.get("max_retries", 0)
        self.ctx.step_retries = {}

        if "initial_structure" in self.inputs:
            self.ctx.run_inputs["structure"] = self.inputs.initial_structure

        self.report(f"Setup complete. Engine={engine}, steps={[s['prefix'] for s in self.ctx.manifest]}")

    def should_run_next_step(self) -> bool:
        return self.ctx.current_step_index < len(self.ctx.manifest)

    def run_next_step(self):
        step = self.ctx.manifest[self.ctx.current_step_index]
        mdp_file = self._extract_file_from_bundle(step["mdp"])

        if self.ctx.engine == "gromacs":
            from tracy.workflows.gromacs_run import GromacsRunWorkChain
            engine_wc = GromacsRunWorkChain

        mdp_overrides = self.ctx.protocol.get("tracy", {}).get("mdp_overrides", {})
        overrides = (
            mdp_overrides.get(step["step_id"])    # most specific: "step6.3"
            or mdp_overrides.get(step["prefix"])  # unique prefix:  "equilibration_3"
            or mdp_overrides.get(step["name"])    # generic name:   "equilibration"
        )
        if overrides:
            from tracy.adapters.gromacs import patch_mdp
            mdp_file = patch_mdp(mdp_file, orm.Dict(overrides))

        inputs: dict = {
            "structure":     self.ctx.run_inputs["structure"],
            "topology":      self.ctx.run_inputs["topology"],
            "toppar":        self.ctx.run_inputs["toppar"],
            "mdp_file":      mdp_file,
            "gromacs_code":  self.inputs.code,
            "output_prefix": orm.Str(step["prefix"]),
        }
        if "index" in self.ctx.run_inputs:
            inputs["index_file"] = self.ctx.run_inputs["index"]
        if "checkpoint" in self.ctx.run_inputs:
            inputs["checkpoint"] = self.ctx.run_inputs["checkpoint"]
        if "options" in self.inputs:
            inputs["options"] = self.inputs.options

        calc = self.submit(engine_wc, **inputs)
        self.report(f"Submitted {engine_wc.__name__} for step '{step['name']}' (pk={calc.pk})")
        return ToContext(current_step_wc=calc)

    def inspect_step(self) -> ExitCode | None:
        wc = self.ctx.current_step_wc
        step = self.ctx.manifest[self.ctx.current_step_index]

        if not wc.is_finished_ok:
            step_idx = self.ctx.current_step_index
            retries_so_far = self.ctx.step_retries.get(step_idx, 0)
            if retries_so_far < self.ctx.max_retries:
                self.ctx.step_retries[step_idx] = retries_so_far + 1
                self.report(
                    f"Step '{step['name']}' failed (exit {wc.exit_status}), "
                    f"retrying ({retries_so_far + 1}/{self.ctx.max_retries})."
                )
                return
            self.report(f"Step '{step['name']}' failed with exit status {wc.exit_status}")
            self.out("md_report", orm.Dict({
                "steps_run": self.ctx.completed_steps,
                "final_step_exit_status": wc.exit_status,
                "failed_step": step["name"],
            }).store())
            return self.exit_codes.ERROR_MD_STEP_FAILED

        self.ctx.run_inputs["structure"] = wc.outputs.output_structure

        self.ctx.completed_steps.append({
            "name":    step["name"],
            "prefix":  step["prefix"],
            "mdp":     step["mdp"],
            "step_id": step["step_id"],
            "pk":      wc.pk,
        })
        self.ctx.current_step_index += 1
        self.report(f"Step '{step['name']}' finished OK (pk={wc.pk}).")

    def results(self) -> ExitCode | None:
        last_wc = self.ctx.current_step_wc

        md_results = self._collect_outputs_as_folder(last_wc)

        from tracy.calculations.gromacs_log import check_step_quality
        quality_issues = []
        for step in self.ctx.completed_steps:
            step_wc = orm.load_node(step["pk"])
            quality = check_step_quality(step_wc.outputs.log, self.inputs.protocol)
            step["quality"] = quality.get_dict()
            # Expose as named output so quality nodes are reachable from this WorkChain
            self.out(f"step_quality.{step['prefix']}", quality)
            if not step["quality"]["passed"]:
                quality_issues.append((step["name"], step["quality"]["warnings"]))

        if quality_issues:
            for name, warnings in quality_issues:
                for w in warnings:
                    self.report(f"Quality warning [{name}]: {w}")

        self.out("md_results", md_results.store())
        self.out("md_report", orm.Dict({
            "steps_run": self.ctx.completed_steps,
            "final_step_exit_status": last_wc.exit_status,
        }).store())
        self.report("RunMembraneMDWorkChain finished successfully.")

    # -------------------------------------------------------------------------

    def _extract_file_from_bundle(self, filename: str) -> orm.SinglefileData:
        """Return a SinglefileData for a named file inside md_input_bundle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.inputs.md_input_bundle.base.repository.copy_tree(tmpdir)
            return orm.SinglefileData(file=str(Path(tmpdir) / filename))

    def _collect_outputs_as_folder(self, wc) -> orm.FolderData:
        """Gather all SinglefileData outputs of a WorkChain into a FolderData."""
        from aiida.common.links import LinkType
        folder = orm.FolderData()
        for link in wc.base.links.get_outgoing(link_type=LinkType.RETURN).all():
            if isinstance(link.node, orm.SinglefileData):
                with link.node.open(mode="rb") as fh:
                    folder.put_object_from_filelike(fh, link.node.filename)
        return folder
