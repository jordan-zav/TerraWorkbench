"""TerraWorkbench QGIS plugin."""


def classFactory(iface):
    """Create the QGIS plugin instance."""
    from .plugin import TerraWorkbenchPlugin

    return TerraWorkbenchPlugin(iface)
