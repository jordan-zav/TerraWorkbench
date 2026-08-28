"""QGIS plugin lifecycle."""

from qgis.core import QgsApplication

from .dependency_dialog import show_dependency_dialog
from .provider import TerraWorkbenchProvider


class TerraWorkbenchPlugin:
    """Register the TerraWorkbench Processing provider."""

    def __init__(self, iface):
        self.iface = iface
        self.provider = None

    def initProcessing(self):
        if self.provider is None:
            self.provider = TerraWorkbenchProvider()
            QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()
        show_dependency_dialog(self.iface.mainWindow())

    def unload(self):
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
