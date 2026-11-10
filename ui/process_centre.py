"""Geophysics-wide catalogue: host forms and explicitly identified Core APIs."""

from html import escape
import json

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


class ProcessCentre(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(
            tr(
                "TerraWorkbench — Geophysical processes",
                "TerraWorkbench — Procesos geofísicos",
                "TerraWorkbench — Processos geofísicos",
            )
        )
        self.resize(1180, 780)
        self.setMinimumSize(820, 580)
        layout = QVBoxLayout(self)
        title = QLabel(
            tr(
                "Explore all disciplines · inspect the method · choose the correct input",
                "Explora todas las disciplinas · revisa el método · elige la entrada correcta",
                "Explore todas as disciplinas · consulte o método · escolha a entrada correta",
            )
        )
        title.setWordWrap(True)
        layout.addWidget(title)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(
            tr(
                "Search name, group, domain or ID…",
                "Buscar nombre, grupo, dominio o ID…",
                "Buscar nome, grupo, domínio ou ID…",
            )
        )
        self.mode = QComboBox()
        for value, labels in (
            ("all", ("All interfaces", "Todas las interfaces", "Todas as interfaces")),
            ("qgis", ("QGIS forms", "Formularios QGIS", "Formulários QGIS")),
            ("core", ("Core API", "API del core", "API do core")),
        ):
            self.mode.addItem(tr(*labels), value)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.mode)
        refresh = QPushButton(tr("Refresh", "Actualizar", "Atualizar"))
        refresh.clicked.connect(self.refresh)
        filters.addWidget(refresh)
        layout.addLayout(filters)
        split = QSplitter(qt_enum(Qt, "Orientation", "Horizontal"))
        self.tree = QTreeWidget()
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
        self.launch = QPushButton(
            tr(
                "Open processing form…",
                "Abrir formulario de proceso…",
                "Abrir formulário de processo…",
            )
        )
        self.launch.setEnabled(False)
        self.launch.clicked.connect(self.open_form)
        controls.addWidget(self.launch)
        self.workflows = QPushButton(
            tr(
                "Run saved workflow…",
                "Ejecutar workflow guardado…",
                "Executar fluxo salvo…",
            )
        )
        self.workflows.clicked.connect(self.open_workflow)
        controls.addWidget(self.workflows)
        note = QLabel(
            tr(
                "Core entries use signature-based controls and JSON/NPZ inputs. No optional packages are installed here.",
                "Las entradas del core usan controles basados en su firma y entradas JSON/NPZ. Aquí no se instalan paquetes opcionales.",
                "As entradas do core usam controles baseados na assinatura e entradas JSON/NPZ. Nenhum pacote opcional é instalado aqui.",
            )
        )
        note.setWordWrap(True)
        controls.addWidget(note, 1)
        layout.addLayout(controls)
        self.search.textChanged.connect(self.filter_items)
        self.mode.currentIndexChanged.connect(self.filter_items)
        self.tree.currentItemChanged.connect(self.inspect)
        self.tree.itemDoubleClicked.connect(lambda *_: self.open_form())
        self.refresh()

    def refresh(self):
        self.tree.clear()
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
                "{visible} visible / {total} entries · QGIS forms + registered Core expansion; not a completeness certification",
                "{visible} visibles / {total} entradas · formularios QGIS + expansión registrada del core; no certifica cobertura completa",
                "{visible} visíveis / {total} entradas · formulários QGIS + expansão registrada do core; não certifica cobertura completa",
            ).format(visible=visible, total=len(self.entries))
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
                domain = getattr(
                    algorithm,
                    "processing_domain",
                    tr("Not declared", "No declarado", "Não declarado"),
                )
                html = f"<h2>{escape(title)}</h2><p>{escape(key)}<br>{escape(translate(domain))}</p>"
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
                html += (
                    "<h3>"
                    + escape(
                        tr(
                            "Implementation and libraries",
                            "Implementación y librerías",
                            "Implementação e bibliotecas",
                        )
                    )
                    + "</h3>"
                )
                details = getattr(algorithm, "implementation_details", ())
                html += (
                    "<ul>"
                    + "".join(
                        f"<li>{escape(translate(str(label)))}: {escape(translate(str(value)))}</li>"
                        for label, value in details
                    )
                    + "</ul>"
                    if details
                    else escape(
                        tr(
                            "Not declared by this algorithm",
                            "No declarado por este algoritmo",
                            "Não declarado por este algoritmo",
                        )
                    )
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
                    html += f"<tr><td><b>{escape(parameter.name())}</b><br>{escape(translate(parameter.description()))}</td><td>{escape(str(parameter.defaultValue()))}</td></tr>"
                html += (
                    "</table><p>"
                    + escape(
                        tr(
                            "Opening the form does not run the process. Review CRS, units, data, parameters and output paths before execution.",
                            "Abrir el formulario no ejecuta el proceso. Revisa CRS, unidades, datos, parámetros y rutas de salida antes de ejecutar.",
                            "Abrir o formulário não executa o processo. Revise SRC, unidades, dados, parâmetros e caminhos de saída antes de executar.",
                        )
                    )
                    + "</p>"
                )
            else:
                info = operation_info(source["id"])
                html = f"<h2>{escape(operation_title(info['id']))}</h2><p>{escape(info['id'])} · {escape(domain_label(info['domain']))}</p>"
                html += (
                    "<p>"
                    + escape(
                        tr(
                            "Experimental expansion: synthetic tests only; this is not field validation or complete coverage of the discipline.",
                            "Expansión experimental: solo pruebas sintéticas; no equivale a validación de campo ni cobertura completa de la disciplina.",
                            "Expansão experimental: apenas testes sintéticos; não equivale à validação de campo nem à cobertura completa da disciplina.",
                        )
                    )
                    + "</p>"
                )
                html += operation_guidance_html(info["id"])
                html += f"<pre>{escape(info['module'] + '.' + info['function'] + info['signature'])}</pre>"
                html += (
                    "<h3>"
                    + escape(
                        tr(
                            "Libraries and optional engine",
                            "Librerías y motor opcional",
                            "Bibliotecas e motor opcional",
                        )
                    )
                    + f"</h3><pre>{escape(json.dumps({'base_libraries': info['base_libraries'], 'optional_engine': info['optional_engine'], 'optional_extra': info['optional_extra']}, indent=2))}</pre>"
                )
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
