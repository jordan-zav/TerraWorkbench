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


def temporary_import_smoke(app, source, evidence):
    from time import monotonic, sleep
    from types import SimpleNamespace
    from xml.etree import ElementTree

    from qgis import utils
    from qgis.PyQt.QtCore import QObject, QPoint, QSettings, pyqtSignal
    from qgis.PyQt.QtGui import QPixmap, QPainter
    from qgis.core import QgsCoordinateReferenceSystem, QgsLayerTreeModel, QgsProcessingUtils
    from qgis.gui import QgsLayerTreeView

    from TerraWorkbench.qgis_plugin.data_import import (
        WORK_DIRECTORY_KEY, WORK_DIRECTORY_SCOPE, import_layer_path, is_temporary_import,
        recent_work_directories, temporary_import_root, write_project_work_directory,
    )
    from TerraWorkbench.ui.settings_dialog import KEY_OUTPUT
    from TerraWorkbench.ui import workflow_dock

    project = QgsProject.instance()
    settings = QSettings()
    settings.setValue(KEY_OUTPUT, str(evidence / "filter-output"))
    evidence.mkdir(parents=True)
    set_language("es")
    dock = FilterStackDock()
    temp_root = temporary_import_root().resolve()

    def unexpected_dialog(*args, **kwargs):
        raise AssertionError(f"Unexpected dialog: {args}, {kwargs}")

    def convert():
        with (
            patch.object(QFileDialog, "getSaveFileName", new=unexpected_dialog),
            patch.object(QFileDialog, "getExistingDirectory", new=unexpected_dialog),
            patch.object(QMessageBox, "information", new=unexpected_dialog),
            patch.object(QMessageBox, "critical", new=unexpected_dialog),
        ):
            return dock._finish_import(str(source))

    def save_project(decision, folder=None):
        decisions = []

        def choose(box):
            decisions.append(box.windowTitle())
            return box.defaultButton() if decision == "save" else box.escapeButton()

        with (
            patch.object(QMessageBox, "exec", return_value=0),
            patch.object(QMessageBox, "clickedButton", new=choose),
            patch.object(QFileDialog, "getExistingDirectory", return_value=str(folder or "")),
        ):
            assert project.write(str(evidence / "project.qgs"))
        return decisions

    try:
        # The Processing preference maps to QgsProcessing::settingsTempPath in QGIS 3.44.
        qgis_temp_setting = "qgis/configuration/temp-path"
        alternate_temp = evidence.parent / "processing-custom-temp"
        alternate_temp.mkdir()
        zone_a = evidence / "zone-a"
        zone_b = evidence / "zone-b"
        work_a = zone_a / "North"
        work_b = zone_b / "South"
        work_a.mkdir(parents=True)
        work_b.mkdir(parents=True)
        project_a = zone_a / "north.qgz"
        project_b = zone_b / "south.qgz"
        with patch.object(QFileDialog, "getExistingDirectory", return_value=str(work_a)):
            dock._choose_work_directory()
        assert project.write(str(project_a))
        assert project.readEntry(WORK_DIRECTORY_SCOPE, WORK_DIRECTORY_KEY) == ("North", True)
        project.clear()
        assert dock.work_directory_button.text().endswith("Temporal (QGIS)")
        dock._set_work_directory(work_b)
        assert project.write(str(project_b))
        for project_file, work in ((project_a, work_a), (project_b, work_b)):
            assert project.read(str(project_file))
            assert dock.work_directory_button.text().endswith(work.name)
            assert Path(dock.work_directory_button.toolTip()) == work
        for number in range(5):
            folder = zone_b / f"Sector {number + 1}"
            folder.mkdir()
            dock._set_work_directory(folder)
        dock._set_work_directory(work_b)
        assert len(recent_work_directories()) == 5
        assert Path(recent_work_directories()[0]) == work_b
        dock.show()
        app.processEvents()
        button = dock.work_directory_button
        menu = dock.work_directory_menu
        origin = dock.mapToGlobal(QPoint(0, 0))
        menu.popup(button.mapToGlobal(QPoint(0, button.height())))
        app.processEvents()
        panel_image, menu_image = dock.grab(), menu.grab()
        offset = menu.pos() - origin
        image = QPixmap(panel_image)
        painter = QPainter(image)
        painter.drawPixmap(offset, menu_image)
        painter.end()
        assert image.save(str(evidence / "work-folder-menu.png"))
        menu.close()
        assert project.read(str(project_a))
        missing = zone_a / "Missing"
        write_project_work_directory(project, missing)
        messages = []
        iface = SimpleNamespace(messageBar=lambda: SimpleNamespace(pushWarning=lambda *args: messages.append(args)))
        with patch.object(utils, "iface", iface):
            dock.refresh_work_directory()
            dock.refresh_work_directory()
            assert len(messages) == 1 and str(missing) in messages[0][1]
            assert dock.work_directory_button.text().endswith("Temporal (QGIS)")
            first = convert()
            assert len(messages) == 1
        assert first is not None and is_temporary_import(first)
        original = import_layer_path(first).resolve()
        assert original.is_relative_to(temp_root) and original.is_file()
        assert first.name().endswith("(temporal)")
        panel = QgsLayerTreeView()
        model = QgsLayerTreeModel(project.layerTreeRoot(), panel)
        panel.setModel(model)
        panel.resize(530, 180)
        panel.show()
        app.processEvents()
        assert panel.grab().save(str(evidence / "temporary-layer.png"))
        panel.close()
        panel.deleteLater()

        set_language("pt")
        dock.retranslate()
        assert first.name().endswith("(temporário)")
        assert dock.save_import_action.text() == "Salvar como…"
        assert dock.work_directory_button.text() == "Pasta de trabalho: Temporário (QGIS)"
        set_language("es")
        dock.retranslate()

        saved = evidence / "retained.tif"
        layer_id = first.id()
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(saved), "")):
            dock.save_import_action.trigger()
        assert first.id() == layer_id and import_layer_path(first) == saved
        assert saved.read_bytes() == original.read_bytes()
        assert not is_temporary_import(first)

        bundled = Path(__file__).resolve().parents[1] / "sample_data/synthetic/synthetic_dem.tif"
        with (
            patch.object(workflow_dock, "import_survey_grid", new=unexpected_dialog),
            patch.object(QFileDialog, "getSaveFileName", new=unexpected_dialog),
        ):
            native = dock._finish_import(str(bundled))
        assert import_layer_path(native).resolve() == bundled.resolve()
        assert not is_temporary_import(native)

        temporary = convert()
        QgsSettings().setValue(qgis_temp_setting, alternate_temp.as_posix())
        temp_root = temporary_import_root().resolve()
        assert Path(QgsProcessingUtils.tempFolder()).is_relative_to(alternate_temp)
        print(f"Processing temporary imports: {temp_root}")
        duplicate = convert()
        assert import_layer_path(duplicate).is_relative_to(temp_root)
        assert temporary.source() != duplicate.source()
        assert is_temporary_import(temporary) and is_temporary_import(duplicate)
        configured = evidence / "imports"
        configured.mkdir()
        dock._set_work_directory(configured)
        dock.settings_dialog.load()
        assert dock.settings_dialog.output_directory.text() == str(evidence / "filter-output")
        permanent = convert()
        assert import_layer_path(permanent).resolve().is_relative_to(configured.resolve())
        assert not is_temporary_import(permanent)
        dock.layer_combo.setCurrentIndex(dock.layer_combo.findData(duplicate.id()))
        assert dock.save_import_action.text() == "Guardar en la carpeta de trabajo"
        with patch.object(QFileDialog, "getSaveFileName", new=unexpected_dialog):
            dock.save_import_action.trigger()
        assert not is_temporary_import(duplicate)
        assert import_layer_path(duplicate).is_relative_to(configured)
        assert len(save_project("ignore")) == 1
        assert not save_project("ignore")
        project.removeMapLayer(temporary.id())
        assert not save_project("ignore")
        dock._set_work_directory(None)

        gdb = evidence / "test.gdb"
        gdb.write_bytes(b"!CBD")

        class MockProcess(QObject):
            readyReadStandardOutput = pyqtSignal()
            finished = pyqtSignal(int, int)

            def setProcessEnvironment(self, environment):
                pass

            def readAllStandardOutput(self):
                return b""

            def readAllStandardError(self):
                return b""

            def kill(self):
                raise AssertionError("The mocked Geosoft import must finish normally.")

            def start(self, executable, arguments):
                assert "--extract-all" in arguments
                output = Path(arguments[arguments.index("--output") + 1])
                assert output.resolve().is_relative_to(temp_root)
                channels, lines, csv = (output / name for name in ("channels.csv", "lines.csv", "samples.csv"))
                channels.write_text("channel\nMAG\n", encoding="utf-8")
                lines.write_text("line\nL1\nT1\n", encoding="utf-8")
                csv.write_text(
                    "LINE,FIDUCIAL,X,Y,MAG\nL1,1,400000,100000,1\nL1,2,400100,100000,2\n"
                    "T1,1,400000,100000,3\nT1,2,400000,100100,4\n",
                    encoding="utf-8",
                )
                (output / "test_inventory.json").write_text(json.dumps({
                    "source": str(gdb), "channels_csv": str(channels), "lines_csv": str(lines),
                    "csv": str(csv), "x_field": "X", "y_field": "Y",
                    "coordinate_system": {"wkt": QgsCoordinateReferenceSystem("EPSG:27700").toWkt()},
                    "lines": [{"name": "L1", "kind": "traverse"}, {"name": "T1", "kind": "tie"}],
                }), encoding="utf-8")
                self.finished.emit(0, 0)

        def extract(box):
            return next(button for button in box.buttons()
                        if box.buttonRole(button) == QMessageBox.AcceptRole)

        with (
            patch.object(dock, "_geosoft_runtime", return_value=SimpleNamespace(standalone=False, python="mock")),
            patch.object(workflow_dock, "QProcess", MockProcess),
            patch.object(QMessageBox, "exec", return_value=0),
            patch.object(QMessageBox, "clickedButton", new=extract),
            patch.object(QFileDialog, "getExistingDirectory", new=unexpected_dialog),
            patch.object(QMessageBox, "warning", new=unexpected_dialog),
        ):
            dock.import_geosoft_gdb(str(gdb))
            deadline = monotonic() + 10
            group = None
            while group is None and monotonic() < deadline:
                app.processEvents()
                group = project.layerTreeRoot().findGroup("test")
                sleep(0.02)
            assert group is not None
        group_layers = [node.layer() for node in group.findLayers()]
        assert len(group_layers) == 4, [layer.name() for layer in group_layers]
        assert all(".gpkg|" in layer.source() and not Path(layer.source().split("|")[0]).resolve()
                   .is_relative_to(temp_root) for layer in group_layers)
        gdb_tables = [layer for layer in project.mapLayers().values()
                      if layer.providerType() == "delimitedtext" and is_temporary_import(layer)]
        assert len(gdb_tables) == 2
        kept = evidence / "saved-on-project-write"
        kept.mkdir()
        new_temporary = convert()
        assert len(save_project("save", kept)) == 1
        assert project.readEntry(WORK_DIRECTORY_SCOPE, WORK_DIRECTORY_KEY) == (kept.name, True)
        assert all(not is_temporary_import(layer) and import_layer_path(layer).is_relative_to(kept)
                   for layer in [new_temporary, *gdb_tables])
        expected = {layer.id(): layer.name() for layer in [new_temporary, *gdb_tables]}
        xml = ElementTree.parse(evidence / "project.qgs")
        for element in xml.findall(".//projectlayers/maplayer"):
            if element.findtext("id") in expected:
                assert "saved-on-project-write" in element.findtext("datasource")
        assert project.read(str(evidence / "project.qgs"))
        assert all(project.mapLayer(key).isValid() and project.mapLayer(key).name() == name
                   for key, name in expected.items())
        print(f"PASS: temporary root {temp_root}", flush=True)
        print("PASS: GRD default/configured, TIFF in place, save/repoint, project warnings and simulated Geosoft", flush=True)
    finally:
        dock.disconnect_project()
        dock.close()
        dock.deleteLater()
        project.clear()
        app.processEvents()


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
    if destination := os.environ.get("TW_TEMP_IMPORT_EVIDENCE"):
        import traceback

        sample = Path(__file__).resolve().parents[1] / "sample_data/nrcan/Hydraulic/BC_2004_G_Hydraulic_dem.GRD"
        try:
            temporary_import_smoke(app, sample if sample.is_file() else source, Path(destination))
        except Exception:
            print(traceback.format_exc(), flush=True)
            raise
        finally:
            QgsApplication.processingRegistry().removeProvider(provider)
            app.exitQgis()
        return
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
            with (
                patch.object(
                    QFileDialog, "getOpenFileName", return_value=(str(source), "")
                ),
                patch.object(
                    QFileDialog, "getSaveFileName", side_effect=AssertionError("Import asked where to save")
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
            imported = Path(dock._selected_raster().source())
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
