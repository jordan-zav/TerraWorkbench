"""Confirmed/cancelled cleanup of an isolated active QGIS profile, never real data."""

import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType
from unittest.mock import patch

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QSettings, QCoreApplication
from qgis.PyQt.QtGui import QFont, QFontDatabase
from qgis.PyQt.QtWidgets import QMessageBox

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main():
    from TerraWorkbench.embedded_qpip.manager import dependency_directory, _active_profile_root
    from TerraWorkbench.ui.dependency_dialog import DependencyDialog
    from TerraWorkbench.ui.i18n import set_language

    root = Path(tempfile.mkdtemp(prefix="tw_cleanup_"))
    profile = root / "arbitrary-custom-root/selected"
    profile.mkdir(parents=True)
    QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication([], False, str(profile))
    app.initQgis()
    if os.name == "nt" and "WINDIR" in os.environ:
        QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts/arial.ttf"))
    app.setFont(QFont("Arial", 10))
    QCoreApplication.setOrganizationName("TerraWorkbenchCleanupTest")
    QCoreApplication.setApplicationName("Isolated")
    profile = _active_profile_root()
    assert profile.is_relative_to(Path(tempfile.gettempdir()).resolve()), profile
    habitual = root / "appdata/QGIS/QGIS3/profiles/default"
    habitual.mkdir(parents=True)
    habitual_sentinel = habitual / "keep.dat"
    habitual_sentinel.write_text("keep", encoding="utf-8")
    keys = ["addFinalResultToProject", "confirmClearStack", "defaultBand", "defaultOutputDirectory",
            "dependencyDialogVersion", "geosoftLocation", "keepIntermediate", "language",
            "localTestDataDirectory", "openInspectorAfterAdd", "showScientificTooltips", "surveyWorkspace"]
    results = []
    settings = QSettings()
    for locale in ("en", "es", "pt"):
        with patch.dict(os.environ, {"APPDATA": str(root / "appdata")}):
            target = dependency_directory()
            assert target.is_relative_to(profile)
            target.mkdir(parents=True)
            (target / "fake-package").mkdir()
            (target / "payload.dat").write_bytes(b"abc")
            (target / "fake-package/data.bin").write_bytes(b"12345")
            sibling = target.parent / "99.99"
            sibling.mkdir(exist_ok=True)
            (sibling / "keep.dat").write_bytes(b"keep")
            for key in keys:
                settings.setValue("TerraWorkbench/" + key, "test")
            set_language(locale)
            settings.setValue("OtherPlugin/keep", "unrelated")
            settings.setValue("TerraWorkbenchOther/keep", "near-prefix")
            settings.sync()
            dialog = DependencyDialog()

            def confirm(box, answer):
                assert str(target) in box.text() and "8 bytes" in box.text()
                assert all("TerraWorkbench/" + key in box.text() for key in keys)
                box.show()
                app.processEvents()
                suffix = "cancel" if answer == QMessageBox.No else "confirm"
                box.grab().save(str(root / f"cleanup-{locale}-{suffix}.png"))
                box.hide()
                return answer

            def abort_error(*args):
                raise AssertionError("Unexpected cleanup warning: " + str(args[-1]))

            in_use = {
                "en": "Some dependencies are in use in this session. Restart QGIS and use this button before opening any TerraWorkbench tool.",
                "es": "Algunas dependencias están en uso en esta sesión. Reinicie QGIS y use este botón antes de abrir cualquier herramienta de TerraWorkbench.",
                "pt": "Algumas dependências estão em uso nesta sessão. Reinicie o QGIS e use este botão antes de abrir qualquer ferramenta do TerraWorkbench.",
            }
            before = {p.relative_to(target).as_posix(): p.read_bytes()
                      for p in target.rglob("*") if p.is_file()}
            before_keys = {key: settings.value(key) for key in settings.allKeys()}

            def unchanged():
                assert {p.relative_to(target).as_posix(): p.read_bytes()
                        for p in target.rglob("*") if p.is_file()} == before
                settings.sync()
                assert {key: settings.value(key) for key in settings.allKeys()} == before_keys
                assert not dialog.cleanup_completed

            for attribute in ("__file__", "__path__"):
                loaded = ModuleType("tw_cleanup_in_use_fixture")
                setattr(loaded, attribute, str(target / "locked.pyd") if attribute == "__file__"
                        else [str(target / "fake-package")])
                with patch.dict(sys.modules, {loaded.__name__: loaded}), patch.object(
                    QMessageBox, "warning"
                ) as warning, patch.object(QMessageBox, "exec") as confirmation:
                    assert dialog.cleanup() is False
                    confirmation.assert_not_called()
                    warning.assert_called_once()
                    assert warning.call_args.args[2] == in_use[locale]
                unchanged()

            # A dependency may become loaded while confirmation is open.
            loaded = ModuleType("tw_cleanup_late_import_fixture")
            loaded.__file__ = str(root / "outside.pyd")

            def load_during_confirmation(box):
                answer = confirm(box, QMessageBox.Yes)
                loaded.__file__ = str(target / "locked.pyd")
                return answer

            with patch.dict(sys.modules, {loaded.__name__: loaded}), patch.object(
                QMessageBox, "warning"
            ) as warning, patch.object(QMessageBox, "exec", load_during_confirmation):
                assert dialog.cleanup() is False
                warning.assert_called_once()
                assert warning.call_args.args[2] == in_use[locale]
            unchanged()

            with patch("TerraWorkbench.ui.dependency_dialog._active_profile_root",
                       side_effect=RuntimeError("profile fixture unavailable")), patch.object(
                QMessageBox, "warning"
            ) as warning, patch.object(QMessageBox, "exec") as confirmation:
                assert dialog.cleanup() is False
                confirmation.assert_not_called()
                warning.assert_called_once()
                assert "profile fixture unavailable" in warning.call_args.args[2]
            unchanged()

            with patch.object(QMessageBox, "warning", abort_error), patch.object(QMessageBox, "exec", lambda box: confirm(box, QMessageBox.No)):
                assert dialog.cleanup() is False
            assert (target / "payload.dat").exists()
            assert len([k for k in settings.allKeys() if k.startswith("TerraWorkbench/")]) == 12
            with patch.object(QMessageBox, "warning", abort_error), patch.object(QMessageBox, "exec", lambda box: confirm(box, QMessageBox.Yes)), patch.object(QMessageBox, "information") as info:
                assert dialog.cleanup() is True
                assert info.called
            settings.sync()
            assert not target.exists()
            assert not [k for k in settings.allKeys() if k.startswith("TerraWorkbench/")]
            assert settings.value("OtherPlugin/keep") == "unrelated"
            assert settings.value("TerraWorkbenchOther/keep") == "near-prefix"
            assert (sibling / "keep.dat").read_bytes() == b"keep"
            assert habitual_sentinel.read_text(encoding="utf-8") == "keep"
            assert dialog.cleanup_completed and not dialog.install_button.isEnabled()
            dialog.show()
            app.processEvents()
            dialog.grab().save(str(root / f"cleanup-{locale}-complete.png"))
            dialog.close()
            results.append({"locale": locale, "files_removed": 2, "bytes_removed": 8, "keys_removed": 12,
                            "unrelated_state_preserved": True, "loaded_file_blocked": True,
                            "loaded_namespace_blocked": True, "late_import_blocked": True,
                            "unavailable_profile_handled": True})
    (root / "result.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("PASS: confirmed cleanup, cancellation, exact inventory, active custom profile and unrelated state", root)


if __name__ == "__main__":
    main()
