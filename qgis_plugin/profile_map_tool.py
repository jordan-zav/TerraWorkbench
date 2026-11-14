"""Identify survey features for the line-profile editor."""

from qgis.PyQt.QtCore import Qt
from qgis.core import QgsProject, QgsVectorLayer
from qgis.gui import QgsMapToolIdentify

from .qgis_compat import qt_enum
from .survey_map_layers import survey_layer_database


class ProfileMapTool(QgsMapToolIdentify):
    """Open the line under a click in an identified survey layer."""

    def __init__(self, canvas, open_profile):
        super().__init__(canvas)
        self.open_profile = open_profile

    @staticmethod
    def context(layer):
        """Return the database context for a survey vector layer."""
        if isinstance(layer, QgsVectorLayer):
            return survey_layer_database(QgsProject.instance(), layer)
        return None

    def canvasReleaseEvent(self, event):
        if event.button() != qt_enum(Qt, "MouseButton", "LeftButton"):
            return
        layers = [layer for layer in self.canvas().layers() if self.context(layer)]
        if not layers:
            return
        mode = qt_enum(QgsMapToolIdentify, "IdentifyMode", "TopDownAll")
        for hit in self.identify(event.x(), event.y(), layers, mode):
            if self.open_profile(
                hit.mLayer,
                hit.mFeature,
                event.mapPoint(),
                self.canvas().mapSettings().destinationCrs(),
            ):
                break
