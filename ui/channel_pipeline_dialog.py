"""Version-aware channel lineage rendered as a native, inspectable flow graph."""

import json
from html import escape

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QBrush, QColor, QPen, QPolygonF
from qgis.PyQt.QtCore import QPointF
from qgis.PyQt.QtWidgets import (
    QDialog,
    QGraphicsScene,
    QGraphicsView,
    QGraphicsItem,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QComboBox,
    QTabWidget,
    QTextBrowser,
)

from ..qgis_plugin.qgis_compat import qt_enum
from .survey_workspace_dialog import tr


class ChannelPipelineDialog(QDialog):
    def __init__(self, pipeline, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.current_key = pipeline["root"]
        self.node_items = {}
        self.requested_step = None
        self.setWindowTitle(
            tr("Channel pipeline", "Pipeline del canal", "Pipeline do canal")
        )
        self.resize(1080, 720)
        layout = QVBoxLayout(self)
        header = QLabel(
            tr(
                "Sources → transformations → selected channel",
                "Fuentes → transformaciones → canal seleccionado",
                "Fontes → transformações → canal selecionado",
            )
        )
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(header)
        note = QLabel(
            tr(
                "Click a node for its exact parameters and input versions. Names shown are current; lineage follows immutable versions.",
                "Selecciona un nodo para ver parámetros y versiones de entrada. Se muestran nombres actuales; la historia sigue versiones inmutables.",
                "Selecione um nó para ver parâmetros e versões de entrada. Os nomes são atuais; o histórico segue versões imutáveis.",
            )
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        navigation = QHBoxLayout()
        stage_label = QLabel(tr("Stage", "Etapa", "Etapa"))
        self.stages = QComboBox()
        self.stages.setMinimumContentsLength(24)
        self.stages.setSizeAdjustPolicy(
            qt_enum(
                QComboBox, "SizeAdjustPolicy", "AdjustToMinimumContentsLengthWithIcon"
            )
        )
        stage_label.setBuddy(self.stages)
        navigation.addWidget(stage_label)
        navigation.addWidget(self.stages, 1)
        self.output_button = QPushButton(
            tr("Selected output", "Salida seleccionada", "Saída selecionada")
        )
        self.output_button.clicked.connect(
            lambda: self.select_node(self.pipeline["root"])
        )
        navigation.addWidget(self.output_button)
        self.reuse_button = QPushButton(
            tr(
                "Edit and run step…",
                "Editar y ejecutar etapa…",
                "Editar e executar etapa…",
            )
        )
        self.reuse_button.clicked.connect(self.request_reuse)
        navigation.addWidget(self.reuse_button)
        layout.addLayout(navigation)
        splitter = QSplitter(qt_enum(Qt, "Orientation", "Horizontal"))
        layout.addWidget(splitter, 1)
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setDragMode(qt_enum(QGraphicsView, "DragMode", "ScrollHandDrag"))
        splitter.addWidget(self.view)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.overview = QTextBrowser()
        self.overview.document().setDefaultStyleSheet("pre { white-space: pre-wrap; }")
        self.overview.setOpenLinks(False)
        self.overview.anchorClicked.connect(self.follow_input)
        self.inspector = QTabWidget()
        self.inspector.addTab(
            self.overview, tr("Step details", "Detalle de etapa", "Detalhes da etapa")
        )
        self.inspector.addTab(
            self.details, tr("Technical JSON", "JSON técnico", "JSON técnico")
        )
        splitter.addWidget(self.inspector)
        splitter.setSizes([610, 470])
        controls = QHBoxLayout()
        for label, callback in (
            ("+", lambda: self.view.scale(1.25, 1.25)),
            ("−", lambda: self.view.scale(0.8, 0.8)),
            (tr("Fit", "Ajustar", "Ajustar"), self.fit),
            (
                tr("Copy step JSON", "Copiar etapa JSON", "Copiar etapa JSON"),
                self.copy_step,
            ),
            (
                tr(
                    "Copy pipeline JSON", "Copiar pipeline JSON", "Copiar pipeline JSON"
                ),
                self.copy_json,
            ),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            controls.addWidget(button)
        layout.addLayout(controls)
        self.draw()
        self.scene.selectionChanged.connect(self.selected)
        self.stages.currentIndexChanged.connect(self.stage_changed)
        self.select_node(pipeline["root"])

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
        for level in sorted(levels):
            for key in levels[level]:
                node = nodes[key]
                self.stages.addItem(
                    f"{level + 1} · {node['name']} · v{node['number']}", key
                )
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
            self.scene.addPolygon(
                QPolygonF(
                    [QPointF(x2, y2), QPointF(x2 - 5, y2 - 9), QPointF(x2 + 5, y2 - 9)]
                ),
                pen,
                QBrush(QColor("#8295a5")),
            )
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
            item = self.scene.addRect(
                0,
                0,
                280,
                92,
                QPen(QColor("#248c91" if chosen else "#93a4b3"), 2),
                QBrush(QColor("#e3f4f1" if chosen else "#f4f7fa")),
            )
            item.setPos(x, y)
            item.setFlag(
                qt_enum(QGraphicsItem, "GraphicsItemFlag", "ItemIsSelectable"), True
            )
            item.setData(0, key)
            self.node_items[key] = item
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
                summary = params.get("domain", "—")
                if method in ("mean", "median", "despike"):
                    summary += f" · w={params.get('window', '—')}"
                elif method in ("lowpass", "highpass", "bandpass") and all(
                    k in params for k in ("cutoff", "order")
                ):
                    summary += f" · f={params['cutoff']:g} · n={params['order']}"
            text = self.scene.addText(
                f"{node['name'][:34]} · v{node['number']}\n{label}\n{summary[:42]}"
            )
            text.setDefaultTextColor(QColor("#153844"))
            text.setTextWidth(262)
            text.setParentItem(item)
            text.setPos(8, 4)
            text.setAcceptedMouseButtons(qt_enum(Qt, "MouseButton", "NoButton"))
            item.setToolTip(node["name"] + "\n" + node["created"])
        self.scene.setSceneRect(
            self.scene.itemsBoundingRect().adjusted(-25, -25, 25, 25)
        )

    def show_node(self, key):
        self.current_key = key
        self.reuse_button.setEnabled(
            self.pipeline["nodes"][key]["provenance"].get("operation")
            in ("formula", "channel_filter")
        )
        self.stages.blockSignals(True)
        self.stages.setCurrentIndex(self.stages.findData(key))
        self.stages.blockSignals(False)
        self.details.setPlainText(
            json.dumps(self.pipeline["nodes"][key], ensure_ascii=False, indent=2)
        )
        self.overview.setHtml(self.summary_html(key))

    def summary_html(self, key):
        """Presentation only: never infer unrecorded engines or historical units."""
        node = self.pipeline["nodes"][key]
        provenance = node["provenance"]
        unknown = tr("Not recorded", "No registrado", "Não registrado")

        def value(data):
            return escape(
                json.dumps(data, ensure_ascii=False, indent=2)
                if not isinstance(data, str)
                else data
            )

        def section(title, data):
            return f"<h3>{escape(title)}</h3><pre>{value(data)}</pre>"

        operation = provenance.get("operation", unknown)
        operation_labels = {
            "import": tr("Import", "Importación", "Importação"),
            "formula": tr("Formula", "Fórmula", "Fórmula"),
            "duplicate": tr("Duplicate", "Duplicación", "Duplicação"),
            "reproject": tr("Reproject", "Reproyección", "Reprojeção"),
            "channel_filter": tr(
                "Channel filter", "Filtro de canal", "Filtro de canal"
            ),
        }
        display_name = value(node["name"]).replace("_", "_&#8203;")
        html = f"<h2>{display_name} · v{node['number']}</h2>"
        html += f"<p>{escape(operation_labels.get(operation, operation))}</p>"
        html += (
            "<p>"
            + escape(tr("Created", "Creado", "Criado"))
            + f": {value(node['created'])}<br>"
        )
        html += (
            escape(tr("Exact version", "Versión exacta", "Versão exata"))
            + f": {value(key)}<br>"
        )
        html += (
            escape(
                tr(
                    "Current channel unit",
                    "Unidad actual del canal",
                    "Unidade atual do canal",
                )
            )
            + f": {value(node.get('unit') or unknown)}</p>"
        )
        html += (
            "<h3>"
            + escape(tr("Input versions", "Versiones de entrada", "Versões de entrada"))
            + "</h3>"
        )
        inputs = [edge for edge in self.pipeline["edges"] if edge["target"] == key]
        if inputs:
            html += "<ul>"
            for edge in inputs:
                source = self.pipeline["nodes"][edge["source"]]
                html += f'<li>{value(edge["input_name"])} → <a href="version:{escape(edge["source"], quote=True)}">{value(source["name"])} · v{source["number"]}</a><br>{value(edge["source"])}</li>'
            html += "</ul>"
        else:
            html += (
                "<p>"
                + escape(
                    tr(
                        "No input channel recorded.",
                        "Sin canal de entrada registrado.",
                        "Sem canal de entrada registrado.",
                    )
                )
                + "</p>"
            )
        if "expression" in provenance:
            html += section(
                tr("Formula", "Fórmula", "Fórmula"), provenance["expression"]
            )
        params = provenance.get("parameters")
        parameter_labels = {
            "method": tr("Process", "Proceso", "Processo"),
            "domain": tr("Axis domain", "Dominio del eje", "Domínio do eixo"),
            "axis": tr("Axis channel", "Canal del eje", "Canal do eixo"),
            "group": tr("Transect channel", "Canal de transecta", "Canal de transecto"),
            "sensor": tr("Sensor channel", "Canal de sensor", "Canal de sensor"),
            "max_gap": tr(
                "Maximum gap (axis units)",
                "Hueco máximo (unidades del eje)",
                "Lacuna máxima (unidades do eixo)",
            ),
            "window": tr("Window (samples)", "Ventana (muestras)", "Janela (amostras)"),
            "threshold": tr("Hampel threshold", "Umbral Hampel", "Limiar Hampel"),
            "order": tr("Butterworth order", "Orden Butterworth", "Ordem Butterworth"),
            "cutoff": tr(
                "Lower / single cutoff",
                "Corte inferior / único",
                "Corte inferior / único",
            ),
            "upper_cutoff": tr("Upper cutoff", "Corte superior", "Corte superior"),
            "spacing_tolerance": tr(
                "Spacing tolerance (fraction)",
                "Tolerancia de espaciado (fracción)",
                "Tolerância de espaçamento (fração)",
            ),
            "max_segment_rows": tr(
                "Rows per continuous segment",
                "Filas por tramo continuo",
                "Linhas por trecho contínuo",
            ),
        }
        if isinstance(params, dict):
            html += (
                "<h3>"
                + escape(
                    tr(
                        "Recorded parameters",
                        "Parámetros registrados",
                        "Parâmetros registrados",
                    )
                )
                + "</h3><table cellpadding='5'>"
            )
            for name, data in params.items():
                if name == "method":
                    data = {
                        "mean": tr("Moving mean", "Media móvil", "Média móvel"),
                        "median": tr("Moving median", "Mediana móvil", "Mediana móvel"),
                        "despike": tr(
                            "Hampel despiking",
                            "Eliminar picos · Hampel",
                            "Remover picos · Hampel",
                        ),
                        "detrend": tr(
                            "Linear detrend",
                            "Quitar tendencia lineal",
                            "Remover tendência linear",
                        ),
                        "lowpass": tr(
                            "Butterworth low-pass",
                            "Butterworth pasa-bajos",
                            "Butterworth passa-baixas",
                        ),
                        "highpass": tr(
                            "Butterworth high-pass",
                            "Butterworth pasa-altos",
                            "Butterworth passa-altas",
                        ),
                        "bandpass": tr(
                            "Butterworth band-pass",
                            "Butterworth pasa-banda",
                            "Butterworth passa-faixa",
                        ),
                    }.get(data, data)
                elif name == "domain":
                    data = {
                        "samples": tr(
                            "Samples · row order",
                            "Muestras · orden de filas",
                            "Amostras · ordem das linhas",
                        ),
                        "time": tr(
                            "Time · seconds", "Tiempo · segundos", "Tempo · segundos"
                        ),
                        "distance": tr(
                            "Distance · metres",
                            "Distancia · metros",
                            "Distância · metros",
                        ),
                    }.get(data, data)
                html += f"<tr><td>{escape(parameter_labels.get(name, name))}</td><td>{value(data)}</td></tr>"
            html += "</table>"
            html += (
                "<p>"
                + escape(
                    tr(
                        "All saved settings are shown; some may be inactive for this process. Cutoff units follow the recorded axis domain.",
                        "Se muestran todos los ajustes guardados; algunos pueden estar inactivos para este proceso. Las unidades de corte dependen del dominio del eje registrado.",
                        "Todos os ajustes salvos são mostrados; alguns podem estar inativos para este processo. As unidades de corte seguem o domínio do eixo registrado.",
                    )
                )
                + "</p>"
            )
        else:
            html += section(
                tr("Parameters", "Parámetros", "Parâmetros"),
                unknown if params is None else params,
            )
        html += section(
            tr(
                "Recorded libraries", "Librerías registradas", "Bibliotecas registradas"
            ),
            provenance.get("libraries", unknown),
        )
        for field, title in (
            ("engine", tr("Recorded engine", "Motor registrado", "Motor registrado")),
            (
                "statistics",
                tr(
                    "Execution statistics",
                    "Estadísticas de ejecución",
                    "Estatísticas de execução",
                ),
            ),
            ("ordering", tr("Ordering", "Orden de muestras", "Ordem das amostras")),
            (
                "edges",
                tr("Edge handling", "Tratamiento de bordes", "Tratamento de bordas"),
            ),
        ):
            if field in provenance:
                html += section(title, provenance[field])
        html += (
            "<p>"
            + escape(
                tr(
                    "Read-only inspection. Copying JSON does not execute a recipe.",
                    "Consulta de solo lectura. Copiar JSON no ejecuta una receta.",
                    "Consulta somente leitura. Copiar JSON não executa uma receita.",
                )
            )
            + "</p>"
        )
        return html

    def stage_changed(self, index):
        key = self.stages.itemData(index)
        if key in self.node_items:
            self.select_node(key)

    def select_node(self, key):
        self.scene.blockSignals(True)
        self.scene.clearSelection()
        self.node_items[key].setSelected(True)
        self.scene.blockSignals(False)
        self.show_node(key)
        self.view.ensureVisible(self.node_items[key])

    def follow_input(self, url):
        key = url.path()
        if url.scheme() == "version" and key in self.node_items:
            self.select_node(key)

    def selected(self):
        items = self.scene.selectedItems()
        if items:
            self.show_node(items[0].data(0))

    def fit(self):
        self.view.fitInView(
            self.scene.sceneRect(), qt_enum(Qt, "AspectRatioMode", "KeepAspectRatio")
        )

    def showEvent(self, event):
        super().showEvent(event)
        self.fit()

    def copy_json(self):
        from qgis.PyQt.QtWidgets import QApplication

        QApplication.clipboard().setText(
            json.dumps(self.pipeline, ensure_ascii=False, indent=2)
        )

    def copy_step(self):
        from qgis.PyQt.QtWidgets import QApplication

        QApplication.clipboard().setText(
            json.dumps(
                self.pipeline["nodes"][self.current_key], ensure_ascii=False, indent=2
            )
        )

    def request_reuse(self):
        node = self.pipeline["nodes"][self.current_key]
        if node["provenance"].get("operation") in ("formula", "channel_filter"):
            self.requested_step = node
            self.accept()
