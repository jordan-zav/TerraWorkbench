"""Exercise the workspace filtering action and versioned flow graph in QGIS."""

import os
import copy
import json
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QSettings, QUrl
from qgis.PyQt.QtGui import QFont, QFontDatabase
from qgis.PyQt.QtTest import QTest
from qgis.PyQt import sip

from TerraWorkbench.ui.channel_filter_dialog import ChannelFilterDialog, suggested_name
from TerraWorkbench.compat.channel_filters import ChannelFilterOptions
from TerraWorkbench.ui.channel_pipeline_dialog import ChannelPipelineDialog
from TerraWorkbench.ui.i18n import LANGUAGE_KEY, set_language
from TerraWorkbench.ui.survey_workspace_dialog import SurveyWorkspaceDialog, KEY_WORKSPACE


def main():
    QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication([], False)
    app.initQgis()
    if os.name == "nt":
        QFontDatabase.addApplicationFont(
            str(Path(os.environ["WINDIR"]) / "Fonts" / "arial.ttf")
        )
    app.setFont(QFont("Arial", 10))
    settings = QSettings()
    previous = {key: settings.value(key, None) for key in (KEY_WORKSPACE, LANGUAGE_KEY)}
    settings.remove(KEY_WORKSPACE)
    original_exec = ChannelFilterDialog.exec
    workspace = None
    try:
        with tempfile.TemporaryDirectory(prefix="tw_channel_filters_") as folder:
            source = Path(folder) / "survey.csv"
            source.write_text(
                "line,time,mag,base\n"
                + "".join(f"L1,{i},{i + 100},5\n" for i in range(100)),
                encoding="utf-8",
            )
            workspace = SurveyWorkspaceDialog()
            workspace.set_project(Path(folder) / "project", create=True)
            database = workspace.store.import_file(source)
            workspace.store.derive(
                database, "mag_corrected", 'c("mag")-c("base")', "nT"
            )
            workspace.refresh()
            errors = []
            workspace.fail = errors.append
            for lang in ("en", "es", "pt"):
                set_language(lang)
                dialog = ChannelFilterDialog(workspace.store, database, "mag_corrected")
                dialog.domain.setCurrentIndex(dialog.domain.findData("time"))
                dialog.axis.setCurrentIndex(dialog.axis.findData("time"))
                dialog.group.setCurrentIndex(dialog.group.findData("line"))
                dialog.sensor.setCurrentIndex(1)
                assert dialog.output.text() == "mag_corrected__mean_w5_time"
                dialog.method.setCurrentIndex(dialog.method.findData("lowpass"))
                assert "lowpass_n4_f0.1_time" in dialog.output.text()
                dialog.output.setText("custom_name")
                dialog.method.setCurrentIndex(dialog.method.findData("median"))
                assert dialog.output.text() == "custom_name"
                dialog.show()
                app.processEvents()
                assert dialog.grab().save(
                    str(Path(tempfile.gettempdir()) / f"tw_filter_{lang}.png")
                )
                dialog.accept()
                assert dialog.options.method == "median"
                options = dialog.options
                repeated = ChannelFilterDialog(
                    workspace.store, database, "mag_corrected"
                )
                repeated.apply_options("mag_corrected", options)
                assert repeated.settings().to_dict() == options.to_dict()
                assert repeated.output.text() not in repeated.existing
                sip.delete(repeated)
                sip.delete(dialog)
                print(
                    f"PASS {lang}: filter settings, explicit grouping, naming and custom override",
                    flush=True,
                )

            def accept_filter(dialog):
                dialog.channel.setCurrentText("mag_corrected")
                dialog.group.setCurrentIndex(dialog.group.findData("line"))
                dialog.sensor.setCurrentIndex(1)
                dialog.accept()
                return dialog.result()

            ChannelFilterDialog.exec = accept_filter
            workspace.filter_signal()
            deadline = time.monotonic() + 30
            while workspace.worker is not None and time.monotonic() < deadline:
                app.processEvents()
                QTest.qWait(10)
            assert workspace.worker is None and not errors, errors
            output = "mag_corrected__mean_w5_samples"
            graph = workspace.store.channel_pipeline(database, output)
            original_graph = copy.deepcopy(graph)
            assert len(graph["nodes"]) == 5  # mean, formula, line, mag, base
            assert (
                suggested_name("mag_corrected", ChannelFilterOptions(), {output})
                == output + "_2"
            )
            for lang in ("en", "es", "pt"):
                set_language(lang)
                pipeline = ChannelPipelineDialog(graph)
                pipeline.show()
                app.processEvents()
                assert pipeline.stages.count() == len(graph["nodes"])
                assert pipeline.current_key == graph["root"]
                assert pipeline.reuse_button.isEnabled()
                assert pipeline.inspector.currentIndex() == 0
                assert "numpy" in pipeline.overview.toPlainText()
                assert "scipy" in pipeline.overview.toPlainText()
                assert "3000000" in pipeline.overview.toPlainText()
                assert (
                    json.loads(pipeline.details.toPlainText())
                    == graph["nodes"][graph["root"]]
                )
                parent = next(
                    edge["source"]
                    for edge in graph["edges"]
                    if edge["target"] == graph["root"]
                )
                pipeline.follow_input(QUrl("version:" + parent))
                assert pipeline.current_key == parent
                assert pipeline.stages.currentData() == parent
                assert pipeline.node_items[parent].isSelected()
                pipeline.follow_input(QUrl("https://example.com"))
                assert pipeline.current_key == parent
                pipeline.stages.setCurrentIndex(pipeline.stages.findData(graph["root"]))
                assert pipeline.current_key == graph["root"]
                nodes = [item for item in pipeline.scene.items() if item.data(0)]
                assert len(nodes) == 5
                nodes[0].setSelected(True)
                app.processEvents()
                assert "provenance" in pipeline.details.toPlainText()
                pipeline.output_button.click()
                assert pipeline.current_key == graph["root"]
                assert graph == original_graph
                assert pipeline.grab().save(
                    str(Path(tempfile.gettempdir()) / f"tw_pipeline_{lang}.png")
                )
                sip.delete(pipeline)
                print(
                    f"PASS {lang}: branched pipeline graph and selectable provenance",
                    flush=True,
                )
            unsafe_graph = copy.deepcopy(graph)
            reused_node = graph["nodes"][graph["root"]]
            workspace.reuse_channel_step(database, reused_node)
            deadline = time.monotonic() + 30
            while workspace.worker is not None and time.monotonic() < deadline:
                app.processEvents()
                QTest.qWait(10)
            assert workspace.worker is None and not errors, errors
            replayed = workspace.store.channel_pipeline(database, output + "_2")
            assert (
                replayed["nodes"][replayed["root"]]["provenance"]["reused_from_version"]
                == reused_node["id"]
            )
            unsafe_graph["nodes"][graph["root"]]["name"] = "<img src=x> & signal"
            unsafe_graph["nodes"][graph["root"]]["provenance"]["parameters"][
                "method"
            ] = "future_method"
            check = ChannelPipelineDialog(unsafe_graph)
            assert "&lt;img src=x&gt;" in check.summary_html(graph["root"])
            assert "<img src=x> & signal" in check.overview.toPlainText()
            assert "future_method" in check.overview.toPlainText()
            sip.delete(check)
            print(
                "PASS workspace action, worker filtering, unique names and exact-version lineage",
                flush=True,
            )
    finally:
        ChannelFilterDialog.exec = original_exec
        if workspace is not None:
            workspace.dispose()
            app.processEvents()
        for key, value in previous.items():
            if value is None:
                settings.remove(key)
            else:
                settings.setValue(key, value)


if __name__ == "__main__":
    main()
