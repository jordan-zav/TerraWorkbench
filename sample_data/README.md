# TerraWorkbench sample data

## Bundled synthetic examples

The synthetic directory contains educational magnetic, gravity, DEM and calibrated radiometric GeoTIFFs and survey-like CSV points in EPSG:32718. They were generated specifically for TerraWorkbench and released under [CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/). They are artificial values, not observations or geological evidence. Their provenance and units are in [the manifest](synthetic/manifest.json).

Regenerate explicitly using the QGIS Python interpreter: <code>python scripts/generate_sample_data.py</code>. Generation is separate from ordinary validation and should be performed on a working copy.

## External surveys

No NRCan grids or other third-party source surveys are distributed in the public edition. Private development data remain in the development archive. The plugin hides unavailable NRCan example actions; generic GRD import continues to accept a legitimate file chosen by the user. User-selected external test directories are optional and never part of a release package.
