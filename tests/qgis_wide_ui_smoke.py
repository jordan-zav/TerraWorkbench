"""Real-QGIS catalogue/forms and session task-history checks, no engine runs."""

import os
from pathlib import Path
import sys
import tempfile
import json
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from qgis.core import QgsApplication
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtGui import QFont, QFontDatabase
from qgis.PyQt.QtTest import QTest

from TerraWorkbench.ui.i18n import LANGUAGE_KEY, set_language
from TerraWorkbench.ui.process_centre import ProcessCentre
from TerraWorkbench.qgis_plugin.provider import TerraWorkbenchProvider
from TerraWorkbench.ui.survey_workspace_dialog import tr
from TerraWorkbench.ui.task_history_widget import TaskHistoryWidget
from TerraWorkbench.ui.core_job_dialog import CoreJobDialog
from TerraWorkbench.qgis_plugin.qgis_compat import dispose_with_workers
from TerraWorkbench.ui.survey_workspace_dialog import StoreWorker


def main():
    prefix = os.environ["QGIS_PREFIX_PATH"]
    sys.path.insert(0, str(Path(prefix) / "python" / "plugins"))
    app = QgsApplication([], False)
    app.setPrefixPath(prefix, True)
    app.initQgis()
    if os.name == "nt":
        QFontDatabase.addApplicationFont(
            str(Path(os.environ["WINDIR"]) / "Fonts" / "arial.ttf")
        )
    app.setFont(QFont("Arial", 10))
    from processing.core.Processing import Processing
    import processing

    Processing.initialize()
    provider = TerraWorkbenchProvider()
    QgsApplication.processingRegistry().addProvider(provider)
    settings = QSettings()
    previous = settings.value(LANGUAGE_KEY, None)
    try:
        from qgis.PyQt.QtWidgets import QWidget, QDialog
        from threading import Event

        owner = QWidget()
        child = QDialog(owner)
        acknowledged = []

        def until_cancel(cancel, progress):
            while not cancel():
                Event().wait(0.002)
            raise InterruptedError("Expected lifecycle cancellation")

        worker = StoreWorker(until_cancel, child)
        worker.cancelled.connect(lambda: acknowledged.append(True))
        worker.start()
        dispose_with_workers(owner)
        deadline = time.monotonic() + 20
        while not sip.isdeleted(owner) and time.monotonic() < deadline:
            QTest.qWait(10)
            app.processEvents()
        assert sip.isdeleted(owner) and acknowledged
        for lang in ("en", "es", "pt"):
            set_language(lang)
            centre = ProcessCentre()
            centre.show()
            app.processEvents()
            qgis_keys = [
                key for key, (kind, _) in centre.entries.items() if kind == "qgis"
            ]
            core_keys = [
                key for key, (kind, _) in centre.entries.items() if kind == "core"
            ]
            assert len(qgis_keys) == len(provider.algorithms())
            assert len(core_keys) >= 73
            items = {
                centre.tree.topLevelItem(i)
                .child(j)
                .data(0, 256): centre.tree.topLevelItem(i).child(j)
                for i in range(centre.tree.topLevelItemCount())
                for j in range(centre.tree.topLevelItem(i).childCount())
            }
            for key in core_keys:
                centre.tree.setCurrentItem(items[key])
                description = centre.browser.toPlainText()
                assert key.removeprefix("core:") in description and "base_libraries" not in description, (
                    key,
                    centre.browser.toPlainText(),
                )
                assert centre.launch.isEnabled()
            for term in (
                "radiometry",
                "electrical",
                "gravity",
                "borehole",
                "gpr",
                "mt",
            ):
                assert any(term in key for key in core_keys), term
            centre.tree.setCurrentItem(items[qgis_keys[0]])
            assert centre.launch.isEnabled()
            launched = []
            original_exec = processing.execAlgorithmDialog
            from processing.gui.AlgorithmDialog import AlgorithmDialog
            from qgis.PyQt.QtWidgets import QMessageBox

            original_warning = QMessageBox.warning

            def fail_warning(*args):
                raise AssertionError(str(args[-1]))

            def open_without_running(key, parameters):
                form = AlgorithmDialog(
                    QgsApplication.processingRegistry().createAlgorithmById(key),
                    parent=None,
                )
                assert form is not None
                form.show()
                app.processEvents()
                launched.append(key)
                form.reject()
                sip.delete(form)

            try:
                processing.execAlgorithmDialog = open_without_running
                QMessageBox.warning = fail_warning
                centre.open_form()
            finally:
                processing.execAlgorithmDialog = original_exec
                QMessageBox.warning = original_warning
            assert launched == [qgis_keys[0]]
            centre.mode.setCurrentIndex(centre.mode.findData("core"))
            assert not centre.launch.isEnabled()
            centre.search.setText("radiometry")
            visible = [
                key
                for key, item in items.items()
                if not item.isHidden() and not item.parent().isHidden()
            ]
            assert visible and all(
                key.startswith("core:radiometry.") for key in visible
            )
            centre.search.clear()
            centre.mode.setCurrentIndex(0)
            shot = Path(tempfile.gettempdir()) / f"tw_process_centre_{lang}.png"
            assert centre.grab().save(str(shot))
            centre.close()
            sip.delete(centre)
            tasks = TaskHistoryWidget(tr)
            requests = []
            tasks.cancelRequested.connect(lambda: requests.append(True))
            tasks.begin("Synthetic read")
            tasks.progress(650)
            tasks.request_cancel()
            assert tasks.active["state"] == "cancel_requested" and requests == [True]
            tasks.finish("cancelled", "Reader acknowledged cancellation")
            assert tasks.records[-1]["state"] == "cancelled"
            tasks.begin("Synthetic failure")
            tasks.finish("failed", "Deliberate test error")
            assert (
                tasks.toggle.isChecked()
                and "Deliberate test error" in tasks.message.toPlainText()
            )
            tasks.begin("Synthetic completion")
            tasks.finish("completed", "No source data changed")
            assert len(tasks.records) == 3
            sip.delete(tasks)
            with tempfile.TemporaryDirectory(prefix="tw_core_console_") as folder:
                console = CoreJobDialog("gpr.dewow")
                console.insert_required()
                assert set(json.loads(console.parameters.toPlainText())) == {
                    "traces",
                    "dt_s",
                    "window_samples",
                }
                console.parameters.setPlainText(
                    '{"traces": [[1,2,3,4,5,6]], "dt_s": 0.01, "window_samples": 3}'
                )
                console.parameter_form.set_parameters(
                    json.loads(console.parameters.toPlainText())
                )
                console.parameter_tabs.setCurrentIndex(0)
                console.output_path.setText(folder)
                console.run()
                deadline = time.monotonic() + 40
                while console.worker is not None and time.monotonic() < deadline:
                    QTest.qWait(10)
                    app.processEvents()
                assert console.worker is None
                assert console.result is not None, console.status.text()
                assert console.result["status"] == "completed"
                assert Path(console.result["manifest"]).is_file()
                console.parameters.setPlainText('{"traces": []}')
                console.parameter_tabs.setCurrentIndex(1)
                console.run()
                deadline = time.monotonic() + 40
                while console.worker is not None and time.monotonic() < deadline:
                    QTest.qWait(10)
                    app.processEvents()
                assert (
                    console.worker is None
                    and console.tasks.records[-1]["state"] == "failed"
                )
                assert console.queue_paused
                valid_text = (
                    '{"traces": [[1,2,3,4,5,6]], "dt_s": 0.01, "window_samples": 3}'
                )
                console.parameters.setPlainText(valid_text)
                console.run()
                console.parameters.setPlainText(valid_text.replace("0.01", "0.02"))
                console.run()
                assert len(console.pending) == 2 and console.worker is None
                original_ids = [job["id"] for job in console.pending]
                console.queue_list.setCurrentRow(0)
                console.move_queued(1)
                assert [job["id"] for job in console.pending] == list(
                    reversed(original_ids)
                )
                console.cancel_queued()
                assert len(console.pending) == 1
                console.pause_queue.setChecked(False)
                deadline = time.monotonic() + 40
                while console.worker is not None and time.monotonic() < deadline:
                    QTest.qWait(10)
                    app.processEvents()
                assert console.worker is None and not console.pending
                assert console.tasks.records[-1]["state"] == "completed"
                console.parameter_form.set_parameters(json.loads(valid_text))
                console.parameter_tabs.setCurrentIndex(0)
                console.show()
                app.processEvents()
                assert console.grab().save(
                    str(Path(tempfile.gettempdir()) / f"tw_core_console_{lang}.png")
                )
                console.close()
                sip.delete(console)
            print(
                f"PASS {lang}: {len(qgis_keys)} QGIS forms, {len(core_keys)} documented Core APIs, actual form construction, search, cancellation and failure history; {shot}",
                flush=True,
            )
    finally:
        if previous is None:
            settings.remove(LANGUAGE_KEY)
        else:
            settings.setValue(LANGUAGE_KEY, previous)
        QgsApplication.processingRegistry().removeProvider(provider)


if __name__ == "__main__":
    main()
