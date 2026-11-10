"""Offscreen logical-window and scale-factor matrix; no desktop interaction."""

import json
import os
from pathlib import Path
import sys
import tempfile

from qgis.core import QgsApplication, QgsProject, QgsRasterLayer, QgsSettings
from qgis.PyQt import sip
from qgis.PyQt.QtGui import QFont, QFontDatabase
from qgis.PyQt.QtWidgets import QAbstractButton, QLabel, QStyle, QStyleOptionButton

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from TerraWorkbench.ui.i18n import LANGUAGE_KEY, set_language
from TerraWorkbench.qgis_plugin.provider import TerraWorkbenchProvider
from TerraWorkbench.ui.workflow_dock import FilterStackDock
from TerraWorkbench.ui.process_centre import ProcessCentre
from TerraWorkbench.ui.core_job_dialog import CoreJobDialog
from TerraWorkbench.ui.core_workflow_dialog import CoreWorkflowDialog


def overflow(window):
    problems = []
    for widget in window.findChildren(QAbstractButton):
        if not widget.isVisibleTo(window) or not widget.text().strip():
            continue
        text = widget.text().replace("&", "")
        option = QStyleOptionButton()
        option.initFrom(widget)
        option.text = widget.text()
        rectangle = widget.style().subElementRect(
            QStyle.SE_PushButtonContents, option, widget
        )
        if (
            max(
                widget.fontMetrics().horizontalAdvance(line)
                for line in text.splitlines()
            )
            > rectangle.width()
        ):
            problems.append({"kind": "button", "text": text, "width": widget.width()})
    for widget in window.findChildren(QLabel):
        if not widget.isVisibleTo(window) or not widget.text().strip():
            continue
        if widget.wordWrap() and widget.hasHeightForWidth():
            needed = widget.heightForWidth(widget.width())
            if needed > widget.height() + 2:
                problems.append(
                    {
                        "kind": "wrapped label",
                        "text": widget.text()[:100],
                        "needed": needed,
                        "height": widget.height(),
                    }
                )
    return problems


def main():
    QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication([], False)
    app.initQgis()
    if os.name == "nt":
        QFontDatabase.addApplicationFont(
            str(Path(os.environ["WINDIR"]) / "Fonts/arial.ttf")
        )
    app.setFont(QFont("Arial", 10))
    provider = TerraWorkbenchProvider()
    QgsApplication.processingRegistry().addProvider(provider)
    settings = QgsSettings()
    previous = settings.value(LANGUAGE_KEY) if settings.contains(LANGUAGE_KEY) else None
    root = Path(tempfile.gettempdir()) / (
        "layouts-scale-" + os.environ.get("QT_SCALE_FACTOR", "1")
    )
    root.mkdir(exist_ok=True)
    report = []
    dock = None
    try:
        layer = QgsRasterLayer(
            str(
                Path(__file__).resolve().parents[1]
                / "sample_data/synthetic/synthetic_magnetic_anomaly.tif"
            ),
            "Synthetic magnetic grid",
        )
        QgsProject.instance().addMapLayer(layer)
        for locale in ("en", "es", "pt"):
            set_language(locale)
            provider.refreshAlgorithms()
            dock = FilterStackDock()
            for algorithm_id in (
                "terraworkbench:butterworth_lowpass",
                "terraworkbench:smooth_nine_point",
            ):
                dock.algorithm_combo.setCurrentIndex(
                    dock.algorithm_combo.findData(algorithm_id)
                )
                dock.add_step()
            dock.step_list.setCurrentRow(0)
            for width, height in ((900, 640), (1360, 850)):
                centre = ProcessCentre()
                console = CoreJobDialog("depth.euler_window")
                workflow = CoreWorkflowDialog()
                workflow.load_recipe(
                    Path(__file__).resolve().parents[1]
                    / "sample_data/workflows/gravity_layer.json"
                )
                depth_consoles = []
                for method in ("euler", "werner", "spi"):
                    depth = CoreJobDialog("depth.interpret_grid")
                    depth.parameter_form.base.fields["method"][0].setText(
                        json.dumps(method)
                    )
                    depth.parameter_form.tabs.setCurrentIndex(1)
                    depth_consoles.append((method, depth))
                windows = (
                    ("catalogue", centre, width, height),
                    ("core", console, width, height),
                    ("workflow", workflow, width, height),
                    (
                        "knowledge",
                        dock.knowledge_base,
                        min(width, 900),
                        min(height, 760),
                    ),
                    ("filter", dock, 460, height),
                ) + tuple(
                    ("depth_" + method, depth, width, height)
                    for method, depth in depth_consoles
                )
                for label, window, w, h in windows:
                    window.resize(w, h)
                    window.show()
                    app.processEvents()
                    issues = overflow(window)
                    if window.width() > w + 2 or window.height() > h + 2:
                        issues.append(
                            {
                                "kind": "minimum size exceeds window",
                                "actual": [window.width(), window.height()],
                                "requested": [w, h],
                            }
                        )
                    capture = root / f"{label}_{locale}_{w}x{h}.png"
                    assert window.grab().save(str(capture))
                    report.append(
                        {
                            "panel": label,
                            "language": locale,
                            "requested": [w, h],
                            "actual": [window.width(), window.height()],
                            "dpr": window.devicePixelRatioF(),
                            "problems": issues,
                        }
                    )
                    window.hide()
                sip.delete(centre)
                sip.delete(console)
                sip.delete(workflow)
                for _, depth in depth_consoles:
                    sip.delete(depth)
            dock.disconnect_project()
            dock.close()
            sip.delete(dock)
            dock = None
        (root / "layout_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        problems = [row for row in report if row["problems"]]
        print(
            "LAYOUT_REPORT",
            root,
            "panels",
            len(report),
            "with problems",
            len(problems),
            flush=True,
        )
        for row in problems:
            print(row, flush=True)
        assert not problems, "Actionable layout overflow; see layout_report.json"
    finally:
        if dock is not None:
            dock.disconnect_project()
            dock.close()
            sip.delete(dock)
        if previous is None:
            settings.remove(LANGUAGE_KEY)
        else:
            settings.setValue(LANGUAGE_KEY, previous)
        QgsProject.instance().clear()
        QgsApplication.processingRegistry().removeProvider(provider)
        app.exitQgis()


if __name__ == "__main__":
    main()
