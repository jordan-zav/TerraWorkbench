"""QGIS plugin lifecycle."""

from pathlib import Path

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsApplication

from .dependency_dialog import show_dependency_dialog
from .provider import TerraWorkbenchProvider
from .qgis_compat import qt_enum
from .workflow_dock import FilterStackDock


class TerraWorkbenchPlugin:
    """Register the TerraWorkbench Processing provider."""

    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.filter_stack_dock = None
        self.filter_stack_action = None

    def initProcessing(self):
        if self.provider is None:
            self.provider = TerraWorkbenchProvider()
            QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()
        if self.filter_stack_dock is None:
            self.filter_stack_dock = FilterStackDock(self.iface.mainWindow())
            self.iface.addDockWidget(
                qt_enum(Qt, "DockWidgetArea", "RightDockWidgetArea"),
                self.filter_stack_dock,
            )
            self.filter_stack_action = self.filter_stack_dock.toggleViewAction()
            self.filter_stack_action.setText("TerraWorkbench Filter Stack")
            self.filter_stack_action.setIcon(
                QIcon(str(Path(__file__).with_name("icon.svg")))
            )
            self.iface.addPluginToRasterMenu("TerraWorkbench", self.filter_stack_action)
            self.iface.addToolBarIcon(self.filter_stack_action)
            self.filter_stack_dock.show()
        show_dependency_dialog(self.iface.mainWindow())

    def unload(self):
        if self.filter_stack_action is not None:
            self.iface.removePluginRasterMenu(
                "TerraWorkbench", self.filter_stack_action
            )
            self.iface.removeToolBarIcon(self.filter_stack_action)
            self.filter_stack_action = None
        if self.filter_stack_dock is not None:
            self.filter_stack_dock.disconnect_project()
            self.iface.removeDockWidget(self.filter_stack_dock)
            self.filter_stack_dock.deleteLater()
            self.filter_stack_dock = None
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
