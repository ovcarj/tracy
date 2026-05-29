"""RunMembraneMDWorkChain: run the CHARMM-GUI MD protocol on a membrane bundle."""

from __future__ import annotations

import tempfile
from pathlib import Path

from aiida import orm
from aiida.engine import ExitCode, ToContext, WorkChain, while_


class RunMembraneMDWorkChain(WorkChain):
    """Run GROMACS MD steps from a CHARMM-GUI membrane input bundle.

    Dispatches to the appropriate engine adapter based on
    ``protocol.tracy.expected_engine``.  Adding a new engine means adding a
    ``prepare_<engine>_run_inputs`` adapter function and one new branch in
    ``setup`` — this WorkChain does not change.

    Steps are driven by ``protocol.tracy.md_steps``, which filters the
    CHARMM-GUI manifest.  The output structure and checkpoint of each completed
    step are passed automatically to the next.

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

        spec.input("md_input_bundle", valid_type=orm.FolderData)
        spec.input("protocol",        valid_type=orm.Dict)
        spec.input("code",            valid_type=orm.AbstractCode)
        spec.input("options",         valid_type=orm.Dict, required=False)

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
        manifest = [s for s in manifest if s["name"] in requested]

        if not manifest:
            self.report(f"No steps in bundle matched md_steps={requested}")
            return self.exit_codes.ERROR_MANIFEST_INVALID

        self.ctx.manifest = manifest
        self.ctx.run_inputs = prepare_fn(self.inputs.md_input_bundle)
        self.ctx.engine = engine
        self.ctx.current_step_index = 0
        self.ctx.completed_steps = []
        self.report(f"Setup complete. Engine={engine}, steps={[s['name'] for s in manifest]}")

    def should_run_next_step(self) -> bool:
        return self.ctx.current_step_index < len(self.ctx.manifest)

    def run_next_step(self):
        step = self.ctx.manifest[self.ctx.current_step_index]
        mdp_file = self._extract_file_from_bundle(step["mdp"])

        if self.ctx.engine == "gromacs":
            from tracy.workflows.gromacs_run import GromacsRunWorkChain
            engine_wc = GromacsRunWorkChain

        overrides = self.ctx.protocol.get("tracy", {}).get("mdp_overrides", {}).get(step["name"])
        if overrides:
            from tracy.adapters.gromacs import patch_mdp
            mdp_file = patch_mdp(mdp_file, orm.Dict(overrides))

        inputs: dict = {
            "structure":     self.ctx.run_inputs["structure"],
            "topology":      self.ctx.run_inputs["topology"],
            "toppar":        self.ctx.run_inputs["toppar"],
            "mdp_file":      mdp_file,
            "gromacs_code":  self.inputs.code,
            "output_prefix": orm.Str(step["name"]),
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
            self.report(f"Step '{step['name']}' failed with exit status {wc.exit_status}")
            return self.exit_codes.ERROR_MD_STEP_FAILED

        self.ctx.run_inputs["structure"] = wc.outputs.output_structure
        if "checkpoint" in wc.outputs:
            self.ctx.run_inputs["checkpoint"] = wc.outputs.checkpoint

        self.ctx.completed_steps.append({"name": step["name"], "pk": wc.pk})
        self.ctx.current_step_index += 1
        self.report(f"Step '{step['name']}' finished OK (pk={wc.pk}).")

    def results(self) -> ExitCode | None:
        last_wc = self.ctx.current_step_wc

        md_results = self._collect_outputs_as_folder(last_wc)

        self.out("md_results", md_results.store())
        self.out("md_report", orm.Dict({
            "steps_run": [s["name"] for s in self.ctx.completed_steps],
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
