"""TerraWorkbench's embedded, QPIP-derived dependency manager dialog."""

from __future__ import annotations

from html import escape
import importlib.util
import json
import re
import sys

from qgis.PyQt.QtCore import QSettings, Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices, QTextOption
from qgis.PyQt.QtWidgets import (
    QDialog,
    QGridLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QMessageBox,
    QCheckBox,
)

from ..embedded_qpip import (
    dependency_directory,
    dependency_status,
    inversion_supported,
    install_requirements,
)
from ..qgis_plugin.metadata_utils import plugin_version
from ..embedded_qpip.manager import _active_profile_root
from ..embedded_qpip.manager import python_command
from ..embedded_qpip.manager import activate_dependency_path, _log
from ..embedded_qpip.install_progress import PipInstallProgressDialog
from ..embedded_qpip.pip_progress import ProgressUpdate
from ..qgis_plugin.geosoft_runtime import conversion_notice, find_seequent_connector, managed_gx_runtime
from ._paths import PLUGIN_ROOT
from ..qgis_plugin.dependency_cleanup import (
    DependenciesInUseError, cleanup_plan, ensure_dependencies_not_in_use, remove_dependencies,
)
from .i18n import language, text


PLUGIN_VERSION = plugin_version()
SETTINGS_KEY = "TerraWorkbench/dependencyDialogVersion"
QPIP_URL = "https://github.com/opengisch/qpip"


INSTALL_ACTION_STYLE = (
    "QPushButton { font-weight: 600; padding: 6px 12px; }"
    "QPushButton:enabled { border: 2px solid #2e7d32; border-radius: 4px;"
    " background-color: #e8f5e9; color: #1b5e20; }"
    "QPushButton:enabled:hover { background-color: #c8e6c9; }"
)


def gdb_support_state():
    """Inspect both optional components without importing or running GX."""
    if sys.platform != "win32":
        return False, None
    activate_dependency_path()
    package = any(item.requirement.name.casefold() == "geosoft" and item.satisfied
                  for item in dependency_status())
    package = package and importlib.util.find_spec("geosoft") is not None
    return package, managed_gx_runtime(dependency_directory())


def gdb_dotnet_ready():
    from ..qgis_plugin.gx_runtime_setup import dotnet_root

    return dotnet_root(dependency_directory() / "_gx_runtime") is not None


def confirm_gx_conversion(parent=None, *, prepare=False, runtime_missing=True, dotnet_missing=False, package_missing=True):
    """Show the factual Seequent notice until the user chooses not to see it."""
    settings = QSettings()
    key = "TerraWorkbench/gxConversionNoticeHidden"
    hidden = settings.value(key, False, type=bool)
    if hidden and not prepare:
        return True
    dialog = QMessageBox(parent)
    dialog.setWindowTitle("TerraWorkbench — GX Developer")
    notice = conversion_notice(language(), connector_missing=find_seequent_connector() is None)
    if prepare:
        from ..qgis_plugin.gx_runtime_setup import (
            DOTNET_BYTES, GX_REDIST_BYTES, GX_REDIST_URL, GX_LICENSE_TERMS, GX_THIRD_PARTY_TERMS,
        )
        components = []
        if runtime_missing:
            components.append(f"GX 2024.2 · {round(GX_REDIST_BYTES / 2**20)} MiB")
        if dotnet_missing:
            components.append(f".NET 6 portable · {round(DOTNET_BYTES / 2**20)} MiB")
        if package_missing:
            components.append("geosoft (Python)")
        dialog.setText(text("Prepare GDB conversion?", "¿Preparar la conversión GDB?")
                       + "<br>" + "<br>".join(components))
        information = notice + "\n\n" + text(
            "Install in your QGIS profile. GX uses BSD-2-Clause and vendor terms.",
            "Instala el soporte en tu perfil de QGIS. GX usa BSD-2-Clause y los términos del proveedor.",
        )
        links = " · ".join(f'<a href="{escape(url)}">{label}</a>' for url, label in (
            (GX_REDIST_URL, "GX 2024.2"),
            (GX_LICENSE_TERMS, text("Vendor terms", "Términos del proveedor")),
            (GX_THIRD_PARTY_TERMS, text("Third-party licences", "Licencias de terceros")),
        ))
        dialog.setTextFormat(Qt.TextFormat.RichText)
        dialog.setInformativeText(escape(information).replace("\n", "<br>") + "<br>" + links)
    else:
        dialog.setText(notice)
    check = QCheckBox(text("Do not show again", "No volver a mostrar"), dialog)
    check.setChecked(hidden)
    dialog.setCheckBox(check)
    affirmative = QMessageBox.StandardButton.Yes if prepare else QMessageBox.StandardButton.Ok
    negative = QMessageBox.StandardButton.No if prepare else QMessageBox.StandardButton.Cancel
    dialog.setStandardButtons(affirmative | negative)
    dialog.setDefaultButton(negative)
    if prepare:
        dialog.button(affirmative).setText(text("Download", "Descargar") if runtime_missing or dotnet_missing else text("Install", "Instalar"))
        dialog.button(negative).setText(text("Cancel", "Cancelar"))
    execute = getattr(dialog, "exec", None) or dialog.exec_
    if execute() != affirmative:
        return False
    settings.setValue(key, check.isChecked())
    return True


class GDBRuntimeProgressDialog(PipInstallProgressDialog):
    """Display the byte counts emitted by the verified GX downloader."""

    def _consume_line(self, line):
        super()._consume_line(line)
        match = re.fullmatch(r"(?:GX|\.NET) runtime: (\d+)/(\d+) bytes", line.strip())
        if match:
            self._apply_update(ProgressUpdate(
                next(iter(self.rows)), "Downloading",
                int(match[1]), int(match[2]),
            ))


def show_gx_error(parent, details, *, allow_repair=True):
    dialog = QMessageBox(parent)
    dialog.setWindowTitle("TerraWorkbench")
    dialog.setIcon(QMessageBox.Icon.Warning)
    dialog.setText(text("GX could not start. Prepare GDB support again.",
                        "No se pudo iniciar GX. Vuelve a preparar el soporte GDB."))
    close = dialog.addButton(text("Close", "Cerrar"), QMessageBox.ButtonRole.RejectRole)
    repair = (dialog.addButton(text("Repair", "Reparar"), QMessageBox.ButtonRole.ActionRole)
              if allow_repair else None)
    if details:
        detail_button = dialog.addButton(text("Show details", "Mostrar detalles"),
                                         QMessageBox.ButtonRole.ActionRole)
    else:
        detail_button = None
    dialog.setDefaultButton(close)
    dialog.exec()
    if detail_button is not None and dialog.clickedButton() is detail_button:
        detail_dialog = QDialog(parent)
        detail_dialog.setWindowTitle(text("Technical details", "Detalles técnicos"))
        detail_dialog.resize(640, 320)
        layout = QVBoxLayout(detail_dialog)
        diagnostic = QPlainTextEdit(details, detail_dialog)
        diagnostic.setReadOnly(True)
        layout.addWidget(diagnostic)
        done = QPushButton(text("Close", "Cerrar"), detail_dialog)
        done.clicked.connect(detail_dialog.accept)
        layout.addWidget(done)
        detail_dialog.exec()
    if repair is not None and dialog.clickedButton() is repair:
        prepare_gdb_support(parent, repair=True)


def runtime_error_message(output):
    """Translate structured preflight failures instead of showing a traceback."""
    output = str(output)
    if "GX_DOTNET6:" in output:
        output = 'TW_GX_CHECK:' + json.dumps({
            "missing_frameworks": [{"major": "6"}],
            "error": "Microsoft.NETCore.App / Microsoft.WindowsDesktop.App 6",
        })
    for line in reversed(output.splitlines()):
        if line.startswith("TW_GX_CHECK:"):
            try:
                report = json.loads(line[len("TW_GX_CHECK:"):])
            except ValueError:
                break
            if report.get("error_code") == "invalid_redist_configuration":
                return text(
                    "GX configuration is not ready. geosoft.redist must contain two existing, writable user and temporary folders. Details: {error}",
                    "La configuración GX no está lista. geosoft.redist debe indicar dos carpetas existentes y con permiso de escritura: usuario y temporal. Detalle: {error}",
                ).format(error=report.get("error", ""))
            message = text(
                "GX could not load {dll}. Missing DLLs: {missing}. Details: {error}",
                "GX no pudo cargar {dll}. DLL ausentes: {missing}. Detalle: {error}",
            ).format(dll=report.get("dll", "geodist.dll"),
                     missing=", ".join(report.get("missing_dlls", [])) or text("not identified", "no identificadas"),
                     error=report.get("error", ""))
            if any(item.get("major") == "6" for item in report.get("missing_frameworks", [])):
                from ..qgis_plugin.gx_runtime_check import DOTNET6_URL

                message += "\n\n" + text(
                    "The declared .NET 6 framework is missing. Install Microsoft .NET 6 Runtime; Desktop Runtime x64 includes the required desktop and core frameworks. Official download: {url}",
                    "Falta el framework .NET 6 declarado. Instale Microsoft .NET 6 Runtime; Desktop Runtime x64 incluye los frameworks de escritorio y núcleo requeridos. Descarga oficial: {url}",
                ).format(url=DOTNET6_URL)
            return message
    if "GX_REDIST_CONFIG:" in output:
        return text(
            "GX configuration is not ready. geosoft.redist must contain two existing, writable user and temporary folders. Details: {error}",
            "La configuración GX no está lista. geosoft.redist debe indicar dos carpetas existentes y con permiso de escritura: usuario y temporal. Detalle: {error}",
        ).format(error=output.split("GX_REDIST_CONFIG:", 1)[1].splitlines()[0])
    return output[-4000:]


def offer_previous_runtime_cleanup(parent, target):
    from ..qgis_plugin.gx_runtime_setup import previous_runtime_folders, remove_previous_runtime

    try:
        folders = previous_runtime_folders(target)
    except (OSError, ValueError, KeyError):
        return
    for folder in folders:
        answer = QMessageBox.question(parent, "TerraWorkbench", text(
            "The new GX runtime is ready. Remove this previous managed installation? Keeping it is safe.\n{folder}",
            "El nuevo runtime GX está listo. ¿Borrar esta instalación gestionada anterior? Puede conservarla.\n{folder}",
        ).format(folder=folder), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            try:
                remove_previous_runtime(target, folder, confirmed=True)
            except (OSError, ValueError) as error:
                QMessageBox.warning(parent, "TerraWorkbench", str(error))


def prepare_gdb_support(parent=None, *, repair=False):
    """Prepare only optional GDB components with one consent and bounded progress."""
    if sys.platform != "win32":
        return False
    if not check_gdb_connector(parent):
        return False
    package, runtime = gdb_support_state()
    runtime_missing = runtime is None
    dotnet_missing = not gdb_dotnet_ready()
    if package and runtime and not dotnet_missing and not repair:
        return True
    if (not package or runtime is None or dotnet_missing) and not confirm_gx_conversion(
            parent, prepare=True, runtime_missing=runtime is None,
                                 dotnet_missing=dotnet_missing, package_missing=not package):
        return False
    target = dependency_directory()

    def execute(command, requirements, description, progress_type=PipInstallProgressDialog):
        progress = progress_type(command, requirements, description,
                                 log_callback=_log, parent=parent)
        code, cancelled, output = progress.execute()
        if cancelled:
            return False
        if code != 0:
            show_gx_error(parent, runtime_error_message(output), allow_repair=False)
            return False
        return True

    if not package:
        target.mkdir(parents=True, exist_ok=True)
        requirement = "geosoft>=2024.2,<2025"
        command = [python_command(), "-um", "pip", "install", requirement,
                   "--target", str(target), "--upgrade", "--upgrade-strategy", "only-if-needed",
                   "--disable-pip-version-check", "--progress-bar", "raw"]
        if not execute(command, [requirement], text(
            "Installing GDB conversion support", "Instalando soporte de conversión GDB"
        )):
            return False
        activate_dependency_path()
    if runtime is None or dotnet_missing or repair:
        command = [python_command(), "-u", str(PLUGIN_ROOT / "qgis_plugin/gx_runtime_setup.py"),
                   "--target", str(target / "_gx_runtime"), "--accept-terms"]
        if dotnet_missing:
            command.append("--prepare-dotnet")
        component = ".NET 6 portable" if runtime else "Geosoft GX 2024.2 full runtime"
        if not execute(command, [component], text(
            "Preparing GDB conversion support", "Preparando soporte de conversión GDB"
        ), GDBRuntimeProgressDialog):
            return False
    package, runtime = gdb_support_state()
    if not package or runtime is None or not gdb_dotnet_ready():
        QMessageBox.warning(parent, "TerraWorkbench", text(
            "GDB support is not ready. Preparation did not install both required components.",
            "El soporte GDB no está listo. La preparación no instaló los dos componentes necesarios.",
        ))
        return False
    if runtime_missing:
        offer_previous_runtime_cleanup(parent, target / "_gx_runtime")
    return True


def check_gdb_connector(parent=None):
    """Never download native support when its external identity service is absent."""
    if find_seequent_connector() is not None:
        return True
    from ..qgis_plugin.geosoft_runtime import gdb_prerequisite_notice

    QMessageBox.information(parent, "TerraWorkbench", gdb_prerequisite_notice(language()))
    return False


def _gdb_status_html(package, runtime):
    from ..qgis_plugin.gx_runtime_setup import GX_LICENSE_TERMS

    def state(installed):
        if sys.platform != "win32":
            return escape(text("Not available on this system", "No disponible en este sistema"))
        label = text("Installed", "Instalado") if installed else text(
            "Not installed (optional)", "No instalado (opcional)"
        )
        color = "#1b7f3a" if installed else "#9a6700"
        return f'<span style="color:{color};font-weight:600">{escape(label)}</span>'

    title = text("GDB support (optional, Windows only)", "Soporte GDB (opcional, solo Windows)")
    runtime_name = text("Managed GX 2024.2 runtime", "Runtime GX 2024.2 gestionado")
    terms = text("Vendor terms", "Términos del proveedor")
    return (
        f'<tr><td>{escape(title)}<br>geosoft<br>{escape(runtime_name)}</td>'
        f'<td><br>geosoft: {state(package)}<br>{escape(runtime_name)}: {state(runtime is not None)}</td>'
        f'<td>BSD-2-Clause<br><a href="{GX_LICENSE_TERMS}">{escape(terms)}</a></td></tr>'
    )

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

    def __init__(self, parent=None, *, gdb_context=False):
        super().__init__(parent)
        self.gdb_context = gdb_context
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

        self.location_label = QLabel(self)
        layout.addWidget(self.location_label)
        self.location = QPlainTextEdit(self)
        self.location.setReadOnly(True)
        self.location.setWordWrapMode(_qt_enum(QTextOption, "WrapMode", "WrapAnywhere", "WrapAnywhere"))
        self.location.setFixedHeight(2 * self.location.fontMetrics().lineSpacing() + 12)
        layout.addWidget(self.location)

        buttons = QGridLayout()
        self.install_button = QPushButton(self)
        self.install_button.setDefault(True)
        self.install_button.setAutoDefault(True)
        # Green outline marks the one action that installs what is missing.
        self.install_button.setStyleSheet(INSTALL_ACTION_STYLE)
        self.reinstall_button = QPushButton(self)
        self.inversion_button = QPushButton(self)
        self.folder_button = QPushButton(self)
        self.upstream_button = QPushButton(self)
        self.close_button = QPushButton(self)
        for index, button in enumerate((
            self.install_button,
            self.reinstall_button,
            self.inversion_button,
            self.folder_button,
            self.upstream_button,
            self.close_button,
        )):
            buttons.addWidget(button, index // 3, index % 3)
        for column in range(3):
            buttons.setColumnStretch(column, 1)
        self.install_button.clicked.connect(self.install_missing)
        self.reinstall_button.clicked.connect(self.reinstall_all)
        self.inversion_button.clicked.connect(self.install_inversion)
        self.folder_button.clicked.connect(self.open_dependency_folder)
        self.upstream_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(QPIP_URL))
        )
        self.close_button.clicked.connect(self.reject)
        layout.addLayout(buttons)
        self.gdb_button = QPushButton(self)
        self.gdb_button.setStyleSheet(INSTALL_ACTION_STYLE)
        self.gdb_button.setAutoDefault(False)
        self.gdb_button.clicked.connect(self.install_gdb_support)
        layout.addWidget(self.gdb_button)
        self.gdb_note = QLabel(self)
        self.gdb_note.setWordWrap(True)
        layout.addWidget(self.gdb_note)
        self.cleanup_button = QPushButton(self)
        self.cleanup_button.setAutoDefault(False)
        self.cleanup_button.clicked.connect(self.cleanup)
        layout.addWidget(self.cleanup_button)
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
        self.gdb_button.setText(text("Prepare GDB conversion support", "Preparar conversión de GDB"))
        self._refresh_gdb_support()
        self.reinstall_button.setText(text("Reinstall core", "Reinstalar núcleo"))
        self.inversion_button.setText(
            text("Install optional 3D inversion", "Instalar inversión 3D opcional")
        )
        self.folder_button.setText(
            text("Open dependency folder", "Abrir carpeta de dependencias")
        )
        self.upstream_button.setText(text("QPIP upstream", "Proyecto original QPIP"))
        self.cleanup_button.setText(text("Remove dependencies and preferences", "Eliminar dependencias y preferencias"))
        self.close_button.setText(text("Close", "Cerrar"))
        self.location_label.setText(text("Install location", "Ubicación de instalación"))
        for button in (
            self.install_button, self.reinstall_button, self.inversion_button,
            self.folder_button, self.upstream_button, self.cleanup_button, self.close_button,
        ):
            text_width = button.fontMetrics().horizontalAdvance(button.text())
            button.setMinimumWidth(max(button.sizeHint().width(), text_width + 24))

    def showEvent(self, event):
        super().showEvent(event)
        if self.gdb_context and self.gdb_button.isEnabled():
            self.install_button.setDefault(False)
            self.gdb_button.setDefault(True)
            self.gdb_button.setFocus()

    def _refresh_gdb_support(self):
        package, runtime = gdb_support_state()
        available = sys.platform == "win32"
        ready = available and package and runtime is not None and gdb_dotnet_ready()
        self.gdb_button.setEnabled(available and not ready and not self.cleanup_completed)
        self.gdb_note.setText(text(
            "To import GDB, prepare conversion support.",
            "Para importar GDB, prepara el soporte de conversión.",
        ) if available and not ready else text(
            "GDB conversion support is installed.", "El soporte de conversión GDB está instalado."
        ) if available else text(
            "Not available on this system", "No disponible en este sistema"
        ))
        return package, runtime

    def refresh(self):
        core_status = dependency_status()
        self.status = dependency_status(include_inversion=inversion_supported())
        missing = [item for item in core_status
                   if item.requirement.name.casefold() != "geosoft" and not item.satisfied]
        core_names = {item.requirement.name.casefold() for item in core_status}
        inversion_missing = [
            item
            for item in self.status
            if item.requirement.name.casefold() not in core_names and not item.satisfied
        ]
        package, runtime = self._refresh_gdb_support()
        self.browser.setHtml(
            f"<p>{text('TerraWorkbench installs these packages in your QGIS profile.', 'TerraWorkbench instala estos paquetes en tu perfil de QGIS.')}</p>"
            "<table cellspacing='0' cellpadding='7' width='100%' "
            "style='border-collapse:collapse'>"
            "<tr style='background:#e9eef4;font-weight:600'>"
            f"<td>{text('Package and requirement', 'Paquete y requisito')}</td><td>{text('Status', 'Estado')}</td><td>{text('License', 'Licencia')}</td></tr>"
            f"{_status_html([item for item in self.status if item.requirement.name.casefold() != 'geosoft'])}"
            f"{_gdb_status_html(package, runtime)}</table>"
        )
        location = str(dependency_directory())
        self.location.setPlainText(location)
        self.location.setToolTip(location)
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
                "All core scientific requirements are satisfied. Restart QGIS after any repair.",
                "Todos los requisitos científicos del núcleo están satisfechos. Reinicie QGIS después de cualquier reparación.",
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
        """Install what is missing and close once every core requirement is met."""
        if install_requirements(self, force_all=False):
            self.refresh()
            if all(item.satisfied for item in dependency_status()
                   if item.requirement.name.casefold() != "geosoft"):
                self.accept()

    def install_gdb_support(self):
        """Share the same optional preparation flow as GDB import."""
        prepared = prepare_gdb_support(self)
        self.retranslate()
        self.refresh()
        return prepared

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


def open_dependency_dialog(parent=None, *, gdb_context=False):
    """Open the dependency manager on demand from the TerraWorkbench menu."""
    dialog = DependencyDialog(parent, gdb_context=gdb_context)
    dialog.exec()
    return dialog


def show_dependency_dialog(parent=None):
    """Show at startup only while core requirements are missing or conflicting."""
    status = dependency_status()
    missing = any(not item.satisfied for item in status
                  if item.requirement.name.casefold() != "geosoft")
    settings = QSettings()
    if not missing:
        settings.setValue(SETTINGS_KEY, PLUGIN_VERSION)
        return

    dialog = DependencyDialog(parent)
    dialog.exec()
    if not dialog.cleanup_completed and not any(not item.satisfied for item in dependency_status()
                                              if item.requirement.name.casefold() != "geosoft"):
        settings.setValue(SETTINGS_KEY, PLUGIN_VERSION)
