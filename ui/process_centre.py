"""Geophysics-wide catalogue: host forms and explicitly identified Core APIs."""

from html import escape

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from ..qgis_plugin.qgis_compat import qt_enum
from .i18n import translate
from .core_presentation import operation_title, operation_guidance_html, domain_label
from .survey_workspace_dialog import tr
from ..terraworkbench_core.operations import list_operations, operation_info


PARAMETER_KINDS = {
    "source": ("Vector layer", "Capa vectorial", "Camada vetorial"),
    "vector": ("Vector layer", "Capa vectorial", "Camada vetorial"),
    "raster": ("Raster layer", "Capa ráster", "Camada raster"),
    "multilayer": ("Layers", "Capas", "Camadas"),
    "field": ("Field", "Campo", "Campo"),
    "band": ("Band", "Banda", "Banda"),
    "number": ("Number", "Número", "Número"),
    "distance": ("Distance", "Distancia", "Distância"),
    "enum": ("Option", "Opción", "Opção"),
    "boolean": ("Yes / no", "Sí / no", "Sim / não"),
    "string": ("Text", "Texto", "Texto"),
    "file": ("File", "Archivo", "Arquivo"),
    "crs": ("CRS", "SRC", "SRC"),
    "extent": ("Extent", "Extensión", "Extensão"),
    "sink": ("Output layer", "Capa de salida", "Camada de saída"),
    "vectorDestination": ("Output layer", "Capa de salida", "Camada de saída"),
    "rasterDestination": ("Output raster", "Ráster de salida", "Raster de saída"),
    "fileDestination": ("Output file", "Archivo de salida", "Arquivo de saída"),
    "folderDestination": ("Output folder", "Carpeta de salida", "Pasta de saída"),
}


def parameter_summary(parameter):
    """Describe a parameter by its default, or by its kind when it has none."""
    default = parameter.defaultValue()
    if parameter.type() == "enum" and isinstance(default, int):
        options = parameter.options()
        if 0 <= default < len(options):
            default = translate(options[default])
    if default is None or default == "":
        kind = PARAMETER_KINDS.get(parameter.type())
        summary = tr(*kind) if kind else parameter.type()
    elif isinstance(default, bool):
        summary = tr("Yes", "Sí", "Sim") if default else tr("No", "No", "Não")
    else:
        summary = str(default)
    try:
        from qgis.core import QgsProcessingParameterDefinition

        optional = bool(parameter.flags() & QgsProcessingParameterDefinition.Flag.FlagOptional)
    except (AttributeError, TypeError):
        optional = False
    if optional:
        summary += " · " + tr("optional", "opcional", "opcional")
    return summary


class ProcessCentre(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.resize(1180, 780)
        self.setMinimumSize(820, 580)
        layout = QVBoxLayout(self)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.mode = QComboBox()
        for value in ("all", "qgis", "core"):
            self.mode.addItem("", value)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.mode)
        self.refresh_button = QPushButton()
        self.refresh_button.clicked.connect(self.refresh)
        filters.addWidget(self.refresh_button)
        layout.addLayout(filters)
        split = QSplitter(qt_enum(Qt, "Orientation", "Horizontal"))
        self.tree = QTreeWidget()
        self.tree.setColumnWidth(0, 370)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        self.browser.setOpenLinks(False)
        self.browser.document().setDefaultStyleSheet("pre { white-space: pre-wrap; }")
        split.addWidget(self.tree)
        split.addWidget(self.browser)
        split.setSizes([510, 650])
        layout.addWidget(split, 1)
        self.count = QLabel()
        layout.addWidget(self.count)
        controls = QHBoxLayout()
        self.launch = QPushButton()
        self.launch.setEnabled(False)
        self.launch.clicked.connect(self.open_form)
        controls.addWidget(self.launch)
        self.workflows = QPushButton()
        self.workflows.clicked.connect(self.open_workflow)
        controls.addWidget(self.workflows)
        layout.addLayout(controls)
        self.search.textChanged.connect(self.filter_items)
        self.mode.currentIndexChanged.connect(self.filter_items)
        self.tree.currentItemChanged.connect(self.inspect)
        self.tree.itemDoubleClicked.connect(lambda *_: self.open_form())
        self.retranslate()

    def retranslate(self):
        self.setWindowTitle(
            tr(
                "TerraWorkbench — Geophysical processes",
                "TerraWorkbench — Procesos geofísicos",
                "TerraWorkbench — Processos geofísicos",
            )
        )
        self.search.setPlaceholderText(
            tr(
                "Search name, group, domain or ID…",
                "Buscar nombre, grupo, dominio o ID…",
                "Buscar nome, grupo, domínio ou ID…",
            )
        )
        for value, labels in (
            ("all", ("All interfaces", "Todas las interfaces", "Todas as interfaces")),
            ("qgis", ("QGIS forms", "Formularios QGIS", "Formulários QGIS")),
            ("core", ("Core API", "API del core", "API do core")),
        ):
            self.mode.setItemText(self.mode.findData(value), tr(*labels))
        self.tree.setHeaderLabels(
            [
                tr(
                    "Discipline / process",
                    "Disciplina / proceso",
                    "Disciplina / processo",
                ),
                tr("Interface", "Interfaz", "Interface"),
            ]
        )
        self.workflows.setText(
            tr(
                "Run saved workflow…",
                "Ejecutar workflow guardado…",
                "Executar fluxo salvo…",
            )
        )
        self.launch.setText(
            tr(
                "Open processing form…",
                "Abrir formulario de proceso…",
                "Abrir formulário de processo…",
            )
        )
        self.refresh_button.setText(tr("Refresh", "Actualizar", "Atualizar"))
        self.refresh()

    def refresh(self):
        current = self.tree.currentItem()
        selected = current.data(0, 256) if current is not None else None
        self.tree.clear()
        selected_item = None
        self.entries = {}
        groups = {}
        algorithms = sorted(
            (
                a
                for a in QgsApplication.processingRegistry().algorithms()
                if a.id().startswith("terraworkbench:")
            ),
            key=lambda a: (a.group(), a.displayName()),
        )
        for algorithm in algorithms:
            group = groups.setdefault(
                ("qgis", algorithm.group()),
                QTreeWidgetItem([algorithm.group(), "QGIS"]),
            )
            key = algorithm.id()
            self.entries[key] = ("qgis", algorithm)
            item = QTreeWidgetItem([algorithm.displayName(), "QGIS"])
            item.setData(0, 256, key)
            if key == selected:
                selected_item = item
            item.setToolTip(
                0, key + " · " + getattr(algorithm, "processing_domain", "")
            )
            group.addChild(item)
        labels = {
            "gravity": ("Gravity", "Gravimetría", "Gravimetria"),
            "depth": (
                "Source depth · Euler / Werner / SPI",
                "Profundidad de fuentes · Euler / Werner / SPI",
                "Profundidade de fontes · Euler / Werner / SPI",
            ),
            "potential": (
                "Potential fields",
                "Campos potenciales",
                "Campos potenciais",
            ),
            "radiometry": ("Radiometry", "Radiometría", "Radiometria"),
            "electrical": ("Electrical", "Métodos eléctricos", "Métodos elétricos"),
            "em": ("Electromagnetics", "Electromagnetismo", "Eletromagnetismo"),
            "fdem": ("Frequency-domain EM", "EM en frecuencia", "EM em frequência"),
            "tdem": ("Time-domain EM", "EM en tiempo", "EM no tempo"),
            "tem": ("Transient EM", "EM transitorio", "EM transiente"),
            "ip": (
                "Induced polarization",
                "Polarización inducida",
                "Polarização induzida",
            ),
            "sip": (
                "Spectral induced polarization",
                "Polarización inducida espectral",
                "Polarização induzida espectral",
            ),
            "waveform": (
                "Waveform processing",
                "Procesamiento de formas de onda",
                "Processamento de formas de onda",
            ),
            "mt": ("Magnetotellurics", "Magnetotelúrica", "Magnetotelúrica"),
            "gpr": ("Ground penetrating radar", "Georradar", "Georradar"),
            "seismic": ("Seismic", "Sísmica", "Sísmica"),
            "passive": ("Passive seismic", "Sísmica pasiva", "Sísmica passiva"),
            "sp": ("Self potential", "Potencial espontáneo", "Potencial espontâneo"),
            "borehole": ("Borehole", "Registros de pozo", "Perfis de poço"),
            "inversion": (
                "Inversion and uncertainty",
                "Inversión e incertidumbre",
                "Inversão e incerteza",
            ),
            "regional": (
                "Regional modelling",
                "Modelado regional",
                "Modelagem regional",
            ),
            "spectra": ("Spectral analysis", "Análisis espectral", "Análise espectral"),
            "magnetic": ("Magnetics", "Magnetometría", "Magnetometria"),
            "structural": (
                "Structural attributes",
                "Atributos estructurales",
                "Atributos estruturais",
            ),
        }
        for metadata in list_operations():
            prefix = metadata["id"].split(".")[0]
            group_name = tr(*labels[prefix]) if prefix in labels else prefix
            group = groups.setdefault(
                ("core", prefix), QTreeWidgetItem([group_name, "Core API"])
            )
            key = "core:" + metadata["id"]
            self.entries[key] = ("core", metadata)
            item = QTreeWidgetItem([operation_title(metadata["id"]), "Core API"])
            item.setData(0, 256, key)
            if key == selected:
                selected_item = item
            item.setToolTip(0, domain_label(metadata["domain"]))
            group.addChild(item)
        for _, group in sorted(
            groups.items(), key=lambda item: (item[0][0] != "qgis", item[1].text(0))
        ):
            self.tree.addTopLevelItem(group)
            group.setExpanded(True)
        self.browser.setPlainText(
            tr(
                "Select a process to inspect its inputs, domain, libraries and limitations.",
                "Selecciona un proceso para revisar entradas, dominio, librerías y limitaciones.",
                "Selecione um processo para consultar entradas, domínio, bibliotecas e limitações.",
            )
        )
        self.launch.setEnabled(False)
        self.filter_items()
        if selected_item is not None:
            self.tree.setCurrentItem(selected_item)

    def filter_items(self, *_):
        query, mode = self.search.text().casefold().strip(), self.mode.currentData()
        visible = 0
        for index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(index)
            count = 0
            for row in range(group.childCount()):
                item = group.child(row)
                key = item.data(0, 256)
                kind, source = self.entries[key]
                domain = (
                    source["domain"]
                    if kind == "core"
                    else getattr(source, "processing_domain", "")
                )
                haystack = " ".join(
                    (
                        group.text(0),
                        item.text(0),
                        key,
                        domain,
                        domain_label(domain) if kind == "core" else translate(domain),
                    )
                ).casefold()
                show = (mode == "all" or mode == kind) and query in haystack
                item.setHidden(not show)
                count += show
            group.setHidden(not count)
            visible += count
        self.count.setText(
            tr(
                "{visible} processes",
                "{visible} procesos",
                "{visible} processos",
            ).format(visible=visible)
        )
        item = self.tree.currentItem()
        if item is not None and item.data(0, 256):
            self.inspect(item)

    def inspect(self, item, previous=None):
        key = item.data(0, 256) if item is not None else None
        if key not in self.entries:
            self.launch.setEnabled(False)
            return
        kind, source = self.entries[key]
        self.launch.setEnabled(not item.isHidden())
        self.launch.setText(
            tr(
                "Open processing form…",
                "Abrir formulario de proceso…",
                "Abrir formulário de processo…",
            )
            if kind == "qgis"
            else tr(
                "Open advanced Core console…",
                "Abrir consola avanzada del core…",
                "Abrir console avançado do core…",
            )
        )
        try:
            if kind == "qgis":
                algorithm = source
                title = algorithm.displayName()
                # Fall back to the QGIS group so every entry names its discipline.
                domain = getattr(algorithm, "processing_domain", "") or algorithm.group()
                html = f"<h2>{escape(title)}</h2><p>{escape(key)}"
                if domain:
                    html += f"<br>{escape(translate(domain))}"
                html += "</p>"
                html += (
                    "<h3>"
                    + escape(
                        tr(
                            "Method and limitations",
                            "Método y limitaciones",
                            "Método e limitações",
                        )
                    )
                    + "</h3><p>"
                    + escape(translate(algorithm.shortHelpString()))
                    + "</p>"
                )
                details = getattr(algorithm, "implementation_details", ())
                # Show the section only when the algorithm documents it.
                if details:
                    html += (
                        "<h3>"
                        + escape(
                            tr(
                                "Implementation and libraries",
                                "Implementación y librerías",
                                "Implementação e bibliotecas",
                            )
                        )
                        + "</h3><ul>"
                        + "".join(
                            f"<li>{escape(translate(str(label)))}: {escape(translate(str(value)))}</li>"
                            for label, value in details
                        )
                        + "</ul>"
                    )
                html += (
                    "<h3>"
                    + escape(
                        tr(
                            "Inputs and parameters",
                            "Entradas y parámetros",
                            "Entradas e parâmetros",
                        )
                    )
                    + "</h3><table cellpadding='5'>"
                )
                for parameter in algorithm.parameterDefinitions():
                    html += f"<tr><td><b>{escape(parameter.name())}</b><br>{escape(translate(parameter.description()))}</td><td>{escape(parameter_summary(parameter))}</td></tr>"
                html += "</table>"
            else:
                info = operation_info(source["id"])
                html = f"<h2>{escape(operation_title(info['id']))}</h2><p>{escape(info['id'])} · {escape(domain_label(info['domain']))}</p>"
                html += operation_guidance_html(info["id"])
            self.browser.setHtml(html)
        except Exception as error:
            self.browser.setPlainText(str(error))
            self.launch.setEnabled(False)

    def open_workflow(self):
        from .core_workflow_dialog import CoreWorkflowDialog

        dialog = CoreWorkflowDialog(self)
        dialog.exec()
        dialog.deleteLater()

    def open_form(self):
        item = self.tree.currentItem()
        key = item.data(0, 256) if item is not None else None
        if key not in self.entries or item.isHidden():
            return
        if self.entries[key][0] == "core":
            from .core_job_dialog import CoreJobDialog

            dialog = CoreJobDialog(self.entries[key][1]["id"], self)
            dialog.exec()
            dialog.deleteLater()
            return
        import processing

        try:
            processing.execAlgorithmDialog(key, {})
        except Exception as error:
            QMessageBox.warning(self, self.windowTitle(), str(error))
