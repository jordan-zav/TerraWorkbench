"""TerraWorkbench's embedded, QPIP-derived dependency manager dialog."""

from __future__ import annotations

from html import escape
import sys

from qgis.PyQt.QtCore import QSettings, Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QMessageBox,
)

from ..embedded_qpip import (
    dependency_directory,
    dependency_status,
    inversion_supported,
    install_requirements,
)
from ..qgis_plugin.metadata_utils import plugin_version
from ..embedded_qpip.manager import _active_profile_root
from ..qgis_plugin.dependency_cleanup import (
    DependenciesInUseError, cleanup_plan, ensure_dependencies_not_in_use, remove_dependencies,
)
from .i18n import language, text


PLUGIN_VERSION = plugin_version()
SETTINGS_KEY = "TerraWorkbench/dependencyDialogVersion"
QPIP_URL = "https://github.com/opengisch/qpip"

DEPENDENCY_DETAILS = {
    "harmonica": ("BSD-3-Clause", "https://github.com/fatiando/harmonica"),
    "ppigrf": ("MIT", "https://github.com/IAGA-VMOD/ppigrf"),
    "pyproj": ("MIT", "https://pyproj4.github.io/pyproj/stable/"),
    "defusedxml": ("PSF", "https://github.com/tiran/defusedxml"),
    "simpeg": ("MIT", "https://github.com/simpeg/simpeg"),
    "discretize": ("MIT", "https://github.com/simpeg/discretize"),
    "choclo": ("BSD-3-Clause", "https://github.com/fatiando/choclo"),
    "geosoft": ("BSD-2-Clause", "https://pypi.org/project/geosoft/"),
}


def _qt_enum(owner, scoped_name, member_name, legacy_name):
    scoped_enum = getattr(owner, scoped_name, None)
    if scoped_enum is not None:
        return getattr(scoped_enum, member_name)
    return getattr(owner, legacy_name)


TEXT_SELECTABLE_BY_MOUSE = _qt_enum(
    Qt,
    "TextInteractionFlag",
    "TextSelectableByMouse",
    "TextSelectableByMouse",
)
DIALOG_CLOSE = _qt_enum(
    QDialogButtonBox,
    "StandardButton",
    "Close",
    "Close",
)
DIALOG_ACTION_ROLE = _qt_enum(
    QDialogButtonBox,
    "ButtonRole",
    "ActionRole",
    "ActionRole",
)


def _status_html(status):
    upstream, missing, conflict = {
        "en": ("See upstream", "Missing", "Version conflict ({version})"),
        "es": ("Consultar origen", "Falta", "Conflicto de versión ({version})"),
        "pt": ("Consultar origem", "Ausente", "Conflito de versão ({version})"),
    }[language()]
    rows = []
    for item in status:
        name = item.requirement.name
        license_name, repository = DEPENDENCY_DETAILS.get(
            name.casefold(), (upstream, "")
        )
        if item.satisfied:
            state = (
                '<span style="color:#1b7f3a;font-weight:600">'
                f"{text('Installed', 'Instalado')} {escape(item.installed_version)}</span>"
            )
        else:
            label = (
                missing
                if item.installed_version is None
                else conflict.format(version=item.installed_version)
            )
            state = f'<span style="color:#b42318;font-weight:700">{escape(label)}</span>'
        linked_name = f'<a href="{repository}">{escape(name)}</a>' if repository else escape(name)
        rows.append(
            "<tr>"
            f"<td>{linked_name}<br><code>{escape(str(item.requirement))}</code></td>"
            f"<td>{state}</td><td>{escape(license_name)}</td>"
            "</tr>"
        )
    return "".join(rows)


class DependencyDialog(QDialog):
    """Show version-aware status and install through the embedded progress UI."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(
            text(
                "TerraWorkbench — Dependency manager",
                "TerraWorkbench — Administrador de dependencias",
            )
        )
        self.cleanup_completed = False
        self.setMinimumSize(720, 540)
        self.resize(760, 580)

        layout = QVBoxLayout(self)
        self.heading = QLabel()
        self.heading.setStyleSheet("font-size: 15px; font-weight: 600; margin: 4px;")
        layout.addWidget(self.heading)

        self.browser = QTextBrowser(self)
        self.browser.setOpenExternalLinks(True)
        layout.addWidget(self.browser, 1)

        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setTextInteractionFlags(TEXT_SELECTABLE_BY_MOUSE)
        layout.addWidget(self.note)

        buttons = QDialogButtonBox(DIALOG_CLOSE, parent=self)
        self.install_button = QPushButton(self)
        self.install_button.setDefault(True)
        self.install_button.setAutoDefault(True)
        self.install_button.setStyleSheet("font-weight: 600; padding: 6px 12px;")
        self.reinstall_button = QPushButton(self)
        self.inversion_button = QPushButton(self)
        self.folder_button = QPushButton(self)
        self.upstream_button = QPushButton(self)
        for button in (
            self.install_button,
            self.reinstall_button,
            self.inversion_button,
            self.folder_button,
            self.upstream_button,
        ):
            buttons.addButton(button, DIALOG_ACTION_ROLE)
        self.install_button.clicked.connect(self.install_missing)
        self.reinstall_button.clicked.connect(self.reinstall_all)
        self.inversion_button.clicked.connect(self.install_inversion)
        self.folder_button.clicked.connect(self.open_dependency_folder)
        self.upstream_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(QPIP_URL))
        )
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.cleanup_button = QPushButton(self)
        self.cleanup_button.setAutoDefault(False)
        self.cleanup_button.clicked.connect(self.cleanup)
        layout.addWidget(self.cleanup_button)
        self.close_button = buttons.button(DIALOG_CLOSE)
        self.retranslate()
        self.refresh()

    def retranslate(self):
        self.setWindowTitle(
            text(
                "TerraWorkbench — Dependency manager",
                "TerraWorkbench — Administrador de dependencias",
            )
        )
        self.heading.setText(
            text(
                "TerraWorkbench scientific dependency manager",
                "Administrador de dependencias científicas de TerraWorkbench",
            )
        )
        self.install_button.setText(
            text("Install missing / repair", "Instalar faltantes / reparar")
        )
        self.reinstall_button.setText(text("Reinstall core", "Reinstalar núcleo"))
        self.inversion_button.setText(
            text("Install optional 3D inversion", "Instalar inversión 3D opcional")
        )
        self.folder_button.setText(
            text("Open dependency folder", "Abrir carpeta de dependencias")
        )
        self.upstream_button.setText(text("QPIP upstream", "Proyecto original QPIP"))
        self.cleanup_button.setText(text("Remove dependencies and preferences", "Eliminar dependencias y preferencias"))
        if self.close_button is not None:
            self.close_button.setText(text("Close", "Cerrar"))

    def refresh(self):
        core_status = dependency_status()
        self.status = dependency_status(include_inversion=inversion_supported())
        missing = [item for item in core_status if not item.satisfied]
        core_names = {item.requirement.name.casefold() for item in core_status}
        inversion_missing = [
            item
            for item in self.status
            if item.requirement.name.casefold() not in core_names and not item.satisfied
        ]
        self.browser.setHtml(
            f"<p>{text('This manager is built into TerraWorkbench from modified QPIP progress components. It manages only TerraWorkbench requirements and installs into the active QGIS user profile after explicit approval.', 'Este administrador está integrado en TerraWorkbench a partir de componentes de progreso modificados de QPIP. Solo administra los requisitos de TerraWorkbench y los instala en el perfil activo de QGIS después de una aprobación explícita.')}</p>"
            "<table cellspacing='0' cellpadding='7' width='100%' "
            "style='border-collapse:collapse'>"
            "<tr style='background:#e9eef4;font-weight:600'>"
            f"<td>{text('Package and requirement', 'Paquete y requisito')}</td><td>{text('Status', 'Estado')}</td><td>{text('License', 'Licencia')}</td></tr>"
            f"{_status_html(self.status)}</table>"
            f"<p><b>{text('Install location', 'Ubicación de instalación')}:</b><br>"
            f"<code>{dependency_directory()}</code></p>"
        )
        self.install_button.setEnabled(bool(missing))
        self.inversion_button.setEnabled(
            inversion_supported() and bool(inversion_missing)
        )
        self.note.setText(
            text(
                "Missing or conflicting dependencies remain.",
                "Quedan dependencias faltantes o en conflicto.",
            )
            if missing
            else text(
                "All direct requirements are satisfied. Restart QGIS after any repair.",
                "Todos los requisitos directos están satisfechos. Reinicie QGIS después de cualquier reparación.",
            )
        )
        if inversion_missing:
            self.note.setText(
                self.note.text()
                + "\n"
                + text(
                    "The optional 3D inversion stack is not installed; all 2D workflows remain ready.",
                    "La pila opcional de inversión 3D no está instalada; todos los flujos 2D siguen disponibles.",
                )
            )
        if not inversion_supported():
            self.note.setText(
                self.note.text()
                + "\n"
                + text(
                    "3D inversion requires QGIS with Python 3.11 or newer; the 2D tools remain available.",
                    "La inversión 3D requiere QGIS con Python 3.11 o posterior; las herramientas 2D siguen disponibles.",
                )
            )

    def install_missing(self):
        if install_requirements(self, force_all=False):
            self.refresh()

    def reinstall_all(self):
        if install_requirements(self, force_all=True):
            self.refresh()

    def install_inversion(self):
        if install_requirements(
            self, force_all=False, include_inversion=True, inversion_only=True
        ):
            self.refresh()

    def cleanup(self):
        """Confirm an exact inventory, then clean only this active profile."""
        settings = QSettings()
        finished_title = text("Cleanup complete", "Limpieza terminada")
        abort_title = text("Cleanup aborted", "Limpieza interrumpida")
        in_use_message = text(
            "Some dependencies are in use in this session. Restart QGIS and use this button before opening any TerraWorkbench tool.",
            "Algunas dependencias están en uso en esta sesión. Reinicie QGIS y use este botón antes de abrir cualquier herramienta de TerraWorkbench.")
        abort_message = text(
            "Cleanup stopped. Restart QGIS before using the plugin. Details: {error}",
            "La limpieza se detuvo. Reinicie QGIS antes de usar el complemento. Detalles: {error}")
        finished_message = text(
            "Restart QGIS. If TerraWorkbench is still installed, it will ask to reinstall dependencies.",
            "Reinicie QGIS. Si TerraWorkbench sigue instalado, pedirá reinstalar las dependencias.")
        keys = tuple(sorted(key for key in settings.allKeys() if key.startswith("TerraWorkbench/")))
        try:
            settings.sync()
            if settings.status() != QSettings.NoError or not settings.isWritable():
                raise OSError("The active settings store is not writable")
            plan = cleanup_plan(_active_profile_root(), dependency_directory(),
                                f"{sys.version_info.major}.{sys.version_info.minor}", keys)
            ensure_dependencies_not_in_use(plan.target)
            box = QMessageBox(self)
            box.setWindowTitle(text("Confirm cleanup", "Confirmar limpieza"))
            box.setIcon(QMessageBox.Warning)
            box.setTextFormat(_qt_enum(Qt, "TextFormat", "PlainText", "PlainText"))
            box.setText(text(
                "Folder: {path}\nFiles: {count}\nSize: {size} bytes\nSettings keys:\n{keys}\n\nRemove these dependencies and preferences?",
                "Carpeta: {path}\nArchivos: {count}\nTamaño: {size} bytes\nClaves de configuración:\n{keys}\n\n¿Eliminar estas dependencias y preferencias?"
            ).format(path=plan.target, count=plan.file_count, size=plan.total_bytes,
                     keys="\n".join(plan.setting_keys) or "—"))
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            box.setDefaultButton(QMessageBox.No)
            if box.exec() != QMessageBox.Yes:
                return False
            if (_active_profile_root() != plan.profile or dependency_directory() != plan.target
                    or QSettings().fileName() != settings.fileName()):
                raise ValueError("The active profile changed; request confirmation again")
            current = tuple(sorted(key for key in settings.allKeys() if key.startswith("TerraWorkbench/")))
            if current != plan.setting_keys:
                raise ValueError("Settings changed; request confirmation again")
            remove_dependencies(plan, confirmed=True)
            for key in plan.setting_keys:
                settings.remove(key)
            settings.sync()
            if settings.status() != QSettings.NoError:
                raise OSError("Could not save the cleaned settings")
        except DependenciesInUseError:
            QMessageBox.warning(self, abort_title, in_use_message)
            return False
        except (ValueError, OSError, RuntimeError) as error:
            QMessageBox.warning(self, abort_title, abort_message.format(error=error))
            return False
        self.cleanup_completed = True
        for button in (self.install_button, self.reinstall_button, self.inversion_button,
                       self.cleanup_button, self.folder_button):
            button.setEnabled(False)
        self.note.setText(finished_message)
        QMessageBox.information(self, finished_title, finished_message)
        return True

    @staticmethod
    def open_dependency_folder():
        path = dependency_directory()
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def open_dependency_dialog(parent=None):
    """Open the dependency manager on demand from the TerraWorkbench menu."""
    dialog = DependencyDialog(parent)
    dialog.exec()
    return dialog


def show_dependency_dialog(parent=None):
    """Show first on a new version, and every activation while requirements fail."""
    status = dependency_status()
    missing = any(not item.satisfied for item in status)
    settings = QSettings()
    already_seen = settings.value(SETTINGS_KEY, "", type=str) == PLUGIN_VERSION
    if already_seen and not missing:
        return

    dialog = DependencyDialog(parent)
    dialog.exec()
    if not dialog.cleanup_completed and not any(not item.satisfied for item in dependency_status()):
        settings.setValue(SETTINGS_KEY, PLUGIN_VERSION)
