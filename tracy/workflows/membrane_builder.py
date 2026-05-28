"""BuildMembraneWorkChain: membrane construction via CHARMM-GUI with GROMACS output."""

from __future__ import annotations

import tracy
from aiida import orm
from aiida.engine import ExitCode, ToContext, WorkChain, if_

from tracy.adapters.charmm_gui import (
    collect_charmm_gui_metadata,
    extract_gromacs_input_bundle,
)
from tracy.data.gromacs import validate_gromacs_input_bundle


class BuildMembraneWorkChain(WorkChain):
    """Build a membrane via CHARMM-GUI and extract a GROMACS-ready input bundle.

    Accepts a tracy protocol ``Dict`` describing membrane composition and settings.
    When ``charmm_gui_output`` is provided the CHARMM-GUI submission step is
    skipped, which allows development and testing without a live API call.

    Protocol shape (YAML/dict)::

        system:
          name: my_membrane
          description: ...

        charmm_gui:
          module: membrane_builder
          quick_bilayer:
            membtype: PMm          # OR upper/lower leaflet compositions
            membrane_only: true
            margin: 20.0
            ion_conc: 0.15
            ion_type: NaCl

        tracy:
          expected_engine: gromacs
          membrane_normal_axis: z
          require_gromacs_files: true

    Outputs:
        charmm_gui_output (FolderData): Raw CHARMM-GUI output folder.
        gromacs_input_bundle (FolderData): Extracted GROMACS-ready input files.
        system_metadata (Dict): Metadata about the membrane system.
        validation_report (Dict): Structured validation report for the GROMACS bundle.
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)

        spec.input(
            "protocol",
            valid_type=orm.Dict,
            help="Tracy protocol dict describing membrane composition and simulation settings.",
        )
        spec.input(
            "charmm_gui_output",
            valid_type=orm.FolderData,
            required=False,
            help=(
                "Pre-existing CHARMM-GUI output FolderData. "
                "If provided, CHARMM-GUI submission is skipped (development / testing mode)."
            ),
        )

        spec.outline(
            cls.setup,
            if_(cls.should_run_charmm_gui)(
                cls.submit_charmm_gui,
                cls.collect_charmm_gui_output,
            ),
            cls.extract_gromacs_bundle,
            cls.validate_outputs,
            cls.results,
        )

        spec.output(
            "charmm_gui_output",
            valid_type=orm.FolderData,
            help="Raw CHARMM-GUI output folder.",
        )
        spec.output(
            "gromacs_input_bundle",
            valid_type=orm.FolderData,
            help="GROMACS-ready input files extracted from the CHARMM-GUI output.",
        )
        spec.output(
            "system_metadata",
            valid_type=orm.Dict,
            help="Metadata about the membrane system.",
        )
        spec.output(
            "validation_report",
            valid_type=orm.Dict,
            help="Structured validation report for the GROMACS input bundle.",
        )

        spec.exit_code(
            400,
            "ERROR_MISSING_CHARMM_GUI_OUTPUT",
            message="CHARMM-GUI workflow produced no output.",
        )
        spec.exit_code(
            401,
            "ERROR_GROMACS_BUNDLE_EXTRACTION_FAILED",
            message="Could not extract a GROMACS input bundle from the CHARMM-GUI output.",
        )
        spec.exit_code(
            402,
            "ERROR_GROMACS_BUNDLE_INVALID",
            message="Extracted GROMACS input bundle failed validation.",
        )

    # -------------------------------------------------------------------------
    # Predicate helpers
    # -------------------------------------------------------------------------

    def should_run_charmm_gui(self) -> bool:
        """Return True when no pre-existing CHARMM-GUI output was provided."""
        return "charmm_gui_output" not in self.inputs

    # -------------------------------------------------------------------------
    # Outline steps
    # -------------------------------------------------------------------------

    def setup(self) -> None:
        """Cache the protocol dict and set per-run context flags."""
        protocol = self.inputs.protocol.get_dict()
        self.ctx.protocol = protocol
        self.ctx.require_gromacs_files = protocol.get("tracy", {}).get("require_gromacs_files", True)
        system_name = protocol.get("system", {}).get("name", "unnamed")
        self.report(f"Starting BuildMembraneWorkChain for system '{system_name}'.")

    def submit_charmm_gui(self):
        """Submit QuickBilayerWorkChain using parameters from the protocol."""
        from aiida_charmm_gui.workflows.quick_bilayer import QuickBilayerWorkChain

        quick_bilayer_conf = self.ctx.protocol.get("charmm_gui", {}).get("quick_bilayer", {})
        inputs = self._build_quick_bilayer_inputs(quick_bilayer_conf)
        calc = self.submit(QuickBilayerWorkChain, **inputs)
        self.report(f"Submitted QuickBilayerWorkChain (pk={calc.pk}).")
        return ToContext(charmm_gui_calc=calc)

    def collect_charmm_gui_output(self) -> ExitCode | None:
        """Wait for the CHARMM-GUI child workflow and cache its output FolderData."""
        calc = self.ctx.charmm_gui_calc
        if not calc.is_finished_ok:
            self.report(
                f"CHARMM-GUI workflow failed: exit_status={calc.exit_status}, "
                f"exit_message={calc.exit_message!r}."
            )
            return self.exit_codes.ERROR_MISSING_CHARMM_GUI_OUTPUT
        self.ctx.charmm_gui_folder = calc.outputs.results
        self.report(
            f"CHARMM-GUI job {calc.outputs.jobid.value!r} finished. "
            f"Results FolderData pk={calc.outputs.results.pk}."
        )

    def extract_gromacs_bundle(self) -> ExitCode | None:
        """Extract GROMACS-ready files from the CHARMM-GUI output FolderData."""
        if "charmm_gui_output" in self.inputs:
            folder = self.inputs.charmm_gui_output
        else:
            folder = self.ctx.charmm_gui_folder

        self.ctx.charmm_gui_folder = folder

        try:
            bundle = extract_gromacs_input_bundle(folder)
        except Exception as exc:
            self.report(f"GROMACS bundle extraction raised an exception: {exc}")
            return self.exit_codes.ERROR_GROMACS_BUNDLE_EXTRACTION_FAILED

        if bundle is None:
            self.report("No 'gromacs' directory found in CHARMM-GUI output.")
            return self.exit_codes.ERROR_GROMACS_BUNDLE_EXTRACTION_FAILED

        self.ctx.gromacs_bundle = bundle
        self.ctx.charmm_gui_metadata = collect_charmm_gui_metadata(folder)
        self.report("GROMACS input bundle extracted successfully.")

    def validate_outputs(self) -> ExitCode | None:
        """Validate the extracted GROMACS input bundle and cache the report."""
        report = validate_gromacs_input_bundle(self.ctx.gromacs_bundle)
        self.ctx.validation_report = report

        for warning in report.get("warnings", []):
            self.report(f"GROMACS bundle: {warning}")

        if not report["valid"] and self.ctx.require_gromacs_files:
            self.report(f"GROMACS bundle validation failed. Errors: {report['errors']}")
            return self.exit_codes.ERROR_GROMACS_BUNDLE_INVALID

    def results(self) -> None:
        """Store and expose all WorkChain outputs."""
        protocol = self.ctx.protocol
        system_conf = protocol.get("system", {})
        tracy_conf = protocol.get("tracy", {})
        charmm_gui_conf = protocol.get("charmm_gui", {})

        metadata: dict = {
            "system_name": system_conf.get("name", ""),
            "system_description": system_conf.get("description", ""),
            "charmm_gui_module": charmm_gui_conf.get("module", "membrane_builder"),
            "membrane_normal_axis": tracy_conf.get("membrane_normal_axis", "z"),
            "expected_engine": tracy_conf.get("expected_engine", "gromacs"),
            "tracy_version": tracy.__version__,
        }
        if "charmm_gui_metadata" in self.ctx:
            metadata.update(self.ctx.charmm_gui_metadata)

        self.out("charmm_gui_output", self.ctx.charmm_gui_folder)
        self.out("gromacs_input_bundle", self.ctx.gromacs_bundle.store())
        self.out("system_metadata", orm.Dict(metadata).store())
        self.out("validation_report", orm.Dict(self.ctx.validation_report).store())
        self.report("BuildMembraneWorkChain finished successfully.")

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _build_quick_bilayer_inputs(self, conf: dict) -> dict:
        """Map a protocol ``quick_bilayer`` section to QuickBilayerWorkChain AiiDA inputs."""
        inputs: dict = {}

        for str_key in ("membtype", "upper", "lower", "jobid_pdb", "ion_type"):
            if str_key in conf:
                inputs[str_key] = orm.Str(conf[str_key])

        inputs["membrane_only"] = orm.Bool(conf.get("membrane_only", True))
        inputs["margin"] = orm.Float(conf.get("margin", 20.0))

        for float_key in ("wdist", "ion_conc", "temperature"):
            if float_key in conf:
                inputs[float_key] = orm.Float(conf[float_key])

        for bool_key in (
            "prot_projection_upper",
            "prot_projection_lower",
            "ppm",
            "topology_in",
            "heteroatoms",
            "clone_job",
            "run_ff_converter",
            "charmmff_wyf_checked",
            "charmmff_hmr_checked",
            "charmm_mini",
        ):
            if bool_key in conf:
                inputs[bool_key] = orm.Bool(conf[bool_key])

        return inputs
