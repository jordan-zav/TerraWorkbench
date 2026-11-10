# 2. Installation, dependencies and environment

[English](../en/02_instalacion.md) · [Español](../es/02_instalacion.md) · [Português](../pt/02_instalacion.md)

The first dependency installation can take about 10 minutes, depending on connection speed and available caches.

## Choose an entry point

The QGIS plugin and standalone Core distribution are related products with different versions. The plugin version is in metadata.txt; the Python package version is in pyproject.toml. Their numbers need not match. QGIS compatibility declarations do not replace checking the Python interpreter used by an optional engine.

The Core declares Python 3.10 or later and requires NumPy and SciPy. The inversion, electrical and EM extras are declared for Python 3.11 or later, with SimPEG 0.25, discretize 0.12 and choclo 0.3 within the project's specified ranges. Always inspect the [installation contract](../../../pyproject.toml) before pinning an environment.

## Standalone installation

From a dedicated Python environment, in the repository root:

    python -m pip install .
    python -m pip install ".[storage,coordinates,geomagnetism]"

For inversion, use the inversion extra with a compatible Python. These commands explain installation; they should not be run indiscriminately against QGIS Python in an attempt to repair native libraries.

| Requirement | Dependency or extra |
| --- | --- |
| Catalogue and Parquet channels | storage: PyArrow |
| Horizontal transformation | coordinates: PyProj |
| IGRF main field | geomagnetism: ppigrf |
| Prisms and equivalent sources | prisms: Harmonica and a compatible environment |
| Potential-field inversion | inversion: SimPEG, discretize, choclo |
| Historical table API | tables: pandas |
| LAS well logs | borehole: lasio |
| Image features and wavelets | structure, archaeology as required by the operation |
| Raster and geospatial export | GDAL or rasterio, depending on the adapter |

Declaring an extra does not mean all its engines are imported at startup. Optional engines load when used. Record the versions actually installed, not just requirement ranges.

## Plugin installation

Obtain a ZIP validated by scripts/package_plugin.py and install it using QGIS's install-from-ZIP mechanism. Check that the TerraWorkbench provider appears in Processing and its version matches metadata.txt. A manually copied code folder can conceal missing dependencies or an older installation still in use.

GRD, GeoTIFF, FileGDB and layer adapters require a compatible native runtime. Optional Geosoft GeoDatabase access uses its read/export bridge; that bridge is not the Core numerical engine. A Geosoft GeoDatabase and an Esri FileGDB are different formats.

## Complete uninstallation

First open the TerraWorkbench dependency manager and select **Remove dependencies and preferences**. Review the exact active-profile folder, file count, total bytes and settings keys, then confirm. Restart QGIS as instructed; if the plugin remains installed it will ask to reinstall dependencies. To uninstall completely, remove TerraWorkbench through QGIS's **Manage and Install Plugins** after the cleanup.

Manual alternative: close QGIS and remove only <code>ACTIVE_PROFILE/python/dependencies/TerraWorkbench/PYTHON_MAJOR.MINOR</code>, using the active profile shown by QGIS (including a custom profiles root). Remove only keys under <code>TerraWorkbench/</code> from that profile's QSettings configuration: defaultOutputDirectory, keepIntermediate, defaultBand, openInspectorAfterAdd, confirmClearStack, addFinalResultToProject, showScientificTooltips, geosoftLocation, localTestDataDirectory, language, dependencyDialogVersion and surveyWorkspace. Review any additional keys in the same namespace. Preserve other profiles, Python versions and plugins. The automatic action refuses linked directories or junctions; it never deletes files during unload or simple deactivation. Loaded DLLs may prevent deletion on Windows; stop using the plugin, restart QGIS and use the manual alternative if needed.

## Minimum diagnostics

Check the actual Python executable, import only the required module, inspect its signature and run a small controlled example. For a native-library failure, preserve the original message and version inventory. Avoid repeated package installation without determining which interpreter received it.

On shared-resource machines, separate reusable caches from per-run temporaries and avoid concurrent writers to one workspace. Matrix memory is not total process memory.

Details: [scientific Core](../../development/scientific_core.md), [dependencies](../../../requirements/base.txt) and [third-party licences](../../legal/THIRD_PARTY_LICENSES.md).

---

[Contents](README.md) · [Previous](01_inicio.md) · [Next](03_coordenadas.md)
