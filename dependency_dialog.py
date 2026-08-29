"""TerraWorkbench's embedded, QPIP-derived dependency manager dialog."""

from __future__ import annotations

from qgis.PyQt.QtCore import QSettings, Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from .embedded_qpip import (
    dependency_directory,
    dependency_status,
    install_requirements,
)
from .metadata_utils import plugin_version
from .i18n import text


PLUGIN_VERSION = plugin_version()
SETTINGS_KEY = "TerraWorkbench/dependencyDialogVersion"
QPIP_URL = "https://github.com/opengisch/qpip"

DEPENDENCY_DETAILS = {
    "harmonica": ("BSD-3-Clause", "https://github.com/fatiando/harmonica"),
    "ppigrf": ("MIT", "https://github.com/IAGA-VMOD/ppigrf"),
    "defusedxml": ("PSF", "https://github.com/tiran/defusedxml"),
    "simpeg": ("MIT", "https://github.com/simpeg/simpeg"),
    "discretize": ("MIT", "https://github.com/simpeg/discretize"),
    "choclo": ("BSD-3-Clause", "https://github.com/fatiando/choclo"),
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
    rows = []
    for item in status:
        name = item.requirement.name
        license_name, repository = DEPENDENCY_DETAILS.get(
            name.casefold(), ("See upstream", "")
        )
        if item.satisfied:
            state = (
                '<span style="color:#1b7f3a;font-weight:600">'
                f"{text('Installed', 'Instalado')} {item.installed_version}</span>"
            )
        else:
            state = (
                '<span style="color:#b42318;font-weight:700">'
                f"{item.state}</span>"
            )
        linked_name = (
            f'<a href="{repository}">{name}</a>' if repository else name
        )
        rows.append(
            "<tr>"
            f"<td>{linked_name}<br><code>{item.requirement}</code></td>"
            f"<td>{state}</td><td>{license_name}</td>"
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
        self.install_button.setStyleSheet(
            "font-weight: 600; padding: 6px 12px;"
        )
        self.reinstall_button = QPushButton(self)
        self.folder_button = QPushButton(self)
        self.upstream_button = QPushButton(self)
        for button in (
            self.install_button,
            self.reinstall_button,
            self.folder_button,
            self.upstream_button,
        ):
            buttons.addButton(button, DIALOG_ACTION_ROLE)
        self.install_button.clicked.connect(self.install_missing)
        self.reinstall_button.clicked.connect(self.reinstall_all)
        self.folder_button.clicked.connect(self.open_dependency_folder)
        self.upstream_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(QPIP_URL))
        )
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
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
        self.reinstall_button.setText(text("Reinstall all", "Reinstalar todo"))
        self.folder_button.setText(
            text("Open dependency folder", "Abrir carpeta de dependencias")
        )
        self.upstream_button.setText(text("QPIP upstream", "Proyecto original QPIP"))
        if self.close_button is not None:
            self.close_button.setText(text("Close", "Cerrar"))

    def refresh(self):
        self.status = dependency_status()
        missing = [item for item in self.status if not item.satisfied]
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

    def install_missing(self):
        if install_requirements(self, force_all=False):
            self.refresh()

    def reinstall_all(self):
        if install_requirements(self, force_all=True):
            self.refresh()

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
    if not any(not item.satisfied for item in dependency_status()):
        settings.setValue(SETTINGS_KEY, PLUGIN_VERSION)
