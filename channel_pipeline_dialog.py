"""Version-aware channel lineage rendered as a native, inspectable flow graph."""

import json

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QBrush, QColor, QPen, QPolygonF
from qgis.PyQt.QtCore import QPointF
from qgis.PyQt.QtWidgets import (
    QDialog, QGraphicsScene, QGraphicsView, QGraphicsItem, QHBoxLayout, QLabel,
    QPushButton, QSplitter, QTextEdit, QVBoxLayout,
)

from .qgis_compat import qt_enum
from .survey_workspace_dialog import tr


class ChannelPipelineDialog(QDialog):
    def __init__(self, pipeline, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.setWindowTitle(tr("Channel pipeline", "Pipeline del canal", "Pipeline do canal"))
        self.resize(1080, 720)
        layout = QVBoxLayout(self)
        header = QLabel(tr("Sources → transformations → selected channel", "Fuentes → transformaciones → canal seleccionado", "Fontes → transformações → canal selecionado"))
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(header)
        note = QLabel(tr("Click a node for its exact parameters and input versions. Names shown are current; lineage follows immutable versions.",
            "Selecciona un nodo para ver parámetros y versiones de entrada. Se muestran nombres actuales; la historia sigue versiones inmutables.",
            "Selecione um nó para ver parâmetros e versões de entrada. Os nomes são atuais; o histórico segue versões imutáveis."))
        note.setWordWrap(True)
        layout.addWidget(note)
        splitter = QSplitter(qt_enum(Qt, "Orientation", "Horizontal"))
        layout.addWidget(splitter, 1)
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setDragMode(qt_enum(QGraphicsView, "DragMode", "ScrollHandDrag"))
        splitter.addWidget(self.view)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        splitter.addWidget(self.details)
        splitter.setSizes([700, 360])
        controls = QHBoxLayout()
        for label, callback in (("+", lambda: self.view.scale(1.25, 1.25)),
                                ("−", lambda: self.view.scale(0.8, 0.8)),
                                (tr("Fit", "Ajustar", "Ajustar"), self.fit),
                                (tr("Copy pipeline JSON", "Copiar pipeline JSON", "Copiar pipeline JSON"), self.copy_json)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            controls.addWidget(button)
        layout.addLayout(controls)
        self.draw()
        self.scene.selectionChanged.connect(self.selected)
        self.show_node(pipeline["root"])

    def draw(self):
        nodes, edges = self.pipeline["nodes"], self.pipeline["edges"]
        parents = {key: [] for key in nodes}
        for edge in edges:
            parents[edge["target"]].append(edge["source"])
        depths, visiting = {}, set()

        def depth(key):
            if key in visiting:
                raise ValueError("Cycle detected in channel provenance.")
            if key not in depths:
                visiting.add(key)
                depths[key] = 1 + max((depth(p) for p in parents[key]), default=-1)
                visiting.remove(key)
            return depths[key]

        levels = {}
        for key in nodes:
            levels.setdefault(depth(key), []).append(key)
        positions = {}
        for level, keys in levels.items():
            for column, key in enumerate(keys):
                positions[key] = ((column - (len(keys) - 1) / 2) * 310, level * 150)
        for edge in edges:
            x1, y1 = positions[edge["source"]]
            x2, y2 = positions[edge["target"]]
            x1 += 140
            x2 += 140
            y1 += 92
            pen = QPen(QColor("#8295a5"), 2)
            line = self.scene.addLine(x1, y1, x2, y2 - 8, pen)
            line.setToolTip(edge["input_name"])
            self.scene.addPolygon(QPolygonF([QPointF(x2, y2), QPointF(x2 - 5, y2 - 9), QPointF(x2 + 5, y2 - 9)]), pen, QBrush(QColor("#8295a5")))
        operation_labels = {
            "import": tr("Import", "Importación", "Importação"),
            "formula": tr("Formula", "Fórmula", "Fórmula"),
            "duplicate": tr("Duplicate", "Duplicación", "Duplicação"),
            "reproject": tr("Reproject", "Reproyección", "Reprojeção"),
            "channel_filter": tr("Filter", "Filtro", "Filtro"),
        }
        for key, node in nodes.items():
            x, y = positions[key]
            chosen = key == self.pipeline["root"]
            item = self.scene.addRect(0, 0, 280, 92, QPen(QColor("#248c91" if chosen else "#93a4b3"), 2),
                                      QBrush(QColor("#e3f4f1" if chosen else "#f4f7fa")))
            item.setPos(x, y)
            item.setFlag(qt_enum(QGraphicsItem, "GraphicsItemFlag", "ItemIsSelectable"), True)
            item.setData(0, key)
            provenance = node["provenance"]
            operation = provenance.get("operation", "unknown")
            label = operation_labels.get(operation, operation)
            method = provenance.get("parameters", {}).get("method")
            if method:
                label += " · " + method
            summary = node["unit"] or "—"
            if operation == "formula":
                summary = provenance.get("expression", summary)
            elif method:
                params = provenance["parameters"]
                summary = params["domain"]
                if method in ("mean", "median", "despike"):
                    summary += f" · w={params['window']}"
                elif method != "detrend":
                    summary += f" · f={params['cutoff']:g} · n={params['order']}"
            text = self.scene.addText(f"{node['name'][:34]} · v{node['number']}\n{label}\n{summary[:42]}")
            text.setDefaultTextColor(QColor("#153844"))
            text.setTextWidth(262)
            text.setParentItem(item)
            text.setPos(8, 4)
            text.setAcceptedMouseButtons(qt_enum(Qt, "MouseButton", "NoButton"))
            item.setToolTip(node["name"] + "\n" + node["created"])
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-25, -25, 25, 25))

    def show_node(self, key):
        self.details.setPlainText(json.dumps(self.pipeline["nodes"][key], ensure_ascii=False, indent=2))

    def selected(self):
        items = self.scene.selectedItems()
        if items:
            self.show_node(items[0].data(0))

    def fit(self):
        self.view.fitInView(self.scene.sceneRect(), qt_enum(Qt, "AspectRatioMode", "KeepAspectRatio"))

    def showEvent(self, event):
        super().showEvent(event)
        self.fit()

    def copy_json(self):
        from qgis.PyQt.QtWidgets import QApplication
        QApplication.clipboard().setText(json.dumps(self.pipeline, ensure_ascii=False, indent=2))
