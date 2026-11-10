"""TerraWorkbench QGIS plugin."""

# Test collectors may inspect this file as a standalone module when an export
# folder contains punctuation. QGIS always loads it as a real package.
if __package__:
    from .compat.redirects import install_legacy_imports

    install_legacy_imports(__name__)


def classFactory(iface):
    """Create the QGIS plugin instance."""
    from .qgis_plugin.plugin import TerraWorkbenchPlugin

    return TerraWorkbenchPlugin(iface)
