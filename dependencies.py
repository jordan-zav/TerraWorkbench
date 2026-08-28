"""Lazy imports and user-facing dependency diagnostics."""

import site
import os
from pathlib import Path
import sys

from qgis.core import QgsApplication, QgsProcessingException


LOCAL_VENDOR_DIRECTORY = Path(__file__).with_name("_vendor")
if LOCAL_VENDOR_DIRECTORY.is_dir():
    site.addsitedir(str(LOCAL_VENDOR_DIRECTORY))

PYTHON_VERSION_DIRECTORY = f"{sys.version_info.major}.{sys.version_info.minor}"
QPIP_DEPENDENCY_DIRECTORIES = [
    Path(__file__).resolve().parents[2] / "dependencies" / PYTHON_VERSION_DIRECTORY,
]
appdata = os.environ.get("APPDATA")
if appdata:
    profiles_root = Path(appdata) / "QGIS" / "QGIS3" / "profiles"
    if profiles_root.is_dir():
        QPIP_DEPENDENCY_DIRECTORIES.extend(
            profile / "python" / "dependencies" / PYTHON_VERSION_DIRECTORY
            for profile in profiles_root.iterdir()
            if profile.is_dir()
        )
settings_directory = QgsApplication.qgisSettingsDirPath()
if settings_directory:
    QPIP_DEPENDENCY_DIRECTORIES.append(
        Path(settings_directory) / "python" / "dependencies" / PYTHON_VERSION_DIRECTORY
    )
for dependency_directory in QPIP_DEPENDENCY_DIRECTORIES:
    if dependency_directory.is_dir():
        site.addsitedir(str(dependency_directory))


def import_harmonica():
    """Import Harmonica only when an algorithm is executed."""
    try:
        import harmonica
    except ImportError as exc:
        raise QgsProcessingException(
            "Harmonica is not installed in the Python environment used by QGIS. "
            "Install the QGIS plugin qpip and use it to install the packages listed "
            "in TerraWorkbench requirements.txt, then restart QGIS."
        ) from exc
    return harmonica


def import_xarray():
    """Import xarray with a concise QGIS-facing error."""
    try:
        import xarray
    except ImportError as exc:
        raise QgsProcessingException(
            "xarray is required by TerraWorkbench. Install the dependencies "
            "listed in requirements.txt and restart QGIS."
        ) from exc
    return xarray


def import_ppigrf():
    """Import the IAGA-VMOD pure-Python IGRF implementation."""
    try:
        import ppigrf
    except ImportError as exc:
        raise QgsProcessingException(
            "ppigrf is required for automatic IGRF-14 parameters. Use QPIP to "
            "install the packages listed in requirements.txt, then restart QGIS."
        ) from exc
    return ppigrf


def import_simpeg_stack():
    """Import the optional 3D inversion stack without burdening 2D users."""
    try:
        import discretize
        import simpeg
    except ImportError as exc:
        raise QgsProcessingException(
            "The optional SimPEG inversion stack is not installed in the Python "
            "environment used by QGIS. Use QPIP or pip for the active profile to "
            "install requirements-inversion.txt, restart QGIS, and run the inversion again. The 2D tools do not "
            "require this dependency set."
        ) from exc
    return simpeg, discretize
