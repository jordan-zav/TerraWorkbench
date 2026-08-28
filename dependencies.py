"""Lazy imports and user-facing dependency diagnostics."""

from qgis.core import QgsProcessingException


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
