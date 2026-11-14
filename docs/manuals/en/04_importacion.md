# 4. Importing text, GRD and geospatial data

[English](../en/04_importacion.md) · [Español](../es/04_importacion.md) · [Português](../pt/04_importacion.md)

## Inspect before loading

Automatic detection suggests encoding, separator, header row, first data row and types. It uses a file sample; a plausible suggestion does not guarantee that later rows have the same structure. Review numbered physical lines, duplicate names, signs, missing values and decimal separator.

Survey import uses survey_text_import. The historical text_import module provides a different, pandas-based table API; do not interchange their options or assume their outputs are SurveyStore objects. The API reference retains both signatures.

## Text workflow

1. Preserve the original and record size, date and hash.
2. Inspect the file; review comma, semicolon, tab or whitespace separation.
3. Identify comments and header rows, including line sections where present.
4. Declare types, units and XY, Z, time, line and sensor columns.
5. Preview converted rows and check nulls and names.
6. Import into a new database and compare row counts, ranges and samples.

An identifier such as 001 may be meaningful text. Integer conversion discards leading zeros. An exported FID is not necessarily time or distance, and Z may describe platform height, terrain or another quantity.

## GRD and other raster formats

The GRD extension covers multiple encodings. The adapter must recognise the format; do not treat every GRD file as a Geosoft binary raster. Check dimensions, georeferencing, recovered CRS, title, units and NoData before processing.

The plugin workflow can create a working GeoTIFF from GRD or other compatible formats. The original remains intact. Export temporary results to a chosen folder when they must be retained. Record conversion, scale/offset and any resampling.

An irregular XYZ table needs gridding. A regular-grid reader must not silently fill missing positions or invent resolution. Diagnose missing rows or columns explicitly.

## External databases

An Esri FileGDB contains layers or tables accessible through a compatible geospatial stack. A single-file Geosoft GeoDatabase uses the optional inventory/export bridge. Exporting channels to an open format does not mean the Core performs numerical processing with proprietary software.

## Import acceptance

An import is reviewed when expected counts, critical columns, units, coordinates and sampled values agree. Distinguish syntax errors from physically implausible values: both need treatment, but not the same correction.

Further reading: [workspaces](../../guides/survey_workspaces.md), [importers and architecture](../../development/scientific_core.md) and [GDAL model](https://gdal.org/en/stable/user/raster_data_model.html).

## Related implementation

[survey_text_import](../../../terraworkbench_core/survey_text_import.py), [text_import](../../../terraworkbench_core/text_import.py)

---

[Contents](README.md) · [Previous](03_coordenadas.md) · [Next](05_bases_canales.md)

## Open archive of a Geosoft GDB

Convert to open archive (recommended) creates a SurveyStore folder with a SQLite catalogue, native typed Parquet, archive.json and verification.json. It preserves integers, float32/64, text, fixed-size spectra, dummies as nulls and each line/channel's own fiducials. No silent resampling takes place. A second GX read compares every channel; only zero differences and no unreadable channels produce an accepted archive.

On Windows, GDB conversion requires Seequent Connect and a free Seequent ID account. The dependency manager asks for consent before downloading the full GX 2024.2 runtime (about 345 MiB). If .NET 6 is missing, install [Microsoft .NET 6 Desktop Runtime x64](https://dotnet.microsoft.com/en-us/download/dotnet/6.0), which includes the desktop and core frameworks. If an organization account prompts for checkout, select While app is running. The checkout ends when GX closes. To work without a Seequent account, import XYZ or CSV.

Open converted survey archive accepts archive.json, catalog.sqlite or Parquet and creates layers through the existing workflow. The API also accepts the folder. Open archives work without Geosoft or a Seequent ID. Legacy CSV remains available and omits some metadata.

[Schema, verification, CLI and terms](../../development/gdb_open_archive.md).
