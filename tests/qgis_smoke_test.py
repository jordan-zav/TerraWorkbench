"""Run two TerraWorkbench algorithms in a real headless QGIS environment."""

import os
from pathlib import Path
import sys
import tempfile
import gc

import numpy as np
from osgeo import gdal, osr


PROJECT_PARENT = Path(__file__).resolve().parents[2]
if str(PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(PROJECT_PARENT))

from qgis.core import QgsApplication, QgsRasterLayer


def create_test_raster(path):
    driver = gdal.GetDriverByName("GTiff")
    dataset = driver.Create(str(path), 8, 8, 1, gdal.GDT_Float64)
    dataset.SetGeoTransform((500000.0, 100.0, 0.0, 9000000.0, 0.0, -100.0))
    spatial_reference = osr.SpatialReference()
    spatial_reference.ImportFromEPSG(32718)
    dataset.SetProjection(spatial_reference.ExportToWkt())
    values = np.linspace(-100.0, 500.0, 64, dtype=np.float64).reshape(8, 8)
    dataset.GetRasterBand(1).WriteArray(values)
    dataset = None


def main():
    prefix = os.environ.get("QGIS_PREFIX_PATH")
    if not prefix:
        raise RuntimeError("Run this test through python-qgis-ltr.bat")
    processing_plugins = str(Path(prefix) / "python" / "plugins")
    if processing_plugins not in sys.path:
        sys.path.insert(0, processing_plugins)

    QgsApplication.setPrefixPath(prefix, True)
    application = QgsApplication([], False)
    application.initQgis()

    from processing.core.Processing import Processing
    import processing
    from TerraWorkbench.provider import TerraWorkbenchProvider

    Processing.initialize()
    provider = TerraWorkbenchProvider()
    QgsApplication.processingRegistry().addProvider(provider)

    algorithm_ids = {algorithm.id() for algorithm in provider.algorithms()}
    expected = {
        "terraworkbench:grav_dx",
        "terraworkbench:grav_dy",
        "terraworkbench:grav_dz",
        "terraworkbench:grav_dz2",
        "terraworkbench:grav_uc500",
        "terraworkbench:grav_regional",
        "terraworkbench:grav_residual",
        "terraworkbench:grav_thdr",
        "terraworkbench:grav_tilt",
        "terraworkbench:grav_tga",
        "terraworkbench:mag_dx",
        "terraworkbench:mag_dy",
        "terraworkbench:mag_dz",
        "terraworkbench:mag_dz2",
        "terraworkbench:mag_uc500",
        "terraworkbench:mag_rs",
        "terraworkbench:mag_thdr",
        "terraworkbench:mag_tilt",
        "terraworkbench:mag_45hg",
        "terraworkbench:mag_as",
        "terraworkbench:mag_tdx",
        "terraworkbench:mag_theta",
    }
    if not expected.issubset(algorithm_ids):
        raise AssertionError(f"Missing algorithms: {sorted(expected - algorithm_ids)}")

    with tempfile.TemporaryDirectory(prefix="terraworkbench_") as temporary_directory:
        temporary_path = Path(temporary_directory)
        input_path = temporary_path / "input.tif"
        bouguer_path = temporary_path / "bouguer.tif"
        upward_path = temporary_path / "upward.tif"
        create_test_raster(input_path)
        layer = QgsRasterLayer(str(input_path), "input")
        if not layer.isValid():
            raise AssertionError("The synthetic input raster is invalid")

        processing.run(
            "terraworkbench:bouguer_correction",
            {
                "INPUT": layer,
                "BAND": 1,
                "DENSITY_CRUST": 2670.0,
                "DENSITY_WATER": 1040.0,
                "OUTPUT": str(bouguer_path),
            },
        )
        processing.run(
            "terraworkbench:upward_continuation",
            {
                "INPUT": layer,
                "BAND": 1,
                "HEIGHT": 100.0,
                "OUTPUT": str(upward_path),
            },
        )

        for output_path in (bouguer_path, upward_path):
            output_dataset = gdal.Open(str(output_path))
            if output_dataset is None:
                raise AssertionError(f"Missing output: {output_path.name}")
            output_values = output_dataset.GetRasterBand(1).ReadAsArray()
            if output_values.shape != (8, 8) or not np.isfinite(output_values).all():
                raise AssertionError(f"Invalid output: {output_path.name}")
            output_dataset = None
        layer = None
        gc.collect()

    QgsApplication.processingRegistry().removeProvider(provider)
    application.exitQgis()
    print(f"OK: {len(algorithm_ids)} algorithms loaded; Bouguer and upward continuation ran")


if __name__ == "__main__":
    main()
