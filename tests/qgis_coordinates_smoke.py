"""Real QGIS horizontal reprojection and localized coordinate panel smoke."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransformContext
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtGui import QFont, QFontDatabase
from qgis.PyQt import sip
from qgis.PyQt.QtTest import QTest

from TerraWorkbench.i18n import LANGUAGE_KEY, set_language
from TerraWorkbench.survey_store import SurveyStore
from TerraWorkbench.survey_coordinates_dialog import SurveyCoordinatesDialog, coordinate_operation
from TerraWorkbench.survey_workspace_dialog import StoreWorker


def main():
    QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication([], False)
    app.initQgis()
    if os.name == "nt":
        QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts" / "arial.ttf"))
    app.setFont(QFont("Arial", 10))
    settings = QSettings()
    previous = settings.value(LANGUAGE_KEY, None)
    try:
        with tempfile.TemporaryDirectory(prefix="tw_coordinates_") as folder:
            source = Path(folder) / "input.csv"
            source.write_text("lon,lat\n-75,0\n-75,-10\n,-5\n", encoding="utf-8")
            store = SurveyStore(Path(folder) / "project", create=True)
            database = store.import_file(source)
            store.configure_geometry(database, "lon", "lat", "EPSG:4326")
            for lang in ("en", "es", "pt"):
                set_language(lang)
                dialog = SurveyCoordinatesDialog(store, database)
                assert dialog.x.currentText() == "lon"
                assert dialog.y.currentText() == "lat"
                assert dialog.source.crs().authid() == "EPSG:4326"
                dialog.mode.setCurrentIndex(1)
                dialog.target.setCrs(QgsCoordinateReferenceSystem("EPSG:32718"))
                dialog.show()
                app.processEvents()
                assert dialog.grab().save(str(Path(tempfile.gettempdir()) / f"tw_coordinates_{lang}.png"))
                dialog.accept()
                assert dialog.request["output_x"] == "X_projected"
                request = dialog.request
                sip.delete(dialog)
                print(f"PASS {lang}: coordinate selector and reprojection panel", flush=True)
            results, errors = [], []
            worker = StoreWorker(coordinate_operation(store, database, request, QgsCoordinateTransformContext()))
            worker.completed.connect(results.append)
            worker.failed.connect(errors.append)
            worker.start()
            deadline = time.monotonic() + 30
            while worker.isRunning() and time.monotonic() < deadline:
                app.processEvents()
                QTest.qWait(10)
            assert not worker.isRunning(), "Coordinate worker timed out"
            app.processEvents()
            assert not errors, errors
            result = results[0]
            sip.delete(worker)
            assert result["null_pairs"] == 1
            values = next(store.batches(database, ["X_projected", "Y_projected"])).to_pydict()
            assert abs(values["X_projected"][0] - 500000) < 0.001
            assert abs(values["Y_projected"][0] - 10000000) < 0.001
            assert abs(values["Y_projected"][1] - 8894587.5087) < 0.01
            assert values["X_projected"][2] is None
            metadata = json.loads(store.databases()[0]["metadata"])
            assert QgsCoordinateReferenceSystem(metadata["geometry"]["crs"]).authid() == "EPSG:32718"
            request.update(x="X_projected", y="Y_projected", source="EPSG:32718", target="EPSG:4326", output_x="lon_back", output_y="lat_back")
            coordinate_operation(store, database, request, QgsCoordinateTransformContext())(lambda: False, lambda n: None)
            back = next(store.batches(database, ["lon_back", "lat_back"])).to_pydict()
            assert abs(back["lon_back"][1] + 75) < 1e-8
            assert abs(back["lat_back"][1] + 10) < 1e-8
            print("PASS UTM reference, round trip, nulls, active CRS and original preservation", flush=True)
    finally:
        if previous is None:
            settings.remove(LANGUAGE_KEY)
        else:
            settings.setValue(LANGUAGE_KEY, previous)


if __name__ == "__main__":
    main()
