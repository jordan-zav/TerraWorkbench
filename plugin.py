"""QGIS plugin lifecycle."""

from pathlib import Path

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsApplication

from .dependency_dialog import open_dependency_dialog, show_dependency_dialog
from .i18n import text
from .provider import TerraWorkbenchProvider
from .qgis_compat import qt_enum
from .workflow_dock import FilterStackDock


BRAND_ICON_PATH = Path(__file__).parent / "assets" / "branding" / "terraworkbench-icon.png"


class TerraWorkbenchPlugin:
    """Register the TerraWorkbench Processing provider."""

    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.filter_stack_dock = None
        self.filter_stack_action = None
        self.knowledge_action = None
        self.dependency_action = None
        self.workspace_action = None
        self.workspace_dialog = None

    def initProcessing(self):
        if self.provider is None:
            self.provider = TerraWorkbenchProvider()
            QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        # First-run dependency setup must be the first visible TerraWorkbench UI.
        # Scientific algorithms import their heavy stacks lazily, so users can
        # approve installation before opening the workbench itself.
        show_dependency_dialog(self.iface.mainWindow())
        self.initProcessing()
        if self.filter_stack_dock is None:
            self.filter_stack_dock = FilterStackDock(self.iface.mainWindow())
            self.filter_stack_dock.languageChanged.connect(self.retranslate)
            self.iface.addDockWidget(
                qt_enum(Qt, "DockWidgetArea", "RightDockWidgetArea"),
                self.filter_stack_dock,
            )
            self.filter_stack_action = self.filter_stack_dock.toggleViewAction()
            self.filter_stack_action.setText("TerraWorkbench Filter Stack")
            self.filter_stack_action.setIcon(
                QIcon(str(BRAND_ICON_PATH))
            )
            self.iface.addPluginToRasterMenu("TerraWorkbench", self.filter_stack_action)
            self.iface.addToolBarIcon(self.filter_stack_action)
            self.knowledge_action = QAction(
                QIcon(str(BRAND_ICON_PATH)),
                "TerraWorkbench Knowledge Base",
                self.iface.mainWindow(),
            )
            self.knowledge_action.triggered.connect(
                self.filter_stack_dock.show_knowledge_base
            )
            self.iface.addPluginToRasterMenu(
                "TerraWorkbench", self.knowledge_action
            )
            self.dependency_action = QAction(
                "TerraWorkbench Dependencies…",
                self.iface.mainWindow(),
            )
            self.dependency_action.triggered.connect(
                lambda: open_dependency_dialog(self.iface.mainWindow())
            )
            self.iface.addPluginToRasterMenu(
                "TerraWorkbench", self.dependency_action
            )
            self.workspace_action = QAction("TerraWorkbench — Survey databases…", self.iface.mainWindow())
            self.workspace_action.triggered.connect(self.show_workspace)
            self.iface.addPluginToRasterMenu("TerraWorkbench", self.workspace_action)
            self.filter_stack_dock.show()
            self.retranslate()

    def retranslate(self):
        if self.workspace_action is not None:
            from .survey_workspace_dialog import tr
            self.workspace_action.setText(tr("TerraWorkbench — Survey databases…", "TerraWorkbench — Bases de levantamientos…", "TerraWorkbench — Bancos de levantamentos…"))
        if self.filter_stack_action is not None:
            self.filter_stack_action.setText(
                text("TerraWorkbench Filter Stack", "Pila de filtros TerraWorkbench")
            )
        if self.knowledge_action is not None:
            self.knowledge_action.setText(
                text(
                    "TerraWorkbench Knowledge Base",
                    "Base de conocimiento TerraWorkbench",
                )
            )
        if self.dependency_action is not None:
            self.dependency_action.setText(
                text(
                    "TerraWorkbench Dependencies…",
                    "Dependencias de TerraWorkbench…",
                )
            )

    def show_workspace(self):
        from .survey_workspace_dialog import SurveyWorkspaceDialog
        if self.workspace_dialog is None:
            self.workspace_dialog = SurveyWorkspaceDialog(self.iface.mainWindow())
        self.workspace_dialog._close_requested = False
        self.workspace_dialog.show()
        self.workspace_dialog.raise_()
        self.workspace_dialog.activateWindow()

    def unload(self):
        if self.workspace_dialog is not None:
            self.workspace_dialog.dispose()
            self.workspace_dialog = None
        if self.workspace_action is not None:
            self.iface.removePluginRasterMenu("TerraWorkbench", self.workspace_action)
            self.workspace_action.deleteLater()
            self.workspace_action = None
        if self.dependency_action is not None:
            self.iface.removePluginRasterMenu(
                "TerraWorkbench", self.dependency_action
            )
            self.dependency_action.deleteLater()
            self.dependency_action = None
        if self.knowledge_action is not None:
            self.iface.removePluginRasterMenu(
                "TerraWorkbench", self.knowledge_action
            )
            self.knowledge_action.deleteLater()
            self.knowledge_action = None
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
