"""Offscreen real GRD import, editable filter parameters and EN/ES/PT execution.

Run through python-qgis-ltr.bat with TEMP/TMP in an isolated session.
Only generated outputs are written; the source GRD is hashed before and after.
"""

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import struct
from unittest.mock import patch

import numpy as np
from osgeo import gdal
from qgis.core import QgsApplication, QgsProject, QgsRasterLayer, QgsSettings
from qgis.PyQt.QtGui import QFont, QFontDatabase
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from TerraWorkbench.ui.i18n import LANGUAGE_KEY, set_language
from TerraWorkbench.qgis_plugin.dependencies import import_harmonica
from TerraWorkbench.qgis_plugin.provider import TerraWorkbenchProvider
from TerraWorkbench.ui.workflow_dock import FilterStackDock


def grid_info(path):
    dataset = gdal.Open(str(path))
    assert dataset is not None, path
    band = dataset.GetRasterBand(1)
    values = band.ReadAsArray().astype(float)
    nodata = band.GetNoDataValue()
    if nodata is not None:
        values[values == nodata] = np.nan
    info = (dataset.GetGeoTransform(), dataset.GetProjection(), values)
    dataset = None
    return info


def main():
    QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication([], False)
    app.initQgis()
    if os.name == "nt":
        QFontDatabase.addApplicationFont(
            str(Path(os.environ["WINDIR"]) / "Fonts/arial.ttf")
        )
    app.setFont(QFont("Arial", 10))
    sys.path.insert(0, str(Path(os.environ["QGIS_PREFIX_PATH"]) / "python/plugins"))
    from processing.core.Processing import Processing

    Processing.initialize()
    provider = TerraWorkbenchProvider()
    QgsApplication.processingRegistry().addProvider(provider)
    settings = QgsSettings()
    previous = settings.value(LANGUAGE_KEY) if settings.contains(LANGUAGE_KEY) else None
    root = Path(tempfile.gettempdir()) / "grd-workflow"
    root.mkdir()
    # Authored uncompressed Oasis grid: exercise real GRD import without NRCan.
    source = root / "synthetic.grd"
    yy, xx = np.mgrid[:48, :64]
    synthetic = (20 * np.sin(xx / 7) + 12 * np.cos(yy / 5)).astype("<f4")
    header = bytearray(512)
    struct.pack_into("<5i5d2d", header, 0, 4, 2, 64, 48, 1,
                     100.0, 100.0, 450000.0, 8645000.0, 0.0, 0.0, 1.0)
    source.write_bytes(header + synthetic.tobytes())
    Path(str(source) + ".xml").write_text(
        "<metadata><wellknown_epsg>32718</wellknown_epsg></metadata>", encoding="utf-8"
    )
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    reference = (
        import_harmonica()
        .load_oasis_montaj_grid(source)
        .sortby("northing", ascending=False)
        .sortby("easting")
    )
    np.testing.assert_array_equal(reference.values, synthetic[::-1])
    dock = None
    errors = []
    report = []
    language_reference = None
    try:
        for locale, title, cutoff_label in (
            ("en", "Selected filter parameters", "Cutoff wavelength"),
            ("es", "Parámetros del filtro seleccionado", "Longitud de onda"),
            ("pt", "Parâmetros do filtro selecionado", "Comprimento de onda"),
        ):
            set_language(locale)
            provider.refreshAlgorithms()
            dock = FilterStackDock()
            # Public exports omit optional field examples; generic GRD import remains enabled.
            with patch.object(type(dock), "_nrcan_sample_path", return_value=root / "absent.grd"):
                dock.refresh_bundled_reference_actions()
                assert not dock.nrcan_menu.menuAction().isVisible()
                assert not dock.nrcan_hydraulic_mag_action.isEnabled()
            dock.resize(460, 850)
            dock.show()
            # Keep an existing selection: importing must select the NEW raster.
            old = QgsRasterLayer(
                str(
                    Path(__file__).resolve().parents[1]
                    / "sample_data/synthetic/synthetic_dem.tif"
                ),
                "Existing DEM",
            )
            QgsProject.instance().addMapLayer(old)
            dock.refresh_layers()
            dock.layer_combo.setCurrentIndex(dock.layer_combo.findData(old.id()))
            imported = root / f"imported_{locale}.tif"
            with (
                patch.object(
                    QFileDialog, "getOpenFileName", return_value=(str(source), "")
                ),
                patch.object(
                    QFileDialog, "getSaveFileName", return_value=(str(imported), "")
                ),
                patch.object(QMessageBox, "information"),
                patch.object(
                    QMessageBox,
                    "critical",
                    side_effect=lambda *a: errors.append(str(a[-1])),
                ),
            ):
                dock.import_grid()
            assert not errors, errors
            assert Path(dock._selected_raster().source()) == imported
            transform, crs, original = grid_info(imported)
            np.testing.assert_allclose(
                original, reference.values, equal_nan=True, rtol=0, atol=0
            )
            assert crs, "The real GRD must have its sidecar CRS"
            cutoff = 4 * max(abs(transform[1]), abs(transform[5]))
            for operation in ("butterworth_lowpass", "smooth_nine_point"):
                index = dock.algorithm_combo.findData("terraworkbench:" + operation)
                assert index >= 0, operation
                dock.algorithm_combo.setCurrentIndex(index)
                dock.add_step()
            dock.step_list.setCurrentRow(0)
            dock.parameters_button.click()
            app.processEvents()
            assert dock.parameter_group.title() == title
            editor, parameter = dock._parameter_editors["WAVELENGTH"]
            assert cutoff_label in parameter.description(), parameter.description()
            editor.setText("-1")
            assert not dock.update_current_parameters(), "Reject negative wavelengths"
            editor.setText(str(cutoff))
            dock._parameter_editors["ORDER"][0].setText("4")
            assert dock.update_current_parameters()
            assert dock.steps()[0].parameters["WAVELENGTH"] == cutoff
            assert dock.inspector.grab().save(str(root / f"parameters_{locale}.png"))
            assert dock.grab().save(str(root / f"workflow_{locale}.png"))
            output_root = root / locale
            output_root.mkdir()
            dock.output_directory.setText(str(output_root))
            dock.keep_intermediate.setChecked(True)
            results = []
            for wavelength in (cutoff, cutoff * 2):
                dock._parameter_editors["WAVELENGTH"][0].setText(str(wavelength))
                with (
                    patch.object(QMessageBox, "information"),
                    patch.object(
                        QMessageBox,
                        "critical",
                        side_effect=lambda *a: errors.append(str(a[-1])),
                    ),
                    patch.object(
                        QMessageBox,
                        "warning",
                        side_effect=lambda *a: errors.append(str(a[-1])),
                    ),
                ):
                    dock.run_stack()
                assert not errors, errors
                manifest = json.loads(
                    Path(dock.last_recipe).read_text(encoding="utf-8")
                )
                assert manifest["steps"][0]["parameters"]["WAVELENGTH"] == wavelength
                assert len(manifest["stages"]) == 3
                for stage in manifest["stages"][1:]:
                    geo, projection, values = grid_info(stage["path"])
                    assert geo == transform and projection == crs
                    assert values.shape == original.shape
                    assert np.array_equal(np.isfinite(values), np.isfinite(original))
                results.append(values.copy())
            valid = np.isfinite(results[0]) & np.isfinite(results[1])
            assert valid.any() and not np.allclose(results[0][valid], results[1][valid])
            if language_reference is None:
                language_reference = results
            else:
                for expected, actual in zip(language_reference, results):
                    np.testing.assert_allclose(
                        actual, expected, equal_nan=True, rtol=0, atol=0
                    )
            report.append(
                {
                    "language": locale,
                    "shape": list(original.shape),
                    "valid_cells": int(valid.sum()),
                    "changed_cutoff_max_difference": float(
                        np.max(np.abs(results[0][valid] - results[1][valid]))
                    ),
                }
            )
            print("PASS", locale, report[-1], flush=True)
            dock.disconnect_project()
            dock.close()
            dock.deleteLater()
            app.processEvents()
            dock = None
            QgsProject.instance().clear()
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
        (root / "report.json").write_text(
            json.dumps({"source_sha256": source_hash, "runs": report}, indent=2),
            encoding="utf-8",
        )
        print("CAPTURES", root, flush=True)
    finally:
        if dock is not None:
            dock.disconnect_project()
            dock.close()
            dock.deleteLater()
            app.processEvents()
        if previous is None:
            settings.remove(LANGUAGE_KEY)
        else:
            settings.setValue(LANGUAGE_KEY, previous)
        QgsProject.instance().clear()
        QgsApplication.processingRegistry().removeProvider(provider)
        app.exitQgis()


if __name__ == "__main__":
    main()
