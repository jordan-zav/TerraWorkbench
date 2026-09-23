"""Explicit horizontal coordinate assignment and non-destructive reprojection."""

import json

from qgis.PyQt.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QLabel,
    QLineEdit, QMessageBox, QToolButton, QVBoxLayout,
)
from qgis.core import (
    Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsCoordinateTransformContext, QgsPointXY, QgsProject, QgsUnitTypes,
)
from qgis.gui import QgsProjectionSelectionWidget

from .qgis_compat import qt_enum
from .survey_workspace_dialog import tr


def coordinate_operation(store, database_id, request, context):
    """Build the transform in its worker thread; never access the project there."""
    def run(cancel, progress):
        source = QgsCoordinateReferenceSystem(request["source"])
        target = QgsCoordinateReferenceSystem(request["target"])
        if not source.isValid() or not target.isValid():
            raise ValueError("Invalid source or target CRS.")
        transform = QgsCoordinateTransform(source, target, context)
        transform.setAllowFallbackTransforms(False)
        transform.setBallparkTransformsAreAppropriate(False)
        if not transform.isValid():
            raise ValueError("No valid coordinate transformation is available.")
        details = {"library": "QGIS / PROJ", "qgis_version": Qgis.QGIS_VERSION,
                   "fallback_allowed": False, "axis_order": "X/Y (longitude/latitude for geographic CRS)"}

        def convert(xs, ys):
            out_x, out_y = [], []
            for index, (x, y) in enumerate(zip(xs, ys)):
                if index % 256 == 0 and cancel():
                    raise InterruptedError("Coordinate transformation canceled.")
                if source.isGeographic() and not (-180 <= x <= 180 and -90 <= y <= 90):
                    raise ValueError("Geographic coordinates outside longitude/latitude bounds.")
                point = transform.transform(QgsPointXY(float(x), float(y)))
                out_x.append(point.x())
                out_y.append(point.y())
            operation = transform.instantiatedCoordinateOperationDetails()
            details["proj_operation"] = operation.proj
            details["accuracy"] = operation.accuracy
            return out_x, out_y

        return store.reproject_coordinates(
            database_id, request["x"], request["y"], source.toWkt(), target.toWkt(),
            request["output_x"], request["output_y"], convert,
            QgsUnitTypes.toString(target.mapUnits()), details, cancel, progress)
    return run


class SurveyCoordinatesDialog(QDialog):
    def __init__(self, store, database_id, parent=None):
        super().__init__(parent)
        self.store, self.database_id = store, database_id
        self.request = None
        self.setWindowTitle(tr("Coordinates and CRS", "Coordenadas y CRS", "Coordenadas e SRC"))
        self.resize(700, 540)
        layout = QVBoxLayout(self)
        database = next(row for row in store.databases() if row["id"] == database_id)
        heading = QLabel(database["name"])
        heading.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(heading)
        description = QLabel(tr(
            "Assign a reference system, or create a new coordinate pair. Originals stay unchanged.",
            "Asigna un sistema de referencia o crea otro par de coordenadas. Los originales se conservan.",
            "Atribua um sistema de referência ou crie outro par de coordenadas. Os originais são preservados."))
        description.setWordWrap(True)
        layout.addWidget(description)
        self.mode = QComboBox()
        self.mode.addItems([tr("Assign CRS · keep values", "Asignar CRS · conservar valores", "Atribuir SRC · manter valores"),
                            tr("Reproject · new channels", "Reproyectar · canales nuevos", "Reprojetar · novos canais")])
        layout.addWidget(self.mode)
        source_box = QGroupBox(tr("Input coordinates", "Coordenadas de entrada", "Coordenadas de entrada"))
        form = QFormLayout(source_box)
        rows = store.channels(database_id)
        metadata = json.loads(database["metadata"])
        geometry, roles = metadata.get("geometry", {}), metadata.get("channel_roles", {})
        self.x, self.y = QComboBox(), QComboBox()
        for axis, widget in (("x", self.x), ("y", self.y)):
            widget.addItem(tr("Select channel…", "Seleccionar canal…", "Selecionar canal…"), None)
            for row in rows:
                widget.addItem(row["name"], row["id"])
            selected = geometry.get(axis + "_channel_id", roles.get(axis))
            widget.setCurrentIndex(max(0, widget.findData(selected)))
            form.addRow(axis.upper(), widget)
        self.source = QgsProjectionSelectionWidget()
        self.source.setCrs(QgsCoordinateReferenceSystem(geometry.get("crs", "")))
        form.addRow(tr("Source CRS", "CRS de origen", "SRC de origem"), self.source)
        layout.addWidget(source_box)
        self.target_box = QGroupBox(tr("Output coordinates", "Coordenadas de salida", "Coordenadas de saída"))
        output_form = QFormLayout(self.target_box)
        self.target = QgsProjectionSelectionWidget()
        self.target.setCrs(QgsCoordinateReferenceSystem())
        self.output_x, self.output_y = QLineEdit("X_projected"), QLineEdit("Y_projected")
        output_form.addRow(tr("Target CRS", "CRS de destino", "SRC de destino"), self.target)
        output_form.addRow("X", self.output_x)
        output_form.addRow("Y", self.output_y)
        note = QLabel(tr("Full database, without preview filters. New pair becomes active. Null pairs remain null. No vertical transformation.",
            "Base completa, sin filtros de vista. El nuevo par queda activo. Los pares nulos siguen nulos. Sin transformación vertical.",
            "Banco completo, sem filtros de prévia. O novo par fica ativo. Pares nulos permanecem nulos. Sem transformação vertical."))
        note.setWordWrap(True)
        output_form.addRow(note)
        layout.addWidget(self.target_box)
        self.target_box.setVisible(False)
        self.mode.currentIndexChanged.connect(lambda index: self.target_box.setVisible(index == 1))
        info = QToolButton()
        info.setText("i")
        info.setToolTip(tr("Implementation and limits", "Implementación y límites", "Implementação e limites"))
        info.clicked.connect(self.show_info)
        layout.addWidget(info)
        buttons = QDialogButtonBox(qt_enum(QDialogButtonBox, "StandardButton", "Ok") |
                                  qt_enum(QDialogButtonBox, "StandardButton", "Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def show_info(self):
        QMessageBox.information(self, "TerraWorkbench", tr(
            "CRS selector and horizontal transformations: QGIS / PROJ. Storage: PyArrow / SQLite. No approximate fallback is allowed. Accuracy depends on the chosen CRS, datum operation and installed grids. Assignment does not transform values. X is longitude/easting; Y is latitude/northing. Existing map layers remain snapshots.",
            "Selector CRS y transformaciones horizontales: QGIS / PROJ. Almacenamiento: PyArrow / SQLite. No se permite transformación aproximada de respaldo. La precisión depende del CRS, la operación de datum y las rejillas instaladas. Asignar no transforma valores. X es longitud/este; Y es latitud/norte. Las capas existentes siguen siendo instantáneas.",
            "Seletor SRC e transformações horizontais: QGIS / PROJ. Armazenamento: PyArrow / SQLite. Sem transformação aproximada alternativa. A precisão depende do SRC, da operação de datum e das grades instaladas. Atribuir não transforma valores. X é longitude/leste; Y é latitude/norte. As camadas existentes continuam sendo cópias estáticas."))

    def accept(self):
        try:
            if not self.x.currentData() or not self.y.currentData() or self.x.currentData() == self.y.currentData():
                raise ValueError(tr("Choose distinct X/Y channels.", "Selecciona canales X/Y distintos.", "Selecione canais X/Y distintos."))
            source = self.source.crs()
            if not source.isValid():
                raise ValueError(tr("Select the source CRS.", "Selecciona el CRS de origen.", "Selecione o SRC de origem."))
            request = {"x": self.x.currentText(), "y": self.y.currentText(), "source": source.toWkt()}
            if self.mode.currentIndex() == 1:
                target = self.target.crs()
                if not target.isValid() or target == source:
                    raise ValueError(tr("Choose a different valid target CRS.", "Selecciona otro CRS de destino válido.", "Selecione outro SRC de destino válido."))
                names = [self.output_x.text().strip(), self.output_y.text().strip()]
                existing = {c["name"] for c in self.store.channels(self.database_id)}
                if any(not n or len(n) > 200 or "\x00" in n or n in existing for n in names) or names[0] == names[1]:
                    raise ValueError(tr("Use two distinct new channel names.", "Usa dos nombres de canal nuevos y distintos.", "Use dois nomes de canal novos e distintos."))
                request.update(target=target.toWkt(), output_x=names[0], output_y=names[1])
            self.request = request
            self.context = QgsCoordinateTransformContext(QgsProject.instance().transformContext())
            super().accept()
        except ValueError as error:
            QMessageBox.warning(self, self.windowTitle(), str(error))
