# QGIS interface

| Group | Modules |
| --- | --- |
| Workbench and process catalogue | workflow_dock.py; process_centre.py |
| Scientific operation/workflow forms | core_job_dialog.py; core_workflow_dialog.py; core_parameter_form.py; core_field_editor.py; depth_grid_parameter_form.py |
| Survey workspace and channel workflows | survey_workspace_dialog.py; channel_filter_dialog.py; channel_pipeline_dialog.py; survey_coordinates_dialog.py; survey_profile_widget.py |
| Complete chapter reader and offscreen evidence | full_manual.py; evidence_api.py; full books and localized assets are under docs/manuals |
| Import and raster review | text_import_dialog.py; raster_stage_review.py |
| Preferences, dependencies and history | settings_dialog.py; dependency_dialog.py; task_history_widget.py |
| Resource root | _paths.py |

Widgets orchestrate user input and display. Numerical algorithms live in
terraworkbench_core/ and QGIS Processing adapters in algorithms/.
Presentation contracts, language content and parameter readers also live here.

Use PLUGIN_ROOT from _paths.py for bundled resources. Keep Processing IDs,
saved recipe keys and user-data locations stable when changing UI structure.
The [repository guide](../docs/development/repository_structure.md) describes packaging
and the full development boundary.
