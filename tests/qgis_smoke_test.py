"""Run two TerraWorkbench algorithms in a real headless QGIS environment."""

import os
from pathlib import Path
import site
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

TEST_DEPENDENCY_PATH = os.environ.get("TERRAWORKBENCH_TEST_DEPENDENCY_PATH", "")
if TEST_DEPENDENCY_PATH:
    site.addsitedir(TEST_DEPENDENCY_PATH)
    if TEST_DEPENDENCY_PATH not in sys.path:
        sys.path.insert(0, TEST_DEPENDENCY_PATH)


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
        QgsCoordinateReferenceSystem,
        QgsFeature,
        QgsGeometry,
        QgsPointXY,
        QgsProcessing,
        QgsProcessingException,
        QgsProject,
        QgsRasterLayer,
        QgsVectorLayer,
    )
    from qgis.PyQt.QtCore import QSettings, Qt
    from qgis.PyQt.QtWidgets import QAbstractItemView, QMainWindow

    QgsApplication.setPrefixPath(prefix, True)
    application = QgsApplication([], False)
    application.initQgis()

    from processing.core.Processing import Processing
    import processing
    import numpy as np
    from osgeo import gdal, ogr
    from TerraWorkbench.dependencies import (
        import_harmonica,
        import_ppigrf,
        import_xarray,
    )
    from TerraWorkbench.crs_utils import (
        grid_convergence_degrees,
        require_metre_projected_crs,
    )
    from TerraWorkbench.data_import import import_survey_grid, list_vector_layers
    from TerraWorkbench.provider import TerraWorkbenchProvider
    from TerraWorkbench.plugin import TerraWorkbenchPlugin
    import TerraWorkbench.plugin as plugin_module
    from TerraWorkbench.dependency_dialog import DependencyDialog
    from TerraWorkbench.embedded_qpip.install_progress import (
        PipInstallProgressDialog,
    )
    from TerraWorkbench.embedded_qpip.pip_progress import ProgressUpdate
    from TerraWorkbench.embedded_qpip.manager import (
        _python_command,
        read_requirements,
    )
    from TerraWorkbench.i18n import LANGUAGE_KEY, set_language
    from TerraWorkbench.workflow_dock import (
        FilterStackDock,
        PipelineStep,
        SpectrumPlot,
        algorithm_defaults,
        available_algorithms,
        run_filter_stack,
    )

    import_harmonica()
    import_ppigrf()
    import_xarray()

    core_requirement_names = {
        requirement.name.casefold() for requirement in read_requirements()
    }
    all_requirement_names = {
        requirement.name.casefold()
        for requirement in read_requirements(include_inversion=True)
    }
    if "simpeg" in core_requirement_names or "simpeg" not in all_requirement_names:
        raise AssertionError("Core and optional inversion requirements are not separated")

    metric_crs = QgsCoordinateReferenceSystem("EPSG:32718")
    require_metre_projected_crs(metric_crs.toWkt(), "test")
    convergence = grid_convergence_degrees(
        metric_crs.toWkt(), 500000.0, 9000000.0
    )
    if not abs(convergence) < 0.01:
        raise AssertionError("Grid convergence at the UTM central meridian is invalid")
    nonmetric_crs = QgsCoordinateReferenceSystem("EPSG:2227")
    try:
        require_metre_projected_crs(nonmetric_crs.toWkt(), "test")
    except ValueError:
        pass
    else:
        raise AssertionError("A projected CRS in feet was accepted as metric")

    dependency_dialog = DependencyDialog()
    progress_dialog = PipInstallProgressDialog(
        [sys.executable, "-m", "pip", "--version"],
        ["harmonica>=0.7,<0.8", "ppigrf>=2.1,<3"],
        "testing embedded dependency progress",
        lambda _message: None,
    )
    progress_dialog._apply_update(
        ProgressUpdate("harmonica", "Downloading", 75, 100)
    )
    _row, progress_bar = progress_dialog.rows["harmonica"]
    if (
        "QPIP" not in dependency_dialog.browser.toPlainText()
        or progress_bar.value() != 75
    ):
        raise AssertionError("Embedded QPIP dependency UI failed")
    dependency_dialog.close()
    progress_dialog.close()
    dependency_dialog.deleteLater()
    progress_dialog.deleteLater()

    process_dialog = PipInstallProgressDialog(
        [_python_command(), "-um", "pip", "--version"],
        ["packaging"],
        "testing embedded QProcess execution",
        lambda _message: None,
    )
    process_code, process_cancelled, _process_output = process_dialog.execute()
    if process_code != 0 or process_cancelled:
        raise AssertionError("Embedded dependency QProcess execution failed")
    process_dialog.deleteLater()

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
            "terraworkbench:grav_upward_continuation",
            "terraworkbench:grav_regional",
            "terraworkbench:grav_residual",
            "terraworkbench:grav_thdr",
            "terraworkbench:grav_tilt",
            "terraworkbench:grav_tga",
            "terraworkbench:mag_dx",
            "terraworkbench:mag_dy",
            "terraworkbench:mag_dz",
            "terraworkbench:mag_dz2",
            "terraworkbench:mag_upward_continuation",
            "terraworkbench:mag_rs",
            "terraworkbench:mag_thdr",
            "terraworkbench:mag_tilt",
            "terraworkbench:mag_directional_horizontal_gradient",
            "terraworkbench:mag_as",
            "terraworkbench:mag_tdx",
            "terraworkbench:mag_theta",
            "terraworkbench:fft_derivative_easting",
            "terraworkbench:fft_derivative_northing",
            "terraworkbench:fft_derivative_upward",
            "terraworkbench:normal_gravity_grs80",
            "terraworkbench:gravity_disturbance_grs80",
            "terraworkbench:free_air_correction",
            "terraworkbench:free_air_anomaly",
            "terraworkbench:bullard_b_curvature",
            "terraworkbench:simple_bouguer_anomaly",
            "terraworkbench:terrain_correction_prisms",
            "terraworkbench:complete_bouguer_anomaly",
            "terraworkbench:airy_isostatic_moho",
            "terraworkbench:airy_isostatic_anomaly",
            "terraworkbench:grid_survey_points",
            "terraworkbench:crossover_line_leveling",
            "terraworkbench:microlevel_grid",
            "terraworkbench:invert_gravity_density_3d",
            "terraworkbench:invert_magnetic_susceptibility_3d",
            "terraworkbench:invert_magnetic_vector_3d",
            "terraworkbench:invert_joint_gravity_magnetics_3d",
            "terraworkbench:radiometry_ratio",
            "terraworkbench:radiometry_ternary",
            "terraworkbench:radiometry_dose_rate",
            "terraworkbench:radiometry_f_parameter",
            "terraworkbench:radiometry_channel_qc",
            "terraworkbench:radiometry_despike",
            "terraworkbench:radiometry_dead_time",
            "terraworkbench:radiometry_background",
            "terraworkbench:radiometry_height_attenuation",
            "terraworkbench:radiometry_sensitivity_calibration",
            "terraworkbench:radiometry_spectral_unmix",
            "terraworkbench:radiometry_correct_survey_channels",
            "terraworkbench:correct_magnetic_survey_lines",
            "terraworkbench:correct_moving_gravity_survey",
            "terraworkbench:equivalent_source_continuation",
            "terraworkbench:magnetic_pseudogravity",
        }
        if not expected.issubset(algorithm_ids):
            raise AssertionError(
                f"Missing algorithms: {sorted(expected - algorithm_ids)}"
            )
        if len(algorithm_ids) != 83:
            raise AssertionError(f"Expected 83 algorithms, found {len(algorithm_ids)}")

        with tempfile.TemporaryDirectory(
            prefix="terraworkbench_"
        ) as temporary_directory:
            temporary_path = Path(temporary_directory)
            input_path = temporary_path / "input.tif"
            bouguer_path = temporary_path / "bouguer.tif"
            normal_gravity_path = temporary_path / "normal_gravity.tif"
            free_air_path = temporary_path / "free_air.tif"
            terrain_path = temporary_path / "terrain.tif"
            complete_bouguer_path = temporary_path / "complete_bouguer.tif"
            airy_moho_path = temporary_path / "airy_moho.tif"
            isostatic_path = temporary_path / "isostatic.tif"
            upward_path = temporary_path / "upward.tif"
            stack_path = temporary_path / "stack"
            directional_path = temporary_path / "directional.tif"
            rtp_path = temporary_path / "rtp_igrf.tif"
            gridded_path = temporary_path / "survey_grid.tif"
            gridded_filtered_path = temporary_path / "survey_grid_lowpass.tif"
            radiometric_dose_path = temporary_path / "radiometric_dose.tif"
            radiometric_ternary_path = temporary_path / "radiometric_ternary.tif"
            equivalent_source_path = temporary_path / "equivalent_source.tif"
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
                    "TARGET_CRS": QgsCoordinateReferenceSystem("EPSG:32718"),
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
            radiometric_points = QgsVectorLayer(
                "Point?crs=EPSG:32718&field=total:double&field=k:double&field=u:double&field=th:double",
                "raw radiometric points",
                "memory",
            )
            radiometric_feature = QgsFeature(radiometric_points.fields())
            radiometric_feature.setGeometry(
                QgsGeometry.fromPointXY(QgsPointXY(500000, 9000000))
            )
            radiometric_feature.setAttributes([1000.0, 100.0, 50.0, 20.0])
            radiometric_points.dataProvider().addFeature(radiometric_feature)
            corrected_radiometry = processing.run(
                "terraworkbench:radiometry_correct_survey_channels",
                {
                    "INPUT": radiometric_points,
                    "K_WINDOW_FIELD": "k",
                    "U_WINDOW_FIELD": "u",
                    "TH_WINDOW_FIELD": "th",
                    "TOTAL_COUNT_FIELD": "total",
                    "DEAD_TIME_SECONDS": 0.0001,
                    "OUTPUT": "memory:",
                },
            )["OUTPUT"]
            corrected_feature = next(corrected_radiometry.getFeatures())
            if (
                not corrected_feature["tw_rad_ok"]
                or abs(corrected_feature["tw_k_cps"] - 111.111111) > 1e-5
            ):
                raise AssertionError("Radiometric point correction chain failed")
            moving_survey = QgsVectorLayer(
                "Point?crs=EPSG:32718&field=line:string&field=time:double&field=mag:double&field=grav:double",
                "moving geophysical survey",
                "memory",
            )
            moving_features = []
            survey_rows = (
                ("L1", 0.0, 500000.0),
                ("L1", 1.0, 500010.0),
                ("L2", 3600.0, 500020.0),
                ("L2", 3601.0, 500030.0),
            )
            for index, (line_name, time_value, easting) in enumerate(survey_rows):
                feature = QgsFeature(moving_survey.fields())
                feature.setGeometry(
                    QgsGeometry.fromPointXY(QgsPointXY(easting, 9000000))
                )
                feature.setAttributes(
                    [line_name, time_value, 100.0 + index, 10.0 + index]
                )
                moving_features.append(feature)
            moving_survey.dataProvider().addFeatures(moving_features)
            moving_survey.updateExtents()
            if moving_survey.featureCount() != len(survey_rows):
                raise AssertionError("Moving-survey test observations were not stored")
            corrected_mag = processing.run(
                "terraworkbench:correct_magnetic_survey_lines",
                {
                    "INPUT": moving_survey,
                    "VALUE_FIELD": "mag",
                    "TIME_FIELD": "time",
                    "LINE_FIELD": "line",
                    "SIGNED_LAG_SECONDS": 0.0,
                    "HAMPEL_RADIUS": 0,
                    "OUTPUT": "memory:",
                },
            )["OUTPUT"]
            if isinstance(corrected_mag, str):
                corrected_mag = QgsVectorLayer(
                    corrected_mag, "corrected magnetic survey", "ogr"
                )
            if not corrected_mag.isValid():
                raise AssertionError("Corrected magnetic output could not be opened")
            if any(not feature["tw_mag_ok"] for feature in corrected_mag.getFeatures()):
                raise AssertionError("Magnetic line correction produced invalid points")
            corrected_grav = processing.run(
                "terraworkbench:correct_moving_gravity_survey",
                {
                    "INPUT": moving_survey,
                    "VALUE_FIELD": "grav",
                    "TIME_FIELD": "time",
                    "LINE_FIELD": "line",
                    "DRIFT_RATE": 2.0,
                    "EOTVOS_MODE": 2,
                    "OUTPUT": "memory:",
                },
            )["OUTPUT"]
            if isinstance(corrected_grav, str):
                corrected_grav = QgsVectorLayer(
                    corrected_grav, "corrected gravity survey", "ogr"
                )
            if not corrected_grav.isValid():
                raise AssertionError("Corrected gravity output could not be opened")
            corrected_grav_features = list(corrected_grav.getFeatures())
            if any(
                not feature["tw_grav_ok"] for feature in corrected_grav_features
            ):
                raise AssertionError("Moving-gravity correction produced invalid points")
            drift_values = sorted(
                float(feature["tw_drift"])
                for feature in corrected_grav_features
            )
            if (
                len(drift_values) != 4
                or abs(drift_values[0]) > 1e-6
                or drift_values[-1] - drift_values[0] < 1.99
            ):
                raise AssertionError(
                    "Gravity drift restarted at a line boundary: "
                    f"{drift_values!r}"
                )
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
            terrain_layer = None
            complete_layer = None
            try:
                layer = QgsRasterLayer(str(input_path), "input")
                if not layer.isValid():
                    raise AssertionError("The synthetic input raster is invalid")

                processing.run(
                    "terraworkbench:equivalent_source_continuation",
                    {
                        "INPUT": layer,
                        "BAND": 1,
                        "SOURCE_DEPTH": 200.0,
                        "DAMPING": 1.0,
                        "TARGET_HEIGHT": 50.0,
                        "BLOCK_SIZE": 0.0,
                        "MAX_CELLS": 100,
                        "OUTPUT": str(equivalent_source_path),
                    },
                )
                if not equivalent_source_path.exists():
                    raise AssertionError("Equivalent-source output was not created")

                processing.run(
                    "terraworkbench:radiometry_dose_rate",
                    {
                        "INPUT": layer,
                        "BAND": 1,
                        "URANIUM": layer,
                        "URANIUM_BAND": 1,
                        "THORIUM": layer,
                        "THORIUM_BAND": 1,
                        "K_COEFFICIENT": 13.078,
                        "U_COEFFICIENT": 5.675,
                        "TH_COEFFICIENT": 2.494,
                        "OUTPUT": str(radiometric_dose_path),
                    },
                )
                processing.run(
                    "terraworkbench:radiometry_ternary",
                    {
                        "INPUT": layer,
                        "BAND": 1,
                        "URANIUM": layer,
                        "URANIUM_BAND": 1,
                        "THORIUM": layer,
                        "THORIUM_BAND": 1,
                        "LOWER_PERCENTILE": 2.0,
                        "UPPER_PERCENTILE": 98.0,
                        "NORMALIZE": True,
                        "OUTPUT": str(radiometric_ternary_path),
                    },
                )
                ternary_dataset = gdal.Open(str(radiometric_ternary_path))
                if not radiometric_dose_path.exists() or ternary_dataset.RasterCount != 3:
                    raise AssertionError("Radiometric Processing outputs are invalid")
                ternary_dataset = None

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
                    "terraworkbench:normal_gravity_grs80",
                    {
                        "INPUT": layer,
                        "BAND": 1,
                        "OUTPUT": str(normal_gravity_path),
                    },
                )
                processing.run(
                    "terraworkbench:free_air_anomaly",
                    {
                        "INPUT": layer,
                        "BAND": 1,
                        "ELEVATION": layer,
                        "ELEVATION_BAND": 1,
                        "VERTICAL_GRADIENT": 0.3086,
                        "OUTPUT": str(free_air_path),
                    },
                )
                processing.run(
                    "terraworkbench:terrain_correction_prisms",
                    {
                        "INPUT": layer,
                        "BAND": 1,
                        "DENSITY_CRUST": 2670.0,
                        "DENSITY_WATER": 1040.0,
                        "CLEARANCE": 1.0,
                        "MAX_CELLS": 100,
                        "OUTPUT": str(terrain_path),
                    },
                )
                terrain_layer = QgsRasterLayer(str(terrain_path), "terrain")
                processing.run(
                    "terraworkbench:complete_bouguer_anomaly",
                    {
                        "INPUT": layer,
                        "BAND": 1,
                        "ELEVATION": layer,
                        "ELEVATION_BAND": 1,
                        "TERRAIN": terrain_layer,
                        "TERRAIN_BAND": 1,
                        "DENSITY_CRUST": 2670.0,
                        "DENSITY_WATER": 1040.0,
                        "VERTICAL_GRADIENT": 0.3086,
                        "OUTPUT": str(complete_bouguer_path),
                    },
                )
                processing.run(
                    "terraworkbench:airy_isostatic_moho",
                    {
                        "INPUT": layer,
                        "BAND": 1,
                        "REFERENCE_DEPTH": 25000.0,
                        "DENSITY_CRUST": 2670.0,
                        "DENSITY_MANTLE": 3070.0,
                        "OUTPUT": str(airy_moho_path),
                    },
                )
                complete_layer = QgsRasterLayer(
                    str(complete_bouguer_path), "complete Bouguer"
                )
                processing.run(
                    "terraworkbench:airy_isostatic_anomaly",
                    {
                        "INPUT": complete_layer,
                        "BAND": 1,
                        "ELEVATION": layer,
                        "ELEVATION_BAND": 1,
                        "REFERENCE_DEPTH": 25000.0,
                        "DENSITY_CRUST": 2670.0,
                        "DENSITY_MANTLE": 3070.0,
                        "MAX_CELLS": 100,
                        "OUTPUT": str(isostatic_path),
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
                    "terraworkbench:mag_directional_horizontal_gradient",
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

                exercised_stack_algorithms = 0
                for stack_algorithm in available_algorithms():
                    result = processing.run(
                        stack_algorithm.id(),
                        {
                            **algorithm_defaults(stack_algorithm),
                            "INPUT": layer,
                            "BAND": 1,
                            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
                        },
                    )
                    if not result.get("OUTPUT"):
                        raise AssertionError(
                            f"No output from {stack_algorithm.id()}"
                        )
                    exercised_stack_algorithms += 1
                if exercised_stack_algorithms != len(algorithm_ids) - 21:
                    raise AssertionError(
                        "Not every Filter Stack-compatible algorithm was executed"
                    )
                print(
                    f"OK: executed {exercised_stack_algorithms} stack-compatible algorithms",
                    flush=True,
                )

                dock = FilterStackDock()
                dock.show()
                application.processEvents()
                print("OK: Filter Stack dock constructed", flush=True)
                try:
                    sample_raster = dock.load_sample_raster(
                        "synthetic_magnetic_anomaly.tif"
                    )
                    sample_points = dock.load_sample_points()
                    if (
                        sample_raster is None
                        or not sample_raster.isValid()
                        or sample_points is None
                        or not sample_points.isValid()
                        or sample_raster.crs().authid() != "EPSG:32718"
                    ):
                        raise AssertionError(
                            "Bundled synthetic sample datasets did not load"
                        )
                    QgsProject.instance().removeMapLayers(
                        [sample_raster.id(), sample_points.id()]
                    )
                    print(
                        "OK: bundled MAG raster and survey CSV loaded",
                        flush=True,
                    )
                    nrcan_root = (
                        Path(__file__).resolve().parents[1]
                        / "sample_data"
                        / "nrcan"
                    )
                    nrcan_grids = sorted(
                        path
                        for path in nrcan_root.rglob("*")
                        if path.is_file() and path.suffix.casefold() == ".grd"
                    )
                    if len(nrcan_grids) != 2:
                        raise AssertionError("Expected two bundled NRCan GRD files")
                    if nrcan_grids:
                        real_output = temporary_path / "nrcan_reference_grid.tif"
                        imported, metadata = import_survey_grid(
                            str(nrcan_grids[0]), str(real_output)
                        )
                        real_layer = QgsRasterLayer(imported, "NRCan reference grid")
                        if not real_layer.isValid():
                            raise AssertionError(
                                "A local reference GRD did not convert to GeoTIFF"
                            )
                        if nrcan_grids[0].with_suffix(".GRD.xml").is_file() and not metadata:
                            raise AssertionError(
                                "The local GRD sidecar metadata was not recovered"
                            )
                        print(
                            f"OK: bundled NRCan GRD imported ({nrcan_grids[0].name})",
                            flush=True,
                        )
                        real_layer = None
                        gc.collect()
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
                    if len(available_algorithms()) != len(algorithm_ids) - 21:
                        raise AssertionError(
                            "Filter Stack is missing registered algorithms"
                        )
                    dock.show_algorithm_picker()
                    application.processEvents()
                    if (
                        not dock.algorithm_picker.isVisible()
                        or dock.algorithm_picker.width() > 440
                    ):
                        raise AssertionError(
                            "Compact left-side algorithm chooser failed"
                        )
                    dock.algorithm_search.setText("RTP IGRF")
                    application.processEvents()
                    visible_algorithms = [
                        dock._algorithm_labels.get(
                            dock.algorithm_list.item(index).data(
                                Qt.ItemDataRole.UserRole
                            ),
                            "",
                        )
                        for index in range(dock.algorithm_list.count())
                        if not dock.algorithm_list.item(index).isHidden()
                    ]
                    if not any("RTP" in label for label in visible_algorithms):
                        raise AssertionError("RTP is not discoverable in the chooser")
                    for index in range(dock.algorithm_list.count()):
                        item = dock.algorithm_list.item(index)
                        row_widget = dock.algorithm_list.itemWidget(item)
                        if (
                            item.text()
                            or row_widget is None
                            or item.sizeHint().height()
                            < row_widget.sizeHint().height()
                        ):
                            raise AssertionError(
                                "Filter chooser row text/height overlaps its custom widget"
                            )
                    dock.show_algorithm_info(
                        "terraworkbench:butterworth_lowpass"
                    )
                    application.processEvents()
                    if (
                        not dock.filter_info.isVisible()
                        or "Butterworth"
                        not in dock.filter_info.browser.toPlainText()
                    ):
                        raise AssertionError(
                            "Per-filter information button/dialog failed"
                        )
                    dock.filter_info.hide()
                    dock.algorithm_picker.hide()
                    dock.show_knowledge_base()
                    application.processEvents()
                    if (
                        not dock.knowledge_base.isVisible()
                        or dock.knowledge_base.width() > 900
                        or "Harmonica"
                        not in dock.knowledge_base.repository_browser.toPlainText()
                    ):
                        raise AssertionError(
                            "Clickable Knowledge Base did not open correctly"
                        )
                    dock.knowledge_base.hide()
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
                    normal_gravity_path,
                    free_air_path,
                    terrain_path,
                    complete_bouguer_path,
                    airy_moho_path,
                    isostatic_path,
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

                ascii_source = temporary_path / "scientific_grid.xyz"
                ascii_source.write_text(
                    "500000;6200000;1.0e-4\n"
                    "500100;6200000;2.0e-4\n"
                    "500000;6200100;3.0e-4\n"
                    "500100;6200100;4.0e-4\n",
                    encoding="utf-8",
                )
                import_survey_grid(
                    ascii_source, temporary_path / "scientific_grid.tif"
                )

                duplicate_source = temporary_path / "duplicate_grid.csv"
                duplicate_source.write_text(
                    "x,y,value\n0,0,1\n0,0,2\n0,1,3\n1,0,4\n",
                    encoding="utf-8",
                )
                try:
                    import_survey_grid(
                        duplicate_source, temporary_path / "duplicate_grid.tif"
                    )
                except QgsProcessingException as error:
                    if "duplicate" not in str(error).casefold():
                        raise
                else:
                    raise AssertionError("Duplicate X/Y coordinates were accepted")
                print(
                    "OK: scientific-notation ASCII imported and duplicate grid rejected",
                    flush=True,
                )

                vector_container = temporary_path / "vector_container.gpkg"
                vector_dataset = ogr.GetDriverByName("GPKG").CreateDataSource(
                    str(vector_container)
                )
                vector_dataset.CreateLayer("survey_points", geom_type=ogr.wkbPoint)
                vector_dataset = None
                if list_vector_layers(vector_container) != ["survey_points"]:
                    raise AssertionError("GDAL vector/table enumeration failed")
                print("OK: vector container layers enumerated", flush=True)
            finally:
                for file_layer_name in (
                    "corrected_mag",
                    "corrected_grav",
                    "inversion_layer",
                ):
                    file_layer = locals().get(file_layer_name)
                    if isinstance(file_layer, QgsVectorLayer):
                        file_layer.setDataSource(
                            "Point?crs=EPSG:4326", "released", "memory"
                        )
                for raster_layer_name in (
                    "gridded_layer",
                    "layer",
                    "terrain_layer",
                    "complete_layer",
                ):
                    raster_layer = locals().get(raster_layer_name)
                    if isinstance(raster_layer, QgsRasterLayer):
                        raster_layer.setDataSource("", "released", "gdal")
                point_layer = None
                gridded_layer = None
                line_layer = None
                radiometric_points = None
                corrected_radiometry = None
                moving_survey = None
                corrected_mag = None
                corrected_grav = None
                corrected_grav_features = None
                leveled = None
                inversion_layer = None
                layer = None
                terrain_layer = None
                complete_layer = None
                gc.collect()
                application.processEvents()

        QgsApplication.processingRegistry().removeProvider(provider)
        provider = None

        lifecycle_events = []

        class FakeInterface:
            def __init__(self):
                self.window = QMainWindow()
                self.dock_area = None

            def mainWindow(self):
                return self.window

            def addDockWidget(self, area, dock):
                lifecycle_events.append("dock")
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
        plugin_module.show_dependency_dialog = (
            lambda _parent: lifecycle_events.append("dependencies")
        )
        plugin = TerraWorkbenchPlugin(FakeInterface())
        settings = QSettings()
        previous_language = settings.value(LANGUAGE_KEY, None)
        try:
            plugin.initGui()
            if (
                plugin.filter_stack_dock is None
                or plugin.filter_stack_action is None
                or plugin.knowledge_action is None
                or plugin.dependency_action is None
            ):
                raise AssertionError(
                    "Plugin lifecycle did not register the Filter Stack and Knowledge Base"
                )
            if lifecycle_events[:2] != ["dependencies", "dock"]:
                raise AssertionError(
                    "Dependency manager was not the first TerraWorkbench UI"
                )
            set_language("es")
            plugin.filter_stack_dock.preferences_changed()
            magnetic_dx = QgsApplication.processingRegistry().algorithmById(
                "terraworkbench:mag_dx"
            )
            if (
                plugin.filter_stack_dock.settings_button.text()
                != "Configuración…"
                or "Primera derivada" not in magnetic_dx.displayName()
                or "Jordan Zavaleta (GisGeo Dev)"
                not in plugin.filter_stack_dock.settings_dialog.about_label.text()
                or "jordanzav@gisgeo.dev"
                not in plugin.filter_stack_dock.settings_dialog.about_label.text()
            ):
                raise AssertionError("Spanish runtime localization/settings failed")
            drag_drop_enum = getattr(
                QAbstractItemView, "DragDropMode", QAbstractItemView
            )
            settings_position = plugin.filter_stack_dock.file_grid.getItemPosition(
                plugin.filter_stack_dock.file_grid.indexOf(
                    plugin.filter_stack_dock.settings_button
                )
            )
            if (
                plugin.filter_stack_dock.step_list.dragDropMode()
                != drag_drop_enum.InternalMove
                or settings_position != (0, 2, 1, 1)
            ):
                raise AssertionError(
                    "Drag-reordering or compact Settings placement failed"
                )
            set_language("pt")
            plugin.filter_stack_dock.preferences_changed()
            if (
                plugin.filter_stack_dock.settings_button.text()
                != "Configurações…"
                or "Primeira derivada"
                not in QgsApplication.processingRegistry()
                .algorithmById("terraworkbench:mag_dx")
                .displayName()
                or "Geofísica de Campos Potenciais"
                not in plugin.filter_stack_dock.knowledge_base.reference_browser.toPlainText()
            ):
                raise AssertionError("Portuguese runtime localization failed")
            set_language("en")
            plugin.filter_stack_dock.preferences_changed()
            if (
                plugin.filter_stack_dock.settings_button.text() != "Settings…"
                or "First horizontal derivative"
                not in QgsApplication.processingRegistry()
                .algorithmById("terraworkbench:mag_dx")
                .displayName()
            ):
                raise AssertionError("English runtime localization failed")
        finally:
            plugin.unload()
            plugin_module.show_dependency_dialog = original_dependency_dialog
            if previous_language is None:
                settings.remove(LANGUAGE_KEY)
            else:
                settings.setValue(LANGUAGE_KEY, previous_language)
        print(
            "OK: plugin lifecycle registered and removed the right-side dock",
            flush=True,
        )
        print(
            f"OK: {len(algorithm_ids)} algorithms loaded; direct tools and a "
            "two-step Filter Stack ran",
            flush=True,
        )
    finally:
        if provider is not None:
            QgsApplication.processingRegistry().removeProvider(provider)
        QgsProject.instance().clear()
        application.processEvents()
        gc.collect()
        application.exitQgis()


if __name__ == "__main__":
    main()
