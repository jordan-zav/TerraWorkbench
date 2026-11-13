"""Validate and package TerraWorkbench for the official QGIS repository."""

from __future__ import annotations

import argparse
import ast
import configparser
import re
import sys
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = "TerraWorkbench"
METADATA_PATH = ROOT / "metadata.txt"
DIST_DIR = ROOT / "dist"
MAX_PACKAGE_BYTES = 25 * 1024 * 1024
VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?\Z")

REQUIRED_METADATA = (
    "name",
    "qgisMinimumVersion",
    "description",
    "about",
    "version",
    "author",
    "email",
    "repository",
)

PLUGIN_FILES = (
    "qgis_plugin/gx_runtime_check.py",
    "assets/runtime/SHA256SUMS",
    "assets/runtime/SHA512SUMS",
    "assets/legacy/icon.svg",
    "compat/__init__.py",
    "compat/redirects.py",
    "qgis_plugin/__init__.py",
    "ui/__init__.py",
    "ui/_paths.py",
    "__init__.py",
    "metadata.txt",
    "qgis_plugin/metadata_utils.py",
    "qgis_plugin/delimited_text.py",
    "ui/i18n.py",
    "ui/knowledge_content.py",
    "ui/knowledge_methods.py",
    "ui/core_presentation.py",
    "ui/core_parameter_schema.py",
    "ui/core_field_editor.py",
    "ui/npz_inspector.py",
    "ui/evidence_api.py",
    "ui/full_manual.py",
    "ui/parameter_json.py",
    "qgis_plugin/qgis_compat.py",
    "qgis_plugin/crs_utils.py",
    "qgis_plugin/plugin.py",
    "qgis_plugin/provider.py",
    "qgis_plugin/raster_io.py",
    "qgis_plugin/hillshade.py",
    "compat/spectral.py",
    "compat/line_processing.py",
    "qgis_plugin/microlevel.py",
    "compat/basic_processing.py",
    "compat/gridding_methods.py",
    "compat/survey_store.py",
    "compat/magnetic_pipeline.py",
    "compat/survey_grid_pipeline.py",
    "compat/survey_correction_pipeline.py",
    "compat/channel_filters.py",
    "ui/channel_filter_dialog.py",
    "ui/channel_pipeline_dialog.py",
    "compat/text_import.py",
    "ui/text_import_dialog.py",
    "ui/survey_coordinates_dialog.py",
    "ui/survey_workspace_dialog.py",
    "ui/survey_sheet.py",
    "ui/survey_profile_widget.py",
    "ui/process_centre.py",
    "ui/core_job_dialog.py",
    "ui/core_workflow_dialog.py",
    "ui/core_parameter_form.py",
    "ui/depth_grid_parameter_form.py",
    "ui/raster_stage_review.py",
    "ui/task_history_widget.py",
    "compat/inversion_core.py",
    "compat/gravity_corrections.py",
    "compat/isostasy.py",
    "compat/radiometry.py",
    "compat/survey_corrections.py",
    "compat/preprocessing.py",
    "qgis_plugin/dependencies.py",
    "ui/dependency_dialog.py",
    "ui/settings_dialog.py",
    "ui/workflow_dock.py",
    "ui/hillshade.py",
    "qgis_plugin/data_import.py",
    "qgis_plugin/geosoft_runtime.py",
    "qgis_plugin/geosoft_bridge.py",
    "qgis_plugin/gdb_archive_gx.py",
    "qgis_plugin/gx_runtime_setup.py",
    "terraworkbench_core/gdb_archive.py",
    "scripts/convert_gdb_archive.py",
    "assets/branding/README.md",
    "assets/branding/terraworkbench-logo.png",
    "assets/branding/terraworkbench-icon.png",
    "LICENSE",
    "README.md",
    "README.es.md",
    "README.pt.md",
    "requirements/base.txt",
    "requirements/inversion.txt",
    "docs/legal/THIRD_PARTY_LICENSES.md",
)

DOC_FILES = (
    "docs/path_migrations.json",
    "docs/manual_es/README.md",
    "docs/guides/README.md",
    "docs/reference/README.md",
    "docs/development/README.md",
    "docs/research/README.md",
    "docs/research/PAPER_BACKED_MAGNETIC_METHODS.md",
    "docs/validation/README.md",
    "docs/legal/README.md",
    "docs/guides/api_evidence.md",
    "docs/validation/reports/lagged_irls.md",
    "docs/validation/records/public/lagged_irls_20261102.json",
    "docs/validation/reports/mvi_outer_sensitivity.md",
    "docs/validation/records/mvi_outer_20261105.json",
    "docs/validation/reports/mvi_acceptance.md",
    "docs/validation/records/mvi_acceptance_20261105.json",
    "docs/validation/reports/mvi_stability.md",
    "docs/validation/records/public/mvi_stability_20261102.json",
    "docs/reference/methods/spherical_mvi.md",
    "docs/validation/reports/mvi_causal_diagnosis.md",
    "docs/validation/records/mvi_causal_diagnosis_20261102.json",
    "docs/validation/records/spherical_mvi_20261029.json",
    "docs/validation/reports/mvi_reference_validation.md",
    "docs/validation/records/mvi_reference_20261029.json",
    "docs/reference/methods/regularization_conventions.md",
    "docs/validation/records/voxel_recovery_20261028.json",
    "docs/validation/reports/voxel_recovery_validation.md",
    "docs/validation/reports/inversion3d_extensions.md",
    "docs/validation/reports/2d_extensions.md",
    "docs/validation/records/README.md",
    "docs/validation/records/2d_extensions_20261028.json",
    "docs/validation/records/inversion3d_extensions_20261028.json",
    "docs/validation/records/inversion3d_methods_20261028.json",
    "docs/validation/records/public_processing_20261028.json",
    "docs/validation/records/public_inversion_20261028.json",
    "docs/README.md",
    "docs/development/repository_structure.md",
    "docs/reference/methods/ip_stacking.md",
    "docs/reference/methods/ip_current_history.md",
    "docs/reference/methods/dispersive_ip_mvi.md",
    "docs/validation/reports/inversion_methods_validation.md",
    "docs/validation/reports/inversion_convergence_resolution.md",
    "docs/validation/reports/public_inversion_benchmark.md",
    "docs/validation/reports/inversion_validation.md",
    "docs/validation/reports/numerical_capacity_validation.md",
    "docs/validation/reports/processing_overlap_audit.md",
    "docs/handbook/handbook_sources.json",
    "docs/guides/geophysical_workbench_gui.md",
    "docs/guides/survey_explorer.md",
    "docs/research/core_expansion_implementation.md",
    "docs/research/geophysics_expansion.md",
    "docs/research/geophysics_backlog.json",
    "docs/reference/methods/source_depth.md",
    "docs/development/standalone_inversion.md",
    "docs/development/scientific_core.md",
    "docs/development/standalone_acquisition.md",
    "docs/reference/methods/magnetic_component_api.md",
    "docs/reference/methods/compact_magnetics.md",
    "docs/reference/methods/structural_attributes.md",
    "docs/reference/methods/apparent_properties.md",
    "docs/guides/core_workflows.md",
    "docs/reference/methods/adaptive_terrain.md",
    "docs/reference/methods/isostasy.md",
    "docs/reference/methods/interpolation_methods.md",
    "docs/guides/basic_processing_migration.md",
    "docs/guides/survey_workspaces.md",
    "docs/assets/filter-stack.png",
    "docs/handbook/README.md",
    "docs/guides/localization.md",
    "docs/handbook/handbook_en.md",
    "docs/handbook/handbook_es.md",
    "docs/handbook/handbook_pt.md",
    "docs/handbook/geofisica_potencial_referencia.md",
    "docs/handbook/potential_fields_reference_en.md",
    "docs/handbook/potential_fields_reference_pt.md",
    "docs/handbook/repositorios_referencia.md",
    "docs/handbook/roadmap_cobertura.md",
    "docs/handbook/sources.json",
)

EMBEDDED_QPIP_FILES = (
    "embedded_qpip/__init__.py",
    "embedded_qpip/manager.py",
    "embedded_qpip/install_progress.py",
    "embedded_qpip/pip_progress.py",
    "embedded_qpip/NOTICE.md",
    "embedded_qpip/LICENSE.qpip",
)

SAMPLE_FILES = (
    "sample_data/workflows/gravity_layer.json",
    "sample_data/README.md",
    "sample_data/synthetic/manifest.json",
    "sample_data/synthetic/synthetic_magnetic_anomaly.tif",
    "sample_data/synthetic/synthetic_gravity_anomaly.tif",
    "sample_data/synthetic/synthetic_dem.tif",
    "sample_data/synthetic/synthetic_potassium.tif",
    "sample_data/synthetic/synthetic_equivalent_uranium.tif",
    "sample_data/synthetic/synthetic_equivalent_thorium.tif",
    "sample_data/synthetic/synthetic_survey_points.csv",
)


def load_metadata() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    with METADATA_PATH.open(encoding="utf-8") as metadata_file:
        parser.read_file(metadata_file)
    return parser


def current_version() -> str:
    parser = load_metadata()
    if "general" not in parser:
        return ""
    return parser["general"].get("version", "").strip()


def update_version(version: str) -> None:
    content = METADATA_PATH.read_text(encoding="utf-8")
    updated, replacements = re.subn(
        r"(?im)^version=.*$",
        f"version={version}",
        content,
        count=1,
    )
    if replacements != 1:
        raise RuntimeError("metadata.txt must contain exactly one version field")
    with METADATA_PATH.open("w", encoding="utf-8", newline="\n") as metadata_file:
        metadata_file.write(updated)
    replacements = (
        (
            ROOT / "README.md",
            (
                (r"Version [0-9A-Za-z.+-]+", f"Version {version}"),
                (r"version-[0-9A-Za-z.+-]+-2563eb", f"version-{version}-2563eb"),
                (
                    r"Version \*\*[0-9A-Za-z.+-]+\*\* is the current release",
                    f"Version **{version}** is the current release",
                ),
            ),
        ),
        (
            ROOT / "docs" / "handbook" / "geofisica_potencial_referencia.md",
            (
                (
                    r"Versión y validación actual \(v[0-9A-Za-z.+-]+\)",
                    f"Versión y validación actual (v{version})",
                ),
            ),
        ),
    )
    for path, patterns in replacements:
        value = path.read_text(encoding="utf-8")
        for pattern, replacement in patterns:
            value, count = re.subn(pattern, replacement, value, count=1)
            if count != 1:
                raise RuntimeError(
                    f"Could not synchronize version marker in {path.relative_to(ROOT)}"
                )
        path.write_text(value, encoding="utf-8", newline="\n")


def runtime_document(relative: str) -> bool:
    """Leave repository provenance in public source, outside the runtime ZIP.

    The manual reader consumes coverage.json; the other metadata, figure
    digests, API inventory/notes and validation records are build/audit inputs.
    Keep this filter separate from the authoritative public export manifest.
    """
    if relative == "docs/manuals/_meta/coverage.json":
        return True
    return not (
        relative.endswith(".json")
        and (
            relative.startswith(("docs/manuals/_meta/", "docs/reference/api/notes/",
                                 "docs/validation/records/"))
            or relative == "docs/reference/api/core_inventory.json"
            or (relative.startswith("docs/manuals/assets/")
                and relative.endswith("/figuras.json"))
        )
    )


def package_files() -> list[Path]:
    # The explicit public source manifest is authoritative, including in a private checkout.
    try:
        from scripts.public_files import read_manifest
    except ModuleNotFoundError:
        from public_files import read_manifest
    return [ROOT / relative for relative in read_manifest(ROOT)
            if runtime_document(relative) and (relative.startswith(("algorithms/", "terraworkbench_core/", "compat/",
                                    "qgis_plugin/", "ui/", "embedded_qpip/", "assets/",
                                    "docs/", "sample_data/", "requirements/"))
            or relative in PLUGIN_FILES or relative in ("__init__.py", "metadata.txt", "LICENSE", "README.md",
                            "README.es.md", "README.pt.md", "public_manifest.txt"))]


def validate_source() -> list[str]:
    errors: list[str] = []
    try:
        metadata = load_metadata()
    except (OSError, configparser.Error) as error:
        return [f"metadata.txt could not be read: {error}"]

    if "general" not in metadata:
        return ["metadata.txt is missing the [general] section"]

    general = metadata["general"]
    for key in REQUIRED_METADATA:
        if not general.get(key, "").strip():
            errors.append(f"metadata.txt is missing required field: {key}")

    version = general.get("version", "").strip()
    if version and VERSION_PATTERN.fullmatch(version) is None:
        errors.append(f"invalid semantic version: {version}")
    if general.get("plugin_dependencies", "").strip():
        errors.append(
            "plugin_dependencies must remain empty while the dependency manager is embedded"
        )
    if "requirements/base.txt" not in general.get("about", ""):
        errors.append(
            "about must explain the external requirements/base.txt dependency"
        )
    if general.get("qgisMaximumVersion", "").strip() != "3.99":
        errors.append(
            "qgisMaximumVersion must remain 3.99 until QGIS 4 runtime tests exist"
        )
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if (
        f"Version {version}" not in readme
        or f"version-{version}-2563eb" not in readme
        or (f"Version **{version}** is the current release" not in readme)
    ):
        errors.append("README version markers do not match metadata.txt")
    if not general.get("changelog", "").lstrip().startswith(version):
        errors.append("metadata changelog must start with the current version")

    for source in package_files():
        if not source.is_file():
            errors.append(
                f"required package file is missing: {source.relative_to(ROOT)}"
            )
        elif source.suffix == ".py":
            try:
                ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            except (OSError, SyntaxError, UnicodeError) as error:
                errors.append(
                    f"invalid Python source {source.relative_to(ROOT)}: {error}"
                )

    errors.extend(missing_internal_imports())
    return errors


def missing_internal_imports() -> list[str]:
    """Report relative imports that point at plugin modules left out of the ZIP.

    PLUGIN_FILES alone does not decide the archive contents; public_manifest.txt
    does. A module listed in one but not the other installs a plugin that fails
    in classFactory, so check every packaged module's relative imports.
    """
    packaged = {source.relative_to(ROOT).as_posix() for source in package_files()}
    errors = [
        f"PLUGIN_FILES entry is not packaged (add it to public_manifest.txt): {name}"
        for name in PLUGIN_FILES
        if name not in packaged
    ]
    for relative in sorted(packaged):
        if not relative.endswith(".py"):
            continue
        try:
            tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeError):
            continue
        package = PurePosixPath(relative).parent
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.level:
                continue
            base = package
            for _ in range(node.level - 1):
                base = base.parent
            targets = (
                [node.module.split(".")]
                if node.module
                else [[alias.name] for alias in node.names]
            )
            for parts in targets:
                target = base.joinpath(*parts)
                if str(target) == ".":
                    continue
                candidates = (f"{target}.py", f"{target}/__init__.py")
                if not any(candidate in packaged for candidate in candidates):
                    if node.module is None and (base / "__init__.py").as_posix() in packaged:
                        continue
                    errors.append(
                        f"{relative} imports {target.as_posix().replace('/', '.')}, "
                        "which is not packaged (add it to public_manifest.txt)"
                    )
    return errors


def validate_archive(archive: Path, expected_version: str) -> list[str]:
    try:
        from scripts.public_files import content_findings, forbidden_path, read_manifest
    except ModuleNotFoundError:
        from public_files import content_findings, forbidden_path, read_manifest

    errors: list[str] = []
    manifest = set(read_manifest(ROOT))
    expected_entries = {
        str(PurePosixPath(PLUGIN_ID) / source.relative_to(ROOT).as_posix())
        for source in package_files()
    }
    with ZipFile(archive) as bundle:
        entries = set(bundle.namelist())
        if len(entries) != len(bundle.namelist()):
            errors.append("archive contains duplicate entries")
        for entry in entries:
            relative = entry.removeprefix(PLUGIN_ID + "/")
            if relative not in manifest or forbidden_path(relative):
                errors.append("archive entry is outside public manifest: " + entry)
            errors.extend(content_findings(entry, bundle.read(entry)))
        if entries != expected_entries:
            missing = sorted(expected_entries - entries)
            unexpected = sorted(entries - expected_entries)
            if missing:
                errors.append(f"archive is missing files: {', '.join(missing)}")
            if unexpected:
                errors.append(
                    f"archive contains unexpected files: {', '.join(unexpected)}"
                )

        metadata_entry = f"{PLUGIN_ID}/metadata.txt"
        packaged_parser = configparser.ConfigParser(interpolation=None)
        packaged_parser.read_string(bundle.read(metadata_entry).decode("utf-8"))
        packaged_version = packaged_parser["general"].get("version", "").strip()
        if packaged_version != expected_version:
            errors.append(
                f"archive metadata version {packaged_version!r} does not match {expected_version!r}"
            )

    if archive.stat().st_size > MAX_PACKAGE_BYTES:
        errors.append("archive exceeds the official QGIS 25 MB package limit")
    return errors


def build_archive() -> Path:
    version = current_version()
    DIST_DIR.mkdir(exist_ok=True)
    archive = DIST_DIR / f"{PLUGIN_ID}-{version}.zip"
    if archive.exists():
        archive.unlink()

    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as bundle:
        for source in package_files():
            archive_name = (
                PurePosixPath(PLUGIN_ID) / source.relative_to(ROOT).as_posix()
            )
            bundle.write(source, str(archive_name))
    return archive


def fail(errors: list[str]) -> None:
    print("\nERROR: release validation failed:", file=sys.stderr)
    for error in errors:
        print(f" - {error}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interactive", action="store_true", help="prompt for version")
    parser.add_argument("--version", help="set the package version non-interactively")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="validate source without creating an archive",
    )
    args = parser.parse_args()

    version = args.version.strip() if args.version else current_version()
    if args.interactive:
        entered = input(f"Version [{version}]: ").strip()
        if entered:
            version = entered
    if VERSION_PATTERN.fullmatch(version) is None:
        fail([f"invalid semantic version: {version!r}"])
    if version != current_version():
        update_version(version)

    errors = validate_source()
    if errors:
        fail(errors)
    print(f"OK: source and metadata validated for TerraWorkbench {version}.")

    if args.check_only:
        return

    archive = build_archive()
    errors = validate_archive(archive, version)
    if errors:
        archive.unlink(missing_ok=True)
        fail(errors)
    print(f"OK: {archive} ({archive.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
