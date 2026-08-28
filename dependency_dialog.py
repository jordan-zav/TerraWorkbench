"""Dependency status dialog shown when the plugin is activated."""

from dataclasses import dataclass
import importlib.util

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

from .metadata_utils import plugin_version


PLUGIN_VERSION = plugin_version()
SETTINGS_KEY = "TerraWorkbench/dependencyDialogVersion"
QPIP_URL = "https://github.com/opengisch/qpip"


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


@dataclass(frozen=True)
class Dependency:
    """One runtime dependency displayed to the user."""

    name: str
    import_name: str
    license_name: str
    repository: str
    optional: bool = False


DEPENDENCIES = (
    Dependency(
        "Harmonica",
        "harmonica",
        "BSD-3-Clause",
        "https://github.com/fatiando/harmonica",
    ),
    Dependency(
        "Verde",
        "verde",
        "BSD-3-Clause",
        "https://github.com/fatiando/verde",
    ),
    Dependency(
        "Choclo",
        "choclo",
        "BSD-3-Clause",
        "https://github.com/fatiando/choclo",
    ),
    Dependency(
        "Xarray",
        "xarray",
        "Apache-2.0",
        "https://github.com/pydata/xarray",
    ),
    Dependency(
        "xrft",
        "xrft",
        "MIT",
        "https://github.com/xgcm/xrft",
    ),
    Dependency(
        "Numba",
        "numba",
        "BSD",
        "https://github.com/numba/numba",
    ),
    Dependency(
        "Scikit-learn",
        "sklearn",
        "BSD-3-Clause",
        "https://github.com/scikit-learn/scikit-learn",
    ),
    Dependency(
        "Pooch",
        "pooch",
        "BSD-3-Clause",
        "https://github.com/fatiando/pooch",
    ),
    Dependency(
        "Dask",
        "dask",
        "BSD-3-Clause",
        "https://github.com/dask/dask",
    ),
    Dependency(
        "SimPEG (3D inversion)",
        "simpeg",
        "MIT",
        "https://github.com/simpeg/simpeg",
    ),
    Dependency(
        "discretize (3D meshes)",
        "discretize",
        "MIT",
        "https://github.com/simpeg/discretize",
    ),
)


def dependency_status():
    """Return dependency records paired with their import availability."""
    return tuple(
        (dependency, importlib.util.find_spec(dependency.import_name) is not None)
        for dependency in DEPENDENCIES
    )


def _status_html(status):
    rows = []
    for dependency, installed in status:
        state = (
            '<span style="color:#1b7f3a;font-weight:600">Installed</span>'
            if installed
            else '<span style="color:#b42318;font-weight:700">Missing</span>'
        )
        rows.append(
            "<tr>"
            f'<td><a href="{dependency.repository}">{dependency.name}</a>'
            f"{' — optional' if dependency.optional else ''}</td>"
            f"<td>{state}</td>"
            f"<td>{dependency.license_name}</td>"
            "</tr>"
        )
    return "".join(rows)


class DependencyDialog(QDialog):
    """Explain requirements, status, licenses and installation behavior."""

    def __init__(self, status, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TerraWorkbench — Scientific dependencies")
        self.setMinimumSize(680, 510)

        layout = QVBoxLayout(self)
        heading = QLabel(
            "TerraWorkbench combines independent open-source scientific libraries."
        )
        heading.setStyleSheet("font-size: 15px; font-weight: 600; margin: 4px;")
        layout.addWidget(heading)

        browser = QTextBrowser(self)
        browser.setOpenExternalLinks(True)
        browser.setHtml(
            "<p>The packages below are required by the current gravity and magnetic "
            "module. QPIP checks the active QGIS profile and offers to install missing "
            "packages. Installation starts only after user approval and is stored in "
            "the user profile, not in the QGIS program directory. SimPEG and "
            "discretize are optional and only needed by the 3D inversion tools; "
            "their pinned subset is also documented in requirements-inversion.txt.</p>"
            "<table cellspacing='0' cellpadding='7' width='100%' "
            "style='border-collapse:collapse'>"
            "<tr style='background:#e9eef4;font-weight:600'>"
            "<td>Project and repository</td><td>Status</td><td>License</td></tr>"
            f"{_status_html(status)}"
            "</table>"
            "<p>TerraWorkbench is GPLv3. The listed permissive licenses are compatible with "
            "GPLv3. Each project remains independent and retains its own copyright, "
            "license and repository.</p>"
        )
        layout.addWidget(browser)

        note = QLabel(
            "If packages are missing, close this window and approve the QPIP "
            "installation prompt. Restart QGIS after installation."
        )
        note.setWordWrap(True)
        note.setTextInteractionFlags(TEXT_SELECTABLE_BY_MOUSE)
        layout.addWidget(note)

        buttons = QDialogButtonBox(DIALOG_CLOSE, parent=self)
        qpip_button = QPushButton("Open QPIP repository", self)
        buttons.addButton(qpip_button, DIALOG_ACTION_ROLE)
        qpip_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(QPIP_URL)))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


def show_dependency_dialog(parent=None):
    """Show once per version, or on every activation while anything is missing."""
    status = dependency_status()
    missing = any(
        not installed and not dependency.optional for dependency, installed in status
    )
    settings = QSettings()
    already_seen = settings.value(SETTINGS_KEY, "", type=str) == PLUGIN_VERSION
    if already_seen and not missing:
        return

    dialog = DependencyDialog(status, parent)
    dialog.exec()
    if not missing:
        settings.setValue(SETTINGS_KEY, PLUGIN_VERSION)
