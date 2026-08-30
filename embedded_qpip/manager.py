"""TerraWorkbench-scoped dependency management using embedded QPIP UI pieces."""

from __future__ import annotations

from dataclasses import dataclass
import configparser
import importlib
from importlib import metadata
import os
from pathlib import Path
import platform
import site
import sys

from packaging.markers import default_environment
from packaging.requirements import Requirement
from qgis.core import Qgis, QgsApplication, QgsMessageLog

from ..i18n import text
from qgis.PyQt.QtWidgets import QMessageBox

from .install_progress import PipInstallProgressDialog


LOG_TAG = "TerraWorkbench dependencies"
INVERSION_MINIMUM_PYTHON = (3, 11)


@dataclass(frozen=True)
class RequirementStatus:
    """Installed state of one direct TerraWorkbench requirement."""

    requirement: Requirement
    installed_version: str | None
    satisfied: bool

    @property
    def state(self):
        if self.installed_version is None:
            return "Missing"
        if self.satisfied:
            return "Installed"
        return f"Version conflict ({self.installed_version})"


def requirements_path():
    """Return the canonical requirements file shipped with TerraWorkbench."""
    return Path(__file__).resolve().parents[1] / "requirements.txt"


def inversion_requirements_path():
    """Return the optional 3D-inversion requirements shipped with the plugin."""
    return Path(__file__).resolve().parents[1] / "requirements-inversion.txt"


def inversion_supported():
    """Whether this QGIS Python can install the pinned SimPEG stack."""
    return sys.version_info >= INVERSION_MINIMUM_PYTHON


def dependency_directory():
    """Return TerraWorkbench's isolated, version-specific dependency directory."""
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    return (
        _active_profile_root()
        / "python"
        / "dependencies"
        / "TerraWorkbench"
        / python_version
    )


def _active_profile_root():
    """Resolve one active profile without leaking packages across profiles."""
    settings_path = Path(QgsApplication.qgisSettingsDirPath()).resolve()
    appdata = os.environ.get("APPDATA")
    standard_root = (
        Path(appdata) / "QGIS" / "QGIS3" / "profiles" if appdata else None
    )
    if (
        settings_path.parent.name.casefold() == "profiles"
        and (
            standard_root is None
            or settings_path.parent == standard_root.resolve()
        )
    ):
        return settings_path

    if standard_root and standard_root.is_dir():
        profiles_ini = standard_root.parent / "profiles.ini"
        if profiles_ini.is_file():
            parser = configparser.ConfigParser()
            parser.read(profiles_ini, encoding="utf-8")
            profile_name = parser.get(
                "core", "lastProfile", fallback=""
            ).strip()
            if profile_name and (standard_root / profile_name).is_dir():
                return standard_root / profile_name
        default_profile = standard_root / "default"
        if default_profile.is_dir():
            return default_profile
        profiles = sorted(path for path in standard_root.iterdir() if path.is_dir())
        if len(profiles) == 1:
            return profiles[0]

    return settings_path


def activate_dependency_path():
    """Expose TerraWorkbench-managed packages to the current QGIS process."""
    target = dependency_directory()
    if target.is_dir():
        site.addsitedir(str(target))
        if str(target) not in sys.path:
            sys.path.insert(0, str(target))
        bin_path = target / "bin"
        path_entries = os.environ.get("PATH", "").split(os.pathsep)
        if str(bin_path) not in path_entries:
            os.environ["PATH"] = str(bin_path) + os.pathsep + os.environ.get(
                "PATH", ""
            )
        importlib.invalidate_caches()
    return target


def read_requirements():
    """Parse compatible direct requirements, honoring environment markers."""
    environment = default_environment()
    requirements = []
    paths = [requirements_path()]
    if inversion_supported():
        paths.append(inversion_requirements_path())
    for path in paths:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith(("#", "-")):
                continue
            requirement = Requirement(line)
            if requirement.marker and not requirement.marker.evaluate(environment):
                continue
            requirements.append(requirement)
    return tuple(requirements)


def dependency_status():
    """Return version-aware status for direct TerraWorkbench requirements."""
    activate_dependency_path()
    status = []
    for requirement in read_requirements():
        try:
            distribution = metadata.distribution(requirement.name)
            version = distribution.version
            satisfied = (
                not requirement.specifier
                or requirement.specifier.contains(version, prereleases=True)
            )
        except metadata.PackageNotFoundError:
            version = None
            satisfied = False
        status.append(RequirementStatus(requirement, version, satisfied))
    return tuple(status)


def python_command():
    """Match QPIP's safe Python executable discovery on QGIS installations."""
    if (Path(sys.prefix) / "conda-meta").exists():
        return "python"
    base_paths = [Path(sys.prefix), Path(sys.executable).parent]
    names = (
        ("python.exe", "python3.exe")
        if platform.system() == "Windows"
        else ("python", "python3")
    )
    for base_path in base_paths:
        for name in names:
            candidate = base_path / name
            if candidate.is_file():
                return str(candidate)
    return sys.executable


# Kept for compatibility with the existing focused smoke test.
_python_command = python_command


def _log(message):
    QgsMessageLog.logMessage(str(message), LOG_TAG, level=Qgis.MessageLevel.Info)


def install_requirements(parent=None, force_all=False):
    """Install missing/conflicting or all direct requirements after user approval."""
    status = dependency_status()
    selected = [
        str(item.requirement)
        for item in status
        if force_all or not item.satisfied
    ]
    if not selected:
        QMessageBox.information(
            parent,
            text("TerraWorkbench dependencies", "Dependencias de TerraWorkbench"),
            text("All compatible TerraWorkbench dependency files are satisfied.", "Todos los archivos de dependencias compatibles de TerraWorkbench están satisfechos."),
        )
        return True

    answer = QMessageBox.question(
        parent,
        text("Install TerraWorkbench dependencies?", "¿Instalar las dependencias de TerraWorkbench?"),
        text("TerraWorkbench will install the selected open-source Python packages inside the active QGIS user profile. QGIS program files and other plugins will not be modified. Continue?", "TerraWorkbench instalará los paquetes Python de código abierto seleccionados dentro del perfil activo de QGIS. No se modificarán los archivos del programa QGIS ni otros complementos. ¿Continuar?"),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer != QMessageBox.StandardButton.Yes:
        return False

    target = dependency_directory()
    target.mkdir(parents=True, exist_ok=True)
    command = [
        python_command(),
        "-um",
        "pip",
        "install",
        *selected,
        "--target",
        str(target),
        "--upgrade",
        "--disable-pip-version-check",
        "--progress-bar",
        "raw",
    ]
    dialog = PipInstallProgressDialog(
        command,
        selected,
        text("Installing TerraWorkbench scientific dependencies", "Instalando dependencias científicas de TerraWorkbench"),
        log_callback=_log,
        parent=parent,
    )
    return_code, cancelled, output = dialog.execute()
    if return_code == 0:
        activate_dependency_path()
        QMessageBox.information(
            parent,
            text("TerraWorkbench dependencies installed", "Dependencias de TerraWorkbench instaladas"),
            text("Installation completed. Restart QGIS before running scientific algorithms so every compiled package is loaded from the new profile.", "Instalación completada. Reinicie QGIS antes de ejecutar algoritmos científicos para que cada paquete compilado se cargue desde el nuevo perfil."),
        )
        return True
    if not cancelled:
        message = QMessageBox(
            QMessageBox.Icon.Warning,
            text("Dependency installation failed", "Falló la instalación de dependencias"),
            text("TerraWorkbench could not install all selected dependencies.", "TerraWorkbench no pudo instalar todas las dependencias seleccionadas."),
            parent=parent,
        )
        message.setDetailedText(output)
        message.exec()
    return False
