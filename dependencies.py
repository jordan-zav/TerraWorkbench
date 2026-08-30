"""Lazy imports and user-facing dependency diagnostics."""

import site
from pathlib import Path
import sys

from qgis.core import QgsProcessingException

from .embedded_qpip import activate_dependency_path


LOCAL_VENDOR_DIRECTORY = Path(__file__).with_name("_vendor")
if LOCAL_VENDOR_DIRECTORY.is_dir():
    site.addsitedir(str(LOCAL_VENDOR_DIRECTORY))

activate_dependency_path()


def import_harmonica():
    """Import Harmonica only when an algorithm is executed."""
    try:
        import harmonica
    except ImportError as exc:
        raise QgsProcessingException(
            "Harmonica is not installed in the Python environment used by QGIS. "
            "Open TerraWorkbench's dependency manager, install the packages listed "
            "in requirements.txt, then restart QGIS."
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
            "ppigrf is required for automatic IGRF-14 parameters. Use the built-in "
            "TerraWorkbench dependency manager, then restart QGIS."
        ) from exc
    return ppigrf


def import_simpeg_stack():
    """Import the optional 3D inversion stack without burdening 2D users."""
    if sys.version_info < (3, 11):
        raise QgsProcessingException(
            "The pinned SimPEG inversion stack requires Python 3.11 or newer. "
            "Use a QGIS build with a compatible Python runtime; the 2D "
            "TerraWorkbench tools remain available in this installation."
        )
    try:
        import discretize
        import simpeg
    except ImportError as exc:
        raise QgsProcessingException(
            "The optional SimPEG inversion stack is not installed in the Python "
            "environment used by QGIS. Use TerraWorkbench's built-in dependency "
            "manager to install requirements-inversion.txt, restart QGIS, and run the inversion again. The 2D tools do not "
            "require this dependency set."
        ) from exc
    return simpeg, discretize
