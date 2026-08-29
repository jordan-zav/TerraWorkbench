# TerraWorkbench sample data

## Bundled synthetic examples

The `synthetic/` directory is generated specifically for TerraWorkbench and is
released under CC0-1.0. It contains aligned magnetic, gravity and DEM GeoTIFFs
plus survey-like CSV points in EPSG:32718. These files are intentionally small
and are suitable for import, FFT filters, Filter Stack and UI demonstrations.

They are synthetic educational values, not observations and not evidence for
geological interpretation.

Regenerate them with QGIS Python:

```powershell
$qgisRoot = & .\scripts\find_qgis.ps1
& "$qgisRoot\bin\python-qgis-ltr.bat" scripts\generate_sample_data.py
```

## Local reference datasets

`local_private/` may contain convenient copies of the user's source surveys.
It is ignored by Git, excluded by the local installer and excluded from release
ZIPs. TerraWorkbench can discover this directory automatically in a development
checkout, or any external directory selected under **Settings > Integrations >
Local test datasets**. Original source files remain unchanged.

The Hydraulic GRD examples came from Natural Resources Canada's Geophysical
Data portal and Geological Survey of Canada Open File 5290. That portal permits
reproduction, including commercial use, under its dataset-specific usage
conditions and the Open Government Licence - Canada. They are published under
`nrcan/` with [`nrcan/NOTICE.md`](nrcan/NOTICE.md), original XML metadata,
checksums and the required citation.

The Mount Milligan files identify Geoscience BC Report 2009-7 as their source.
They remain under ignored `local_private/` because their download page does not
state an explicit redistribution licence. The official project page is:
<https://www.geosciencebc.com/projects/2008-032/>. Public download availability
must not be treated as permission to mirror a third party's files.
