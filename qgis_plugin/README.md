# QGIS host integration

This package owns plugin lifecycle/registration, QGIS compatibility, dependency
diagnostics, metadata reading, coordinate/raster adapters and the external
Geosoft bridge. Qt widgets and language content live in ui/.

The root __init__.py remains the QGIS classFactory entry point. Scientific
Processing implementations remain in terraworkbench_core or their established
algorithm adapters; moving host modules does not change algorithm IDs or recipes.

The externally executed bridge is qgis_plugin/geosoft_bridge.py. It remains a
standalone script for the selected external Python runtime. Metadata and local
vendor discovery resolve against the project/plugin root.
