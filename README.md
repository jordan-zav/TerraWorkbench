# TerraWorkbench

TerraWorkbench is an independent QGIS Processing provider for geophysical data. Its first module exposes selected functionality from the Harmonica library as native QGIS algorithms, including batch processing and graphical Model Designer support.

The project is not an official product of Fatiando a Terra.

## MAG exploration filters

- DX and DY first horizontal derivatives
- DZ first and DZ2 second vertical derivatives
- UC500m upward continuation
- RS residual enhancement
- THDR total horizontal derivative
- Tilt angle
- 45HG directional horizontal gradient
- AS / ASA analytic signal amplitude
- TDX horizontal tilt angle
- Theta angle map

The provider also includes Bouguer correction, configurable upward continuation,
Gaussian low-pass and high-pass filters, reduction to the pole, and configurable
directional derivatives.

## GRAV exploration filters

- DX and DY first horizontal derivatives
- DZ first and DZ2 second vertical derivatives
- UC500m upward continuation
- Gaussian regional field
- Residual field from upward-continuation subtraction
- THDR total horizontal derivative
- Tilt angle
- TGA total gradient amplitude

## Requirements

- QGIS 3.28 or newer
- Harmonica 0.7
- Dependencies installed in the Python environment used by QGIS

TerraWorkbench declares QPIP as a QGIS plugin dependency. During installation, QGIS installs QPIP and QPIP reads requirements.txt, checks the active profile and offers to install any missing Python packages. The user must approve that dependency installation.

The scientific packages are installed in the QGIS user profile and are not bundled inside the TerraWorkbench archive. This avoids replacing the GDAL, NumPy and SciPy versions supplied by QGIS and allows separate dependency sets in different QGIS profiles.

## Installation for development

Copy the complete TerraWorkbench folder into the active QGIS profile under python/plugins, then enable TerraWorkbench in the Plugin Manager. Its algorithms appear in the Processing Toolbox.

On the configured Windows development machine, install_update_open_qgis.bat performs the local workflow automatically: it copies or updates the plugin in the last active profile, checks Python requirements, enables the plugin and opens QGIS. Passing --no-launch performs the same update without opening QGIS. build_dist.bat creates a versioned installation ZIP in dist.

## Raster requirements

FFT tools require an evenly spaced north-up raster in a projected CRS. Input grids must not contain NoData or non-finite cells. Bouguer correction accepts NoData and preserves it in the output.

## License

TerraWorkbench is released under GPL-3.0-or-later. Harmonica is maintained separately by the Fatiando a Terra project under its own license. Runtime license information is recorded in THIRD_PARTY_LICENSES.md.
