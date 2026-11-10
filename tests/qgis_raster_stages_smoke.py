"""Native stage maps, bounded samples and conservative comparison checks."""

import os
from pathlib import Path
import sys
import tempfile
import time
import json
import hashlib

import numpy as np
from osgeo import gdal, osr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtGui import QFont, QFontDatabase
from qgis.PyQt.QtTest import QTest
from qgis.PyQt import sip

from TerraWorkbench.ui.i18n import LANGUAGE_KEY, set_language
from TerraWorkbench.ui.raster_stage_review import (
    RasterStageReview,
    read_stage,
    compare_stages,
)


def write(path, values, shift=0):
    dataset = gdal.GetDriverByName("GTiff").Create(
        str(path), values.shape[1], values.shape[0], 1, gdal.GDT_Float64
    )
    dataset.SetGeoTransform((500000 + shift, 2, 0, 4000000, 0, -2))
    crs = osr.SpatialReference()
    crs.ImportFromEPSG(32618)
    dataset.SetProjection(crs.ExportToWkt())
    band = dataset.GetRasterBand(1)
    band.SetNoDataValue(-9999)
    band.SetUnitType("nT")
    band.WriteArray(values)
    dataset = None


def main():
    gdal.UseExceptions()
    QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication([], False)
    app.initQgis()
    if os.name == "nt":
        QFontDatabase.addApplicationFont(
            str(Path(os.environ["WINDIR"]) / "Fonts" / "arial.ttf")
        )
    app.setFont(QFont("Arial", 10))
    settings = QSettings()
    previous = settings.value(LANGUAGE_KEY, None)
    try:
        with tempfile.TemporaryDirectory(prefix="tw_raster_stages_") as folder:
            folder = Path(folder)
            data = np.arange(64.0).reshape(8, 8)
            first = data.copy()
            first[0, 0] = -9999
            write(folder / "a.tif", first)
            write(folder / "b.tif", data + 2)
            write(folder / "shifted.tif", data, shift=1)
            records = [
                {"path": str(folder / name), "label": name, "band": 1}
                for name in ("a.tif", "b.tif")
            ]
            originals = [
                hashlib.sha256(Path(record["path"]).read_bytes()).hexdigest()
                for record in records
            ]
            a, b = [read_stage(record) for record in records]
            delta = compare_stages(a, b)
            assert delta["statistics"]["mean"] == 2
            assert delta["statistics"]["valid_preview_cells"] == 63
            assert not delta["sampled"]
            shifted = read_stage(
                {"path": str(folder / "shifted.tif"), "label": "shifted"}
            )
            try:
                compare_stages(a, shifted)
                raise AssertionError("Mismatched geometry accepted")
            except ValueError:
                pass
            b["unit"] = "mGal"
            try:
                compare_stages(a, b)
                raise AssertionError("Mismatched units accepted")
            except ValueError:
                pass
            write(folder / "large.tif", np.ones((1024, 1100)))
            large = read_stage({"path": str(folder / "large.tif"), "label": "large"})
            assert large["sampled"] and large["values"].shape == (512, 512)
            for lang in ("en", "es", "pt"):
                set_language(lang)
                dialog = RasterStageReview(records)
                dialog.show()
                dialog.load()
                deadline = time.monotonic() + 40
                while dialog.worker is not None and time.monotonic() < deadline:
                    QTest.qWait(10)
                    app.processEvents()
                assert dialog.worker is None and dialog.samples is not None, (
                    dialog.status.text()
                )
                assert len(dialog.layers) == 2
                dialog.compare()
                assert (
                    json.loads(dialog.details.toPlainText())["statistics"]["mean"] == 2
                )
                QTest.qWait(100)
                app.processEvents()
                assert dialog.grab().save(
                    str(Path(tempfile.gettempdir()) / f"tw_raster_stages_{lang}.png")
                )
                dialog.close()
                sip.delete(dialog)
                print(
                    f"PASS {lang}: native A/B maps, shared scale, paired NoData statistics, geometry/unit refusal and bounded 512-cell previews",
                    flush=True,
                )
            assert originals == [
                hashlib.sha256(Path(record["path"]).read_bytes()).hexdigest()
                for record in records
            ]
    finally:
        if previous is None:
            settings.remove(LANGUAGE_KEY)
        else:
            settings.setValue(LANGUAGE_KEY, previous)


if __name__ == "__main__":
    main()
