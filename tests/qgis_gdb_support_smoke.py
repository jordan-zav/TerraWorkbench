"""Real offscreen GDB consent, Close, optional states and cancellation; never GX."""

import importlib.abc
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

from packaging.requirements import Requirement
from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QProcess, QSettings, QTimer, Qt
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QDialog, QMessageBox

from TerraWorkbench.embedded_qpip.manager import RequirementStatus
from TerraWorkbench.ui import dependency_dialog as module
from TerraWorkbench.ui import workflow_dock
from TerraWorkbench.ui.i18n import set_language


class NoGX(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"geosoft", "gxapi", "gxpy"}:
            raise AssertionError("A test must never load GX: " + fullname)


def main():
    assert os.environ["QT_QPA_PLATFORM"] == "offscreen"
    assert os.environ["QT_QPA_FONTDIR"] == r"C:\Windows\Fonts"
    evidence = Path(os.environ.get("TW_GDB_EVIDENCE", os.environ["TEMP"]))
    evidence.mkdir(parents=True, exist_ok=True)
    app = QgsApplication([], False)
    app.initQgis()
    app.setFont(QFont("Arial", 10))
    blocker = NoGX()
    sys.meta_path.insert(0, blocker)
    results = []
    root = evidence / "fake-support"
    root.mkdir(exist_ok=True)
    dotnet_ready = [True]
    installed = [False, False]
    messages, progress = [], []
    answer = [QMessageBox.No]
    reenter = [None]
    real_exec = QMessageBox.exec
    real_find_spec = module.importlib.util.find_spec
    dock = None

    def status(**kwargs):
        return (
            RequirementStatus(Requirement("harmonica>=0.7,<0.8"), "0.7.0", True),
            RequirementStatus(Requirement("geosoft>=2024.2,<2025"),
                              "2024.2" if installed[0] else None, installed[0]),
        )

    def spec(name, *args, **kwargs):
        if name == "geosoft":
            return object() if installed[0] else None
        return real_find_spec(name, *args, **kwargs)

    def consent(box):
        messages.append(box.text())
        if reenter[0] is not None:
            reenter[0]()
        box.show()
        app.processEvents()
        if box.standardButtons() == (QMessageBox.Yes | QMessageBox.No) and "345 MiB" in box.text():
            assert "BSD-2-Clause" in box.informativeText()
            assert "https://geosoftgxdev.atlassian.net/" in box.informativeText()
            assert box.checkBox() is not None
            locale = QSettings().value("TerraWorkbench/languagePreference")
            capture = evidence / f"confirmation-{locale}.png"
            if not capture.exists():
                assert box.grab().save(str(capture))
        selected = box.button(answer[0]) or box.button(QMessageBox.Cancel)
        assert selected is not None, box.text()
        QTimer.singleShot(0, selected.click)
        return real_exec(box)

    def finish_install(dialog):
        # Both constructors must receive a callable log callback. No QProcess starts.
        assert callable(dialog.log_callback)
        progress.append(dialog.args)
        if "pip" in dialog.args:
            installed[0] = True
        else:
            installed[1] = True
            if "--prepare-dotnet" in dialog.args:
                dotnet_ready[0] = True
        return 0, False, "simulated install"

    try:
        with patch.object(module, "dependency_status", side_effect=status), patch.object(
            module, "dependency_directory", return_value=root
        ), patch.object(workflow_dock, "dependency_directory", return_value=root), patch.object(
            module, "managed_gx_runtime", side_effect=lambda path: root / "runtime" if installed[1] else None
        ), patch.object(module.importlib.util, "find_spec", side_effect=spec), patch.object(
            module, "gdb_dotnet_ready", side_effect=lambda: dotnet_ready[0]
        ), patch.object(
            module, "find_seequent_connector", return_value=root / "GeosoftConnect.exe"
        ), patch.object(workflow_dock, "find_geosoft_runtime", return_value=None
        ), patch.object(QProcess, "start", side_effect=AssertionError("No real child process is allowed")), patch.object(
            QMessageBox, "exec", new=consent
        ), patch.object(QMessageBox, "warning", side_effect=AssertionError("Unexpected warning")), patch.object(
            module.PipInstallProgressDialog, "execute", new=finish_install
        ), patch.object(module.GDBRuntimeProgressDialog, "execute", new=finish_install):
            # The optional package does not force the full manager at startup.
            with patch.object(module, "DependencyDialog", side_effect=AssertionError("Startup reopened manager")):
                module.show_dependency_dialog()
            results.append("optional_missing_does_not_open_startup_manager")

            for locale in ("es", "en", "pt"):
                set_language(locale)
                for failure in (
                    {"error_code": "invalid_redist_configuration", "error": "denied"},
                    {"dll": "geodist.dll", "missing_dlls": ["missing.dll"], "missing_frameworks": [{"major": "6"}]},
                ):
                    message = module.runtime_error_message("TW_GX_CHECK:" + json.dumps(failure))
                    assert "Traceback" not in message
                    if failure.get("missing_frameworks"):
                        assert "missing.dll" in message and "dotnet.microsoft.com" in message
                    else:
                        assert "geosoft.redist" in message and "denied" in message
                with patch.object(module, "find_seequent_connector", return_value=None), patch.object(
                    QMessageBox, "information"
                ) as information:
                    before = len(progress)
                    assert not module.prepare_gdb_support()
                    assert len(progress) == before
                    notice = information.call_args.args[2]
                    assert "Seequent ID" in notice and "XYZ" in notice and "CSV" in notice
                    assert "seequent.com" in notice
                results.append("missing_connect_stops_before_download_" + locale)
                QSettings().remove("TerraWorkbench/gxConversionNoticeHidden")
                assert module.confirm_gx_conversion(prepare=True) is False
                for ready in (False, True):
                    installed[:] = [ready, ready]
                    dialog = module.DependencyDialog(gdb_context=not ready)
                    dialog.show()
                    app.processEvents()
                    assert dialog.gdb_button.isEnabled() is not ready
                    assert not dialog.install_button.isEnabled()
                    assert dialog.gdb_button.styleSheet() == dialog.install_button.styleSheet()
                    html = dialog.browser.toHtml()
                    assert ("#1b7f3a" if ready else "#9a6700") in html
                    assert "BSD-2-Clause" in dialog.browser.toPlainText()
                    if not ready:
                        assert dialog.gdb_button.hasFocus() and "GDB" in dialog.gdb_note.text()
                    assert dialog.grab().save(str(evidence / f"manager-{'installed' if ready else 'missing'}-{locale}.png"))
                    closed = []
                    dialog.rejected.connect(lambda: closed.append(True))
                    watchdog = QTimer(dialog)
                    watchdog.setSingleShot(True)
                    watchdog.timeout.connect(lambda d=dialog: QDialog.reject(d))
                    watchdog.start(2000)
                    QTimer.singleShot(0, lambda d=dialog: QTest.mouseClick(d.close_button, Qt.LeftButton))
                    assert dialog.exec() == QDialog.Rejected
                    assert watchdog.isActive(), "Close timed out"
                    watchdog.stop()
                    assert closed == [True] and not dialog.isVisible()
                    dialog.deleteLater()
                results.append("close_first_click_and_optional_states_" + locale)

            with patch.object(module.sys, "platform", "linux"):
                dialog = module.DependencyDialog()
                assert not dialog.gdb_button.isEnabled()
                assert "neste sistema" in dialog.browser.toPlainText()
                dialog.close()
                dialog.deleteLater()
            results.append("unsupported_platform_disabled")

            set_language("es")
            installed[:] = [True, False]
            manager = module.DependencyDialog()
            with patch.object(module, "prepare_gdb_support", return_value=False) as shared:
                QTest.mouseClick(manager.gdb_button, Qt.LeftButton)
                shared.assert_called_once_with(manager)
            manager.close()
            manager.deleteLater()
            results.append("manager_button_uses_shared_preparation")
            dock = workflow_dock.FilterStackDock()
            with patch.object(module, "DependencyDialog", side_effect=AssertionError("Import opened full manager")), patch.object(
                workflow_dock.QFileDialog, "getOpenFileName", return_value=("synthetic.gdb", "")
            ):
                before = len(messages)
                with patch.object(workflow_dock.QFileDialog, "getOpenFileName", return_value=("", "")):
                    dock.import_geosoft_action.trigger()
                assert len(messages) == before and not dock._gdb_import_active
                results.append("cancelled_file_chooser_is_silent")
                # A second QAction event during consent must not nest/reopen a dialog.
                reenter[0] = dock.import_geosoft_action.trigger
                before = len(messages)
                dock.import_geosoft_action.trigger()
                app.processEvents()
                assert len(messages) == before + 1 and not progress
                assert not dock._gdb_import_active
                results.append("cancelled_consent_no_reopen_even_on_reentry")
                reenter[0] = None

                # One consent, package/runtime progress, then the actual import choices.
                answer[0] = QMessageBox.Yes
                installed[:] = [False, False]
                before = len(messages)
                dock.import_geosoft_gdb("synthetic.gdb")
                assert installed == [True, True] and len(progress) == 2
                assert len(messages) == before + 2  # one combined consent, then data choice
                assert "345 MiB" in messages[-2] and "345 MiB" not in messages[-1]
                results.append("one_consent_installs_both_and_resumes_import")

                answer[0] = QMessageBox.Cancel
                QSettings().remove("TerraWorkbench/gxConversionNoticeHidden")
                before = len(messages)
                assert dock._geosoft_runtime() is None
                assert len(messages) == before + 1
                assert "While app is running" in messages[-1]
                results.append("cancelled_factual_notice_stops_ready_import")
                answer[0] = QMessageBox.Yes

                dotnet_ready[0] = False
                before = len(messages)
                downloads = len(progress)
                assert module.prepare_gdb_support(dock)
                assert len(messages) == before + 1
                assert "66 MiB" in messages[-1] and "345 MiB" not in messages[-1]
                assert len(progress) == downloads + 1 and "--prepare-dotnet" in progress[-1]
                results.append("gx_ready_prepares_only_dotnet_with_one_consent")

                # Ready support never calls preparation or the dependency manager.
                QSettings().setValue("TerraWorkbench/gxConversionNoticeHidden", True)
                before = len(messages)
                with patch.object(module, "prepare_gdb_support", side_effect=AssertionError("Already ready")):
                    assert dock._geosoft_runtime() is not None
                assert len(messages) == before
                results.append("ready_support_no_dependency_or_preparation_dialog")

                # Cancelling either child aborts silently and cannot show the data choices.
                for package, code in ((False, -9), (True, -9), (False, 0), (True, 0)):
                    installed[:] = [package, False]
                    before = len(messages)
                    with patch.object(module.PipInstallProgressDialog, "execute", return_value=(code, True, "cancelled")), patch.object(
                        module.GDBRuntimeProgressDialog, "execute", return_value=(code, True, "cancelled")
                    ):
                        dock.import_geosoft_gdb("synthetic.gdb")
                    assert len(messages) == before + 1 and not dock._gdb_import_active
                results.append("cancelled_package_or_runtime_progress_aborts_silently")

                # Hidden Seequent notice never implies consent to a new download.
                installed[:] = [False, False]
                answer[0] = QMessageBox.No
                before = len(messages)
                assert module.prepare_gdb_support(dock) is False
                assert len(messages) == before + 1
                results.append("hidden_notice_still_requires_download_consent")

            bar = module.GDBRuntimeProgressDialog(["never-executed"], ["Geosoft GX 2024.2 full runtime"],
                                                  "simulated", log_callback=lambda line: None)
            bar._consume_line("GX runtime: 181040530/362081059 bytes")
            assert next(iter(bar.rows.values()))[1].value() == 50
            # A running child defers reject only until its cancellation completes.
            bar.show()
            with patch.object(bar.process, "state", return_value=QProcess.ProcessState.Running), patch.object(bar.process, "kill") as kill:
                bar.reject()
                assert bar.cancelled and bar.isVisible()
                kill.assert_called_once()
            bar._finished(-9, QProcess.ExitStatus.CrashExit)
            assert not bar.isVisible()
            bar.deleteLater()
            results.append("runtime_byte_progress_and_child_cancel_lifecycle")

        (evidence / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print("PASS", len(results), "GDB flow checks", json.dumps(results), flush=True)
    finally:
        if dock is not None:
            dock.disconnect_project()
            dock.close()
        sys.meta_path.remove(blocker)
        app.processEvents()
        app.exitQgis()


if __name__ == "__main__":
    main()
