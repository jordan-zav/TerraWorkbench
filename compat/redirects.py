"""Lazy historical import aliases; short names are explicitly opt-in."""

from importlib import import_module
from importlib.abc import Loader, MetaPathFinder
from importlib.util import spec_from_loader
import sys

MODULE_PATHS = {
    "basic_processing": "compat.basic_processing",
    "channel_filters": "compat.channel_filters",
    "gravity_corrections": "compat.gravity_corrections",
    "gridding_methods": "compat.gridding_methods",
    "inversion_core": "compat.inversion_core",
    "isostasy": "compat.isostasy",
    "line_processing": "compat.line_processing",
    "magnetic_pipeline": "compat.magnetic_pipeline",
    "preprocessing": "compat.preprocessing",
    "radiometry": "compat.radiometry",
    "spectral": "compat.spectral",
    "survey_correction_pipeline": "compat.survey_correction_pipeline",
    "survey_corrections": "compat.survey_corrections",
    "survey_grid_pipeline": "compat.survey_grid_pipeline",
    "survey_store": "compat.survey_store",
    "text_import": "compat.text_import",
    "core_parameter_schema": "ui.core_parameter_schema",
    "core_presentation": "ui.core_presentation",
    "i18n": "ui.i18n",
    "knowledge_content": "ui.knowledge_content",
    "knowledge_methods": "ui.knowledge_methods",
    "npz_inspector": "ui.npz_inspector",
    "parameter_json": "ui.parameter_json",
    "crs_utils": "qgis_plugin.crs_utils",
    "data_import": "qgis_plugin.data_import",
    "delimited_text": "qgis_plugin.delimited_text",
    "dependencies": "qgis_plugin.dependencies",
    "geosoft_bridge": "qgis_plugin.geosoft_bridge",
    "geosoft_runtime": "qgis_plugin.geosoft_runtime",
    "metadata_utils": "qgis_plugin.metadata_utils",
    "microlevel": "qgis_plugin.microlevel",
    "plugin": "qgis_plugin.plugin",
    "provider": "qgis_plugin.provider",
    "qgis_compat": "qgis_plugin.qgis_compat",
    "raster_io": "qgis_plugin.raster_io",
}
for _name in (
    "channel_filter_dialog",
    "channel_pipeline_dialog",
    "core_field_editor",
    "core_job_dialog",
    "core_parameter_form",
    "core_workflow_dialog",
    "dependency_dialog",
    "depth_grid_parameter_form",
    "process_centre",
    "raster_stage_review",
    "settings_dialog",
    "survey_coordinates_dialog",
    "survey_profile_widget",
    "survey_workspace_dialog",
    "task_history_widget",
    "text_import_dialog",
    "workflow_dock",
):
    MODULE_PATHS[_name] = "ui." + _name


class _AliasLoader(Loader):
    def __init__(self, target):
        self.target = target

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        # Replace only the alias stub; keep canonical module identity/metadata.
        sys.modules[module.__name__] = import_module(self.target)


class _AliasFinder(MetaPathFinder):
    def __init__(self, aliases):
        self._terraworkbench_aliases = aliases

    def find_spec(self, fullname, path=None, target=None):
        destination = self._terraworkbench_aliases.get(fullname)
        if destination is None:
            return None
        return spec_from_loader(fullname, _AliasLoader(destination))


def install_legacy_imports(package_name=None):
    """Lazily enable old names, scoped to a plugin or explicitly to a checkout.

    With no package_name this opts into short legacy names. New scientific code
    should use terraworkbench_core.* directly. No Qt/engine modules load eagerly.
    """
    prefix = package_name + "." if package_name else ""
    aliases = {prefix + old: prefix + new for old, new in MODULE_PATHS.items()}
    for finder in sys.meta_path:
        if getattr(finder, "_terraworkbench_aliases", None) == aliases:
            return finder
    finder = _AliasFinder(aliases)
    sys.meta_path.insert(0, finder)
    return finder
