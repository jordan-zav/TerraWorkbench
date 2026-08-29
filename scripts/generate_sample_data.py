"""Generate small redistributable MAG/GRAV/DEM examples for TerraWorkbench."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from osgeo import gdal, osr

gdal.UseExceptions()

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "sample_data" / "synthetic"
ROWS = 96
COLS = 96
CELL_SIZE = 100.0
ORIGIN_X = 450_000.0
ORIGIN_Y = 8_650_000.0
CRS_EPSG = 32718
NODATA = -99999.0


def gaussian(x, y, center_x, center_y, sigma_x, sigma_y):
    """Return an axis-aligned Gaussian without external scientific dependencies."""
    return np.exp(
        -0.5
        * (
            ((x - center_x) / sigma_x) ** 2
            + ((y - center_y) / sigma_y) ** 2
        )
    )


def write_geotiff(path, values, description, units):
    """Write a deterministic compressed one-band GeoTIFF."""
    driver = gdal.GetDriverByName("GTiff")
    dataset = driver.Create(
        str(path),
        COLS,
        ROWS,
        1,
        gdal.GDT_Float32,
        options=("COMPRESS=DEFLATE", "PREDICTOR=3", "TILED=YES"),
    )
    dataset.SetGeoTransform(
        (ORIGIN_X, CELL_SIZE, 0.0, ORIGIN_Y, 0.0, -CELL_SIZE)
    )
    spatial_reference = osr.SpatialReference()
    spatial_reference.ImportFromEPSG(CRS_EPSG)
    dataset.SetProjection(spatial_reference.ExportToWkt())
    dataset.SetMetadata(
        {
            "AREA_OR_POINT": "Area",
            "DESCRIPTION": description,
            "LICENSE": "CC0-1.0",
            "SOURCE": "Synthetic TerraWorkbench example",
            "UNITS": units,
        }
    )
    band = dataset.GetRasterBand(1)
    band.SetDescription(description)
    band.SetNoDataValue(NODATA)
    band.SetUnitType(units)
    band.WriteArray(values.astype(np.float32))
    band.ComputeStatistics(False)
    band.FlushCache()
    dataset.FlushCache()
    dataset = None


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    east = ORIGIN_X + (np.arange(COLS) + 0.5) * CELL_SIZE
    north = ORIGIN_Y - (np.arange(ROWS) + 0.5) * CELL_SIZE
    x, y = np.meshgrid(east, north)
    local_x = x - east.mean()
    local_y = y - north.mean()

    magnetic = (
        180.0 * gaussian(local_x, local_y, -1700, 700, 850, 1300)
        - 125.0 * gaussian(local_x, local_y, -700, -50, 950, 1100)
        + 95.0 * gaussian(local_x, local_y, 1700, -1200, 650, 900)
        + 0.0035 * local_x
        - 0.0015 * local_y
        + 4.0 * np.sin(local_x / 520.0)
    )
    gravity = (
        7.5 * gaussian(local_x, local_y, -1200, 300, 1500, 1200)
        - 5.0 * gaussian(local_x, local_y, 1700, 900, 1700, 1400)
        + 3.0 * gaussian(local_x, local_y, 500, -1800, 1100, 900)
        + 0.00025 * local_x
    )
    dem = (
        850.0
        + 260.0 * gaussian(local_x, local_y, -1800, -700, 1700, 1500)
        + 180.0 * gaussian(local_x, local_y, 1900, 1400, 1300, 1800)
        + 35.0 * np.sin(local_x / 1100.0) * np.cos(local_y / 1350.0)
    )

    write_geotiff(
        OUTPUT / "synthetic_magnetic_anomaly.tif",
        magnetic,
        "Synthetic total-field magnetic anomaly",
        "nT",
    )
    write_geotiff(
        OUTPUT / "synthetic_gravity_anomaly.tif",
        gravity,
        "Synthetic gravity anomaly",
        "mGal",
    )
    write_geotiff(
        OUTPUT / "synthetic_dem.tif",
        dem,
        "Synthetic terrain model",
        "m",
    )

    with (OUTPUT / "synthetic_survey_points.csv").open(
        "w", newline="", encoding="utf-8"
    ) as output_file:
        writer = csv.writer(output_file)
        writer.writerow(
            ("easting", "northing", "line_id", "magnetic_nt", "gravity_mgal", "height_m")
        )
        for row in range(2, ROWS, 4):
            line_id = f"L{row:03d}"
            for column in range(COLS):
                writer.writerow(
                    (
                        f"{east[column]:.1f}",
                        f"{north[row]:.1f}",
                        line_id,
                        f"{magnetic[row, column]:.6f}",
                        f"{gravity[row, column]:.6f}",
                        f"{dem[row, column] + 120.0:.3f}",
                    )
                )

    manifest = {
        "schema_version": 1,
        "license": "CC0-1.0",
        "crs": f"EPSG:{CRS_EPSG}",
        "cell_size_m": CELL_SIZE,
        "dimensions": [ROWS, COLS],
        "nodata": NODATA,
        "files": {
            "synthetic_magnetic_anomaly.tif": {
                "quantity": "magnetic anomaly",
                "units": "nT",
            },
            "synthetic_gravity_anomaly.tif": {
                "quantity": "gravity anomaly",
                "units": "mGal",
            },
            "synthetic_dem.tif": {"quantity": "elevation", "units": "m"},
            "synthetic_survey_points.csv": {
                "quantity": "sampled flight lines",
                "columns": [
                    "easting",
                    "northing",
                    "line_id",
                    "magnetic_nt",
                    "gravity_mgal",
                    "height_m",
                ],
            },
        },
        "warning": "Synthetic educational data. Do not use for geological decisions.",
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
