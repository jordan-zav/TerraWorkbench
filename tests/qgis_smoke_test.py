"""Run two TerraWorkbench algorithms in a real headless QGIS environment."""

import os
from pathlib import Path
import sys
import tempfile
import gc

PROJECT_PARENT = Path(
    os.environ.get(
        "TERRAWORKBENCH_PLUGIN_PARENT",
        str(Path(__file__).resolve().parents[2]),
    )
)
if str(PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(PROJECT_PARENT))


def create_test_raster(path):
    import numpy as np
    from osgeo import gdal, osr

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

    from qgis.core import (
        QgsApplication,
        QgsFeature,
        QgsGeometry,
        QgsPointXY,
        QgsProject,
        QgsRasterLayer,
        QgsVectorLayer,
    )
    from qgis.PyQt.QtWidgets import QMainWindow

    QgsApplication.setPrefixPath(prefix, True)
    application = QgsApplication([], False)
    application.initQgis()

    from processing.core.Processing import Processing
    import processing
    import numpy as np
    from osgeo import gdal
    from TerraWorkbench.dependencies import (
        import_harmonica,
        import_ppigrf,
        import_xarray,
    )
    from TerraWorkbench.data_import import import_survey_grid
    from TerraWorkbench.provider import TerraWorkbenchProvider
    from TerraWorkbench.plugin import TerraWorkbenchPlugin
    import TerraWorkbench.plugin as plugin_module
    from TerraWorkbench.workflow_dock import (
        FilterStackDock,
        PipelineStep,
        SpectrumPlot,
        available_algorithms,
        run_filter_stack,
    )

    import_harmonica()
    import_ppigrf()
    import_xarray()

    provider = None
    algorithm_ids = set()
    try:
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
            "terraworkbench:grid_survey_points",
            "terraworkbench:crossover_line_leveling",
            "terraworkbench:microlevel_grid",
            "terraworkbench:invert_gravity_density_3d",
            "terraworkbench:invert_magnetic_susceptibility_3d",
            "terraworkbench:invert_magnetic_vector_3d",
            "terraworkbench:invert_joint_gravity_magnetics_3d",
        }
        if not expected.issubset(algorithm_ids):
            raise AssertionError(
                f"Missing algorithms: {sorted(expected - algorithm_ids)}"
            )
        if len(algorithm_ids) != 54:
            raise AssertionError(f"Expected 54 algorithms, found {len(algorithm_ids)}")

        with tempfile.TemporaryDirectory(
            prefix="terraworkbench_"
        ) as temporary_directory:
            temporary_path = Path(temporary_directory)
            input_path = temporary_path / "input.tif"
            bouguer_path = temporary_path / "bouguer.tif"
            upward_path = temporary_path / "upward.tif"
            stack_path = temporary_path / "stack"
            directional_path = temporary_path / "directional.tif"
            rtp_path = temporary_path / "rtp_igrf.tif"
            gridded_path = temporary_path / "survey_grid.tif"
            gridded_filtered_path = temporary_path / "survey_grid_lowpass.tif"
            create_test_raster(input_path)
            point_layer = QgsVectorLayer(
                "Point?crs=EPSG:4326&field=mag:double", "survey points", "memory"
            )
            point_features = []
            for longitude, latitude, value in (
                (-77.10, -12.10, 10.0),
                (-77.00, -12.10, 20.0),
                (-77.10, -12.00, 30.0),
                (-77.00, -12.00, 40.0),
                (-77.05, -12.05, 25.0),
            ):
                feature = QgsFeature(point_layer.fields())
                feature.setGeometry(
                    QgsGeometry.fromPointXY(QgsPointXY(longitude, latitude))
                )
                feature.setAttributes([value])
                point_features.append(feature)
            point_layer.dataProvider().addFeatures(point_features)
            processing.run(
                "terraworkbench:grid_survey_points",
                {
                    "INPUT": point_layer,
                    "VALUE_FIELD": "mag",
                    "TARGET_CRS": "EPSG:32718",
                    "METHOD": 0,
                    "CELL_SIZE": 2500.0,
                    "POWER": 2.0,
                    "NEIGHBORS": 4,
                    "SEARCH_RADIUS": 0.0,
                    "OUTPUT": str(gridded_path),
                },
            )
            gridded_layer = QgsRasterLayer(str(gridded_path), "gridded survey")
            if not gridded_layer.isValid():
                raise AssertionError(
                    "Survey gridding output could not be opened in QGIS"
                )
            processing.run(
                "terraworkbench:butterworth_lowpass",
                {
                    "INPUT": gridded_layer,
                    "BAND": 1,
                    "WAVELENGTH": 5000.0,
                    "ORDER": 4,
                    "OUTPUT": str(gridded_filtered_path),
                },
            )
            gridded_layer = None
            gc.collect()

            line_layer = QgsVectorLayer(
                "Point?crs=EPSG:32718&field=line:string&field=kind:string&field=fiducial:double&field=mag:double",
                "leveling points",
                "memory",
            )
            line_features = []
            for line_name, kind, points in (
                (
                    "L1",
                    "traverse",
                    [
                        (500000, 8999900, 10),
                        (500100, 8999900, 10),
                        (500200, 8999900, 10),
                    ],
                ),
                (
                    "L2",
                    "traverse",
                    [
                        (500000, 9000100, -4),
                        (500100, 9000100, -4),
                        (500200, 9000100, -4),
                    ],
                ),
                (
                    "T1",
                    "tie",
                    [(500100, 8999800, 0), (500100, 9000000, 0), (500100, 9000200, 0)],
                ),
            ):
                for fiducial, (x, y, value) in enumerate(points):
                    feature = QgsFeature(line_layer.fields())
                    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
                    feature.setAttributes([line_name, kind, fiducial, value])
                    line_features.append(feature)
            line_layer.dataProvider().addFeatures(line_features)
            leveled = processing.run(
                "terraworkbench:crossover_line_leveling",
                {
                    "INPUT": line_layer,
                    "VALUE_FIELD": "mag",
                    "LINE_FIELD": "line",
                    "LINE_TYPE_FIELD": "kind",
                    "ORDER_FIELD": "fiducial",
                    "TIE_VALUES": "tie",
                    "OUTLIER_SIGMA": 4.5,
                    "CORRECTED": "memory:",
                    "CROSSOVERS": "memory:",
                    "CORRECTIONS": "memory:",
                },
            )
            if leveled["CROSSOVERS"].featureCount() != 2:
                raise AssertionError(
                    "Crossover leveling did not produce both intersections"
                )
            micro_path = temporary_path / "microlevel.tif"
            correction_path = temporary_path / "microlevel_correction.tif"
            processing.run(
                "terraworkbench:microlevel_grid",
                {
                    "INPUT": str(input_path),
                    "BAND": 1,
                    "AZIMUTH": 0.0,
                    "ACROSS_WAVELENGTH": 400.0,
                    "ALONG_WAVELENGTH": 2000.0,
                    "OUTPUT": str(micro_path),
                    "CORRECTION": str(correction_path),
                },
            )
            if not micro_path.exists() or not correction_path.exists():
                raise AssertionError("Microleveling outputs were not created")
            if os.environ.get("TERRAWORKBENCH_TEST_INVERSION") == "1":
                inversion_layer = QgsVectorLayer(
                    "Point?crs=EPSG:32718&field=gravity:double&field=magnetic:double&field=sigma_g:double&field=sigma_m:double",
                    "joint inversion observations",
                    "memory",
                )
                inversion_features = []
                for index, (x, y) in enumerate(
                    (
                        (500000, 9000000),
                        (500100, 9000000),
                        (500200, 9000000),
                        (500000, 9000100),
                        (500100, 9000100),
                        (500200, 9000100),
                        (500000, 9000200),
                        (500100, 9000200),
                        (500200, 9000200),
                    )
                ):
                    anomaly = (0.0, 1.0, 0.0, 1.0, 2.0, 1.0, 0.0, 1.0, 0.0)[index]
                    feature = QgsFeature(inversion_layer.fields())
                    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
                    feature.setAttributes([anomaly / 10.0, anomaly, 0.1, 1.0])
                    inversion_features.append(feature)
                inversion_layer.dataProvider().addFeatures(inversion_features)
                joint_output = temporary_path / "joint_inversion"
                processing.run(
                    "terraworkbench:invert_joint_gravity_magnetics_3d",
                    {
                        "GRAVITY_INPUT": inversion_layer,
                        "GRAVITY_DATA": "gravity",
                        "GRAVITY_SIGMA": "sigma_g",
                        "MAGNETIC_INPUT": inversion_layer,
                        "MAGNETIC_DATA": "magnetic",
                        "MAGNETIC_SIGMA": "sigma_m",
                        "CELL_XY": 100.0,
                        "CELL_Z": 100.0,
                        "DEPTH": 200.0,
                        "PADDING": 1,
                        "MESH_TYPE": 1,
                        "REFINEMENT_LEVELS": 2,
                        "MAX_CELLS": 1000,
                        "ITERATIONS": 1,
                        "COUPLING": 10000.0,
                        "DENSITY_MIN": -1.5,
                        "DENSITY_MAX": 1.5,
                        "SUSCEPTIBILITY_MIN": 0.0,
                        "SUSCEPTIBILITY_MAX": 1.0,
                        "FIELD_AMPLITUDE": 50000.0,
                        "FIELD_INCLINATION": 60.0,
                        "FIELD_DECLINATION": 0.0,
                        "DISK_SENSITIVITIES": False,
                        "OUTPUT": str(joint_output),
                    },
                )
                for expected_name in (
                    "joint_inversion_model.npz",
                    "joint_inversion_summary.json",
                    "gravity_observed_predicted_residual.csv",
                    "magnetics_observed_predicted_residual.csv",
                ):
                    if not (joint_output / expected_name).exists():
                        raise AssertionError(
                            f"Missing joint inversion output: {expected_name}"
                        )
                print(
                    "OK: joint TreeMesh inversion ran through QGIS Processing",
                    flush=True,
                )
            layer = None
            try:
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
                    "terraworkbench:reduction_to_pole_igrf",
                    {
                        "INPUT": layer,
                        "BAND": 1,
                        "FIELD_MODE": 1,
                        "YEAR": 2025,
                        "MONTH": 1,
                        "DAY": 1,
                        "ALTITUDE_KM": 0.0,
                        "MAX_GAIN": 50.0,
                        "OUTPUT": str(rtp_path),
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
                processing.run(
                    "terraworkbench:mag_45hg",
                    {
                        "INPUT": layer,
                        "BAND": 1,
                        "AZIMUTH": 90.0,
                        "OUTPUT": str(directional_path),
                    },
                )

                final_stack_output, stack_outputs = run_filter_stack(
                    layer,
                    1,
                    [
                        PipelineStep(
                            "terraworkbench:butterworth_lowpass",
                            {"WAVELENGTH": 1000.0, "ORDER": 4},
                        ),
                        PipelineStep(
                            "terraworkbench:directional_cosine_reject",
                            {"AZIMUTH": 45.0, "DEGREE": 2},
                        ),
                    ],
                    output_directory=stack_path,
                    keep_intermediate=True,
                )
                if (
                    len(stack_outputs) != 2
                    or Path(final_stack_output)
                    != stack_path / "02_directional_cosine_reject.tif"
                ):
                    raise AssertionError(
                        "Filter stack did not return the expected outputs"
                    )
                print("OK: two-step Processing chain completed", flush=True)

                dock = FilterStackDock()
                print("OK: Filter Stack dock constructed", flush=True)
                try:
                    gdb_source = os.environ.get("TERRAWORKBENCH_GDB_TEST_SOURCE")
                    gdb_export = os.environ.get("TERRAWORKBENCH_GDB_TEST_OUTPUT")
                    if gdb_source and gdb_export:
                        before_ids = set(QgsProject.instance().mapLayers())
                        loaded = dock._load_geosoft_outputs(
                            gdb_source,
                            gdb_export,
                        )
                        if loaded != 3:
                            raise AssertionError(
                                f"Expected 3 open GDB export layers, loaded {loaded}"
                            )
                        added_ids = set(QgsProject.instance().mapLayers()) - before_ids
                        QgsProject.instance().removeMapLayers(list(added_ids))
                        print(
                            "OK: GDB export loaded as points plus two QGIS tables",
                            flush=True,
                        )
                    spectrum_plot = SpectrumPlot(
                        np.linspace(0.0, 1.0, 32),
                        np.geomspace(1.0, 1000.0, 32),
                        np.geomspace(1.0, 100.0, 32),
                    )
                    spectrum_plot.resize(600, 320)
                    if spectrum_plot.grab().isNull():
                        raise AssertionError("Spectrum preview did not render")
                    spectrum_plot.deleteLater()
                    if len(available_algorithms()) != len(algorithm_ids) - 6:
                        raise AssertionError(
                            "Filter Stack is missing registered algorithms"
                        )
                    dock.algorithm_combo.setCurrentIndex(
                        dock.algorithm_combo.findData(
                            "terraworkbench:butterworth_lowpass"
                        )
                    )
                    dock.add_step()
                    dock.algorithm_combo.setCurrentIndex(
                        dock.algorithm_combo.findData(
                            "terraworkbench:directional_cosine_reject"
                        )
                    )
                    dock.add_step()
                    if len(dock.steps()) != 2:
                        raise AssertionError("Filter Stack UI did not retain two steps")
                    if dock.maximumWidth() > 380 or not dock.inspector.isVisible():
                        raise AssertionError(
                            "Compact dock/floating inspector behavior failed"
                        )
                    print("OK: Filter Stack UI retained two steps", flush=True)
                finally:
                    dock.disconnect_project()
                    dock.close()
                    dock.deleteLater()

                for output_path in (
                    bouguer_path,
                    upward_path,
                    directional_path,
                    rtp_path,
                    stack_path / "01_butterworth_lowpass.tif",
                    stack_path / "02_directional_cosine_reject.tif",
                ):
                    output_dataset = gdal.Open(str(output_path))
                    if output_dataset is None:
                        raise AssertionError(f"Missing output: {output_path.name}")
                    output_values = output_dataset.GetRasterBand(1).ReadAsArray()
                    if (
                        output_values.shape != (8, 8)
                        or not np.isfinite(output_values).all()
                    ):
                        raise AssertionError(f"Invalid output: {output_path.name}")
                    output_dataset = None

                gridded_dataset = gdal.Open(str(gridded_path))
                if gridded_dataset is None:
                    raise AssertionError("Survey gridding output is missing")
                gridded_values = gridded_dataset.GetRasterBand(1).ReadAsArray()
                gridded_nodata = gridded_dataset.GetRasterBand(1).GetNoDataValue()
                gridded_projection = gridded_dataset.GetProjection()
                gridded_dataset = None
                valid_grid = np.isfinite(gridded_values) & ~np.isclose(
                    gridded_values, gridded_nodata
                )
                if not np.any(valid_grid) or not gridded_projection:
                    raise AssertionError(
                        "Survey gridding did not produce finite projected cells"
                    )
                filtered_grid_dataset = gdal.Open(str(gridded_filtered_path))
                filtered_grid_values = filtered_grid_dataset.GetRasterBand(
                    1
                ).ReadAsArray()
                filtered_grid_dataset = None
                if (
                    filtered_grid_values.shape != gridded_values.shape
                    or not np.isfinite(filtered_grid_values).all()
                ):
                    raise AssertionError(
                        "Gridded survey could not pass through an FFT filter"
                    )
                print(
                    "OK: survey points gridded and passed directly through FFT filter",
                    flush=True,
                )

                survey_source_value = os.environ.get(
                    "TERRAWORKBENCH_GRD_TEST_SOURCE"
                )
                if survey_source_value and Path(survey_source_value).is_file():
                    survey_source = Path(survey_source_value)
                    imported_path = temporary_path / "mount_polley_mtf.tif"
                    _result, imported_metadata = import_survey_grid(
                        survey_source, imported_path
                    )
                    imported_dataset = gdal.Open(str(imported_path))
                    if imported_dataset is None or imported_dataset.RasterCount != 1:
                        raise AssertionError("Real Oasis montaj GRD import failed")
                    imported_projection = imported_dataset.GetProjection()
                    imported_dataset = None
                    if not imported_projection:
                        raise AssertionError("GRD sidecar CRS metadata was not applied")
                    if imported_metadata.get("EPSG") != "26710":
                        raise AssertionError(
                            f"Unexpected GRD EPSG metadata: {imported_metadata}"
                        )
                    print(
                        "OK: real Mount Polley GRD and XML metadata imported",
                        flush=True,
                    )

                csv_source = temporary_path / "regular_grid.csv"
                csv_source.write_text(
                    "longitude,latitude,mag\n"
                    "-77.1,-12.1,10\n-77.0,-12.1,11\n"
                    "-77.1,-12.0,12\n-77.0,-12.0,13\n",
                    encoding="utf-8",
                )
                csv_output = temporary_path / "regular_grid.tif"
                import_survey_grid(csv_source, csv_output)
                csv_dataset = gdal.Open(str(csv_output))
                if (
                    csv_dataset is None
                    or csv_dataset.RasterXSize != 2
                    or not csv_dataset.GetProjection()
                ):
                    raise AssertionError("Regular CSV grid import failed")
                csv_dataset = None
                print("OK: regular CSV grid imported with geographic CRS", flush=True)
            finally:
                layer = None
                gc.collect()

        QgsApplication.processingRegistry().removeProvider(provider)
        provider = None

        class FakeInterface:
            def __init__(self):
                self.window = QMainWindow()
                self.dock_area = None

            def mainWindow(self):
                return self.window

            def addDockWidget(self, area, dock):
                self.dock_area = area
                self.window.addDockWidget(area, dock)

            def removeDockWidget(self, dock):
                self.window.removeDockWidget(dock)

            def addPluginToRasterMenu(self, _menu, _action):
                pass

            def removePluginRasterMenu(self, _menu, _action):
                pass

            def addToolBarIcon(self, _action):
                pass

            def removeToolBarIcon(self, _action):
                pass

        original_dependency_dialog = plugin_module.show_dependency_dialog
        plugin_module.show_dependency_dialog = lambda _parent: None
        plugin = TerraWorkbenchPlugin(FakeInterface())
        try:
            plugin.initGui()
            if plugin.filter_stack_dock is None or plugin.filter_stack_action is None:
                raise AssertionError(
                    "Plugin lifecycle did not register the Filter Stack"
                )
        finally:
            plugin.unload()
            plugin_module.show_dependency_dialog = original_dependency_dialog
        print(
            "OK: plugin lifecycle registered and removed the right-side dock",
            flush=True,
        )
    finally:
        if provider is not None:
            QgsApplication.processingRegistry().removeProvider(provider)
        application.exitQgis()
    print(
        f"OK: {len(algorithm_ids)} algorithms loaded; direct tools and a two-step "
        "Filter Stack ran"
    )


if __name__ == "__main__":
    main()
