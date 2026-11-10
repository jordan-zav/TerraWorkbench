"""Survey project manager. Long I/O runs on a cancellable worker thread."""

from pathlib import Path
import json
import csv
import uuid
from html import escape

from qgis.PyQt.QtCore import QSettings, QThread, pyqtSignal, QUrl, QUrlQuery
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QGridLayout,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QSplitter,
    QTabWidget,
    QMenu,
)
from qgis.core import QgsProject, QgsVectorLayer, QgsCoordinateReferenceSystem

from .i18n import language
from ..qgis_plugin.qgis_compat import qt_enum
from ..compat.survey_store import SurveyStore
from ..terraworkbench_core.survey_explorer import (
    read_survey_page,
    read_survey_profile,
    survey_group_values,
    compare_survey_profiles,
)
from .survey_profile_widget import SurveyProfileWidget
from qgis.PyQt.QtCore import Qt

KEY_WORKSPACE = "TerraWorkbench/surveyWorkspace"


def tr(en, es, pt):
    return {"en": en, "es": es, "pt": pt}.get(language(), en)


class StoreWorker(QThread):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            result = self.operation(
                self.isInterruptionRequested,
                lambda count: self.progress.emit(str(count)),
            )
            self.completed.emit(result)
        except InterruptedError:
            self.cancelled.emit()
        except Exception as error:
            self.failed.emit(str(error))


class SurveyWorkspaceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(
            tr("Survey databases", "Bases de levantamientos", "Bancos de levantamentos")
        )
        self.resize(1120, 760)
        self.setMinimumSize(780, 580)
        self.store = None
        self.worker = None
        self._dispose = False
        self._close_requested = False
        self._last_db_ids = ()
        self._page_offset = 0
        self._page_context = None
        self._page_has_next = False
        self._channel_info = {}
        layout = QVBoxLayout(self)
        self.controls = QWidget()
        body = QVBoxLayout(self.controls)
        layout.addWidget(self.controls)
        buttons = QHBoxLayout()
        body.addLayout(buttons)
        for labels, callback in (
            (("New project…", "Nuevo proyecto…", "Novo projeto…"), self.new_project),
            (("Open project…", "Abrir proyecto…", "Abrir projeto…"), self.open_project),
            (
                (
                    "Import text / Parquet…",
                    "Importar texto / Parquet…",
                    "Importar texto / Parquet…",
                ),
                self.import_files,
            ),
        ):
            button = QPushButton(tr(*labels))
            button.clicked.connect(callback)
            buttons.addWidget(button)
        self.path_label = QLabel(
            tr(
                "Choose a working folder",
                "Elige una carpeta de trabajo",
                "Escolha uma pasta de trabalho",
            )
        )
        self.path_label.setWordWrap(True)
        processes = QPushButton(
            tr(
                "All geophysical processes…",
                "Todos los procesos geofísicos…",
                "Todos os processos geofísicos…",
            )
        )
        processes.clicked.connect(self.show_processes)
        buttons.addWidget(processes)
        body.addWidget(self.path_label)
        splitter = QSplitter(qt_enum(Qt, "Orientation", "Horizontal"))
        body.addWidget(splitter, 1)
        sidebar = QWidget()
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 0, 6, 0)
        side.addWidget(QLabel(tr("Databases", "Bases", "Bancos")))
        hint = QLabel(
            tr(
                "Select databases to see their common channels.",
                "Selecciona bases para ver sus canales comunes.",
                "Selecione bancos para ver seus canais comuns.",
            )
        )
        hint.setWordWrap(True)
        side.addWidget(hint)
        splitter.addWidget(sidebar)
        viewer = QWidget()
        view = QVBoxLayout(viewer)
        view.setContentsMargins(6, 0, 0, 0)
        splitter.addWidget(viewer)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 820])
        self.databases_list = QListWidget()
        self.databases_list.setSelectionMode(
            qt_enum(QAbstractItemView, "SelectionMode", "ExtendedSelection")
        )
        self.databases_list.itemSelectionChanged.connect(self.refresh_channels)
        self.channels_list = QListWidget()
        self.channels_list.setSelectionMode(
            qt_enum(QAbstractItemView, "SelectionMode", "ExtendedSelection")
        )
        side.addWidget(self.databases_list, 1)
        side.addWidget(
            QLabel(
                tr(
                    "Channels · units · version",
                    "Canales · unidades · versión",
                    "Canais · unidades · versão",
                )
            )
        )
        side.addWidget(self.channels_list, 2)
        filtering = QHBoxLayout()
        self.filter_toggle = QPushButton(
            tr(
                "View / export filters…",
                "Filtros de vista / exportación…",
                "Filtros de visualização / exportação…",
            )
        )
        self.filter_toggle.setCheckable(True)
        self.filter_panel = QWidget()
        filter_layout = QVBoxLayout(self.filter_panel)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        self.filter_toggle.toggled.connect(self.filter_panel.setVisible)
        view.addWidget(self.filter_toggle)
        view.addWidget(self.filter_panel)
        self.filter_panel.hide()
        filtering.addWidget(
            QLabel(
                tr(
                    "Additional view/export filter",
                    "Filtro adicional de vista/exportación",
                    "Filtro adicional de visualização/exportação",
                )
            )
        )
        self.filter_channel = QComboBox()
        self.filter_values = QLineEdit()
        self.filter_values.setPlaceholderText(
            tr(
                "Values separated by commas",
                "Valores separados por comas",
                "Valores separados por vírgulas",
            )
        )
        filtering.addWidget(self.filter_channel)
        filtering.addWidget(self.filter_values)
        filter_layout.addLayout(filtering)
        grouping = QGridLayout()
        self.profile_group = QComboBox()
        self.profile_sensor = QComboBox()
        self.group_values = QLineEdit()
        self.sensor_values = QLineEdit()
        self.group_choices, self.sensor_choices = QComboBox(), QComboBox()
        for choices, entry, source in (
            (self.group_choices, self.group_values, self.profile_group),
            (self.sensor_choices, self.sensor_values, self.profile_sensor),
        ):
            choices.setMinimumContentsLength(8)
            choices.addItem(
                tr("Choose value…", "Elegir valor…", "Escolher valor…"), None
            )
            choices.currentIndexChanged.connect(
                lambda index, c=choices, e=entry, s=source: (
                    e.setText(
                        '"' + c.itemData(index).replace('"', '""') + '"'
                        if any(ch in c.itemData(index) for ch in ',"')
                        or c.itemData(index) != c.itemData(index).strip()
                        else c.itemData(index)
                    )
                    if c.itemData(index) is not None
                    and c.property("source_channel") == s.currentData()
                    else None
                )
            )
        self.group_values.setPlaceholderText(
            # Values chosen from the selector are CSV-quoted when necessary.
            tr(
                "All / comma-separated values",
                "Todas / valores separados por comas",
                "Todos / valores separados por vírgulas",
            )
        )
        self.sensor_values.setPlaceholderText(
            tr(
                "All / comma-separated values",
                "Todos / valores separados por comas",
                "Todos / valores separados por vírgulas",
            )
        )
        for row, (label, combo, values) in enumerate(
            (
                (
                    tr("Transect channel", "Canal de transecta", "Canal de transecto"),
                    self.profile_group,
                    self.group_values,
                ),
                (
                    tr("Sensor channel", "Canal de sensor", "Canal de sensor"),
                    self.profile_sensor,
                    self.sensor_values,
                ),
            )
        ):
            grouping.addWidget(QLabel(label), row, 0)
            grouping.addWidget(combo, row, 1)
            grouping.addWidget(values, row, 2)
        grouping.setColumnStretch(2, 1)
        grouping.addWidget(self.group_choices, 0, 3)
        grouping.addWidget(self.sensor_choices, 1, 3)
        self.discover_groups = QPushButton(
            tr(
                "Find transects / sensors",
                "Buscar transectas / sensores",
                "Buscar transectos / sensores",
            )
        )
        self.discover_groups.clicked.connect(self.load_group_values)
        grouping.addWidget(self.discover_groups, 2, 1, 1, 3)
        filter_layout.addLayout(grouping)
        for entry in (self.filter_values, self.group_values, self.sensor_values):
            entry.textChanged.connect(self.update_filter_caption)
        self.actions_button = QPushButton(
            tr("Channel actions…", "Acciones de canales…", "Ações de canais…")
        )
        menu = QMenu(self.actions_button)
        self.actions_button.setMenu(menu)
        side.addWidget(self.actions_button)
        for index, (labels, callback) in enumerate(
            (
                (("Preview", "Vista previa", "Prévia"), self.preview),
                (("Calculate…", "Calcular…", "Calcular…"), self.calculate),
                (("Duplicate…", "Duplicar…", "Duplicar…"), self.duplicate),
                (
                    (
                        "Rename / units…",
                        "Renombrar / unidades…",
                        "Renomear / unidades…",
                    ),
                    self.rename,
                ),
                (("Export CSV", "Exportar CSV", "Exportar CSV"), self.export),
                (
                    ("To QGIS points…", "A puntos QGIS…", "Para pontos QGIS…"),
                    self.to_qgis,
                ),
                (("History", "Historial", "Histórico"), self.history),
                (
                    (
                        "Coordinates and CRS…",
                        "Coordenadas y CRS…",
                        "Coordenadas e SRC…",
                    ),
                    self.coordinates,
                ),
                (
                    ("Filter channel…", "Filtrar canal…", "Filtrar canal…"),
                    self.filter_signal,
                ),
                (
                    ("Channel pipeline…", "Pipeline del canal…", "Pipeline do canal…"),
                    self.channel_pipeline,
                ),
            )
        ):
            action = menu.addAction(tr(*labels))
            action.triggered.connect(lambda checked=False, fn=callback: fn())
        self.views = QTabWidget()
        view.addWidget(self.views, 1)
        table_page = QWidget()
        table_layout = QVBoxLayout(table_page)
        table_layout.setContentsMargins(0, 6, 0, 0)
        navigation = QHBoxLayout()
        self.page_first = QPushButton(tr("First", "Primera", "Primeira"))
        self.page_previous = QPushButton(tr("Previous", "Anterior", "Anterior"))
        self.page_next = QPushButton(tr("Next", "Siguiente", "Próxima"))
        self.page_reload = QPushButton(
            tr("Load selection", "Cargar selección", "Carregar seleção")
        )
        self.page_size = QComboBox()
        for size in (200, 500, 1000):
            self.page_size.addItem(str(size), size)
        for widget in (
            self.page_first,
            self.page_previous,
            self.page_next,
            self.page_reload,
            self.page_size,
        ):
            navigation.addWidget(widget)
        self.page_first.clicked.connect(lambda: self.load_page(0))
        self.page_previous.clicked.connect(
            lambda: self.load_page(
                max(0, self._page_offset - self.page_size.currentData())
            )
        )
        self.page_next.clicked.connect(
            lambda: self.load_page(self._page_offset + self.page_size.currentData())
        )
        self.page_reload.clicked.connect(self.preview)
        self.page_size.setToolTip(
            tr("Rows per page", "Filas por página", "Linhas por página")
        )
        self.page_first.setEnabled(False)
        self.page_previous.setEnabled(False)
        self.page_next.setEnabled(False)
        table_layout.addLayout(navigation)
        self.table = QTableWidget()
        self.table.setEditTriggers(
            qt_enum(QAbstractItemView, "EditTrigger", "NoEditTriggers")
        )
        table_layout.addWidget(self.table, 1)
        self.page_status = QLabel(
            tr(
                "Select channels and load a page.",
                "Selecciona canales y carga una página.",
                "Selecione canais e carregue uma página.",
            )
        )
        self.page_status.setWordWrap(True)
        table_layout.addWidget(self.page_status)
        self.views.addTab(table_page, tr("Table", "Tabla", "Tabela"))
        profile_page = QWidget()
        profile_layout = QVBoxLayout(profile_page)
        profile_controls = QGridLayout()
        self.profile_channel = QComboBox()
        self.profile_axis = QComboBox()
        self.profile_compare = QComboBox()
        self.profile_compare_mode = QComboBox()
        self.profile_compare_mode.addItem(
            tr("Overlay A / B", "Superponer A / B", "Sobrepor A / B"), "overlay"
        )
        self.profile_compare_mode.addItem(
            tr("Difference B − A", "Diferencia B − A", "Diferença B − A"), "difference"
        )
        self.profile_load = QPushButton(
            tr("Draw profile", "Dibujar perfil", "Desenhar perfil")
        )
        profile_controls.addWidget(QLabel(tr("Channel", "Canal", "Canal")), 0, 0)
        profile_controls.addWidget(self.profile_channel, 0, 1)
        profile_controls.addWidget(QLabel(tr("X axis", "Eje X", "Eixo X")), 1, 0)
        profile_controls.addWidget(self.profile_axis, 1, 1)
        profile_controls.addWidget(self.profile_load, 0, 2, 2, 1)
        profile_controls.setColumnStretch(1, 1)
        self.profile_distance = QCheckBox(
            tr(
                "Distance along profile (m), using saved XY / CRS",
                "Distancia del perfil (m), usando XY / CRS guardados",
                "Distância do perfil (m), usando XY / SRC salvos",
            )
        )
        self.profile_distance.toggled.connect(
            lambda checked: self.profile_axis.setEnabled(not checked)
        )
        self.profile_distance.setToolTip(
            tr(
                "PyProj: CRS unit conversion and ellipsoidal horizontal distance. No vertical datum correction or 3-D path is inferred.",
                "PyProj: conversión de unidades del CRS y distancia horizontal elipsoidal. No se infiere corrección de datum vertical ni trayectoria 3D.",
                "PyProj: conversão de unidades do SRC e distância horizontal elipsoidal. Não se infere correção de datum vertical nem trajetória 3D.",
            )
        )
        profile_controls.addWidget(self.profile_distance, 2, 0, 1, 3)
        profile_controls.addWidget(
            QLabel(tr("Compare B", "Comparar B", "Comparar B")), 3, 0
        )
        profile_controls.addWidget(self.profile_compare, 3, 1)
        profile_controls.addWidget(self.profile_compare_mode, 3, 2)
        profile_layout.addLayout(profile_controls)
        self.profile_legend = QLabel()
        self.profile_legend.setWordWrap(True)
        self.profile_legend.setTextFormat(qt_enum(Qt, "TextFormat", "RichText"))
        profile_layout.addWidget(self.profile_legend)
        self.profile_plot = SurveyProfileWidget()
        self.profile_plot.empty_text = tr(
            "Choose a numeric channel and draw its profile.",
            "Elige un canal numérico y dibuja su perfil.",
            "Escolha um canal numérico e desenhe seu perfil.",
        )
        self.profile_plot.setAccessibleName(
            tr("Channel profile", "Perfil de canal", "Perfil de canal")
        )
        profile_layout.addWidget(self.profile_plot, 1)
        toolbar = QHBoxLayout()
        for caption, callback in (
            ("+", lambda: self.profile_plot.zoom(0.8)),
            ("−", lambda: self.profile_plot.zoom(1.25)),
            (tr("Fit", "Ajustar", "Ajustar"), self.profile_plot.fit),
            (
                tr("Save view PNG…", "Guardar vista PNG…", "Salvar vista PNG…"),
                self.export_profile_view,
            ),
        ):
            button = QPushButton(caption)
            button.clicked.connect(callback)
            toolbar.addWidget(button)
        profile_layout.addLayout(toolbar)
        self.profile_cursor = QLabel(
            tr(
                "Wheel: zoom · drag: pan · statistics refer to the full loaded selection",
                "Rueda: zoom · arrastrar: desplazar · estadísticas de toda la selección cargada",
                "Roda: zoom · arrastar: deslocar · estatísticas de toda a seleção carregada",
            )
        )
        self.profile_cursor.setWordWrap(True)
        self.profile_plot.positionChanged.connect(self.profile_cursor.setText)
        profile_layout.addWidget(self.profile_cursor)
        self.profile_statistics = QLabel(
            tr(
                "Display only. No channel values are changed.",
                "Solo visualización. No se modifica ningún valor.",
                "Apenas visualização. Nenhum valor é alterado.",
            )
        )
        self.profile_statistics.setWordWrap(True)
        profile_layout.addWidget(self.profile_statistics)
        self.profile_load.clicked.connect(self.load_profile)
        self.views.addTab(profile_page, tr("Profiles", "Perfiles", "Perfis"))
        self.status = QLabel(
            tr(
                "Immutable originals · versioned channels · PyArrow/Parquet + SQLite",
                "Originales inmutables · canales versionados · PyArrow/Parquet + SQLite",
                "Originais imutáveis · canais versionados · PyArrow/Parquet + SQLite",
            )
        )
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        from .task_history_widget import TaskHistoryWidget

        self.tasks = TaskHistoryWidget(tr, self)
        self.tasks.cancelRequested.connect(
            lambda: (
                self.worker.requestInterruption() if self.worker is not None else None
            )
        )
        layout.addWidget(self.tasks)
        saved = QSettings().value(KEY_WORKSPACE, "", type=str)
        if saved and (Path(saved) / "catalog.sqlite").is_file():
            try:
                self.set_project(saved)
            except Exception as error:
                self.status.setText(str(error))

    def set_project(self, path, create=False):
        self.store = SurveyStore(path, create=create)
        QSettings().setValue(KEY_WORKSPACE, str(self.store.root))
        self.path_label.setText(str(self.store.root))
        self.refresh()

    def show_processes(self):
        from .process_centre import ProcessCentre

        dialog = ProcessCentre(self)
        dialog.exec()
        dialog.deleteLater()

    def new_project(self):
        parent = QFileDialog.getExistingDirectory(
            self, tr("Parent folder", "Carpeta contenedora", "Pasta principal")
        )
        if not parent:
            return
        name, ok = QInputDialog.getText(
            self,
            tr("New project", "Nuevo proyecto", "Novo projeto"),
            tr("Folder name", "Nombre de carpeta", "Nome da pasta"),
        )
        if not ok or not name.strip():
            return
        if name in (".", "..") or any(c in name for c in '/\\:*?"<>|'):
            self.fail(
                tr(
                    "Invalid folder name",
                    "Nombre de carpeta inválido",
                    "Nome de pasta inválido",
                )
            )
            return
        try:
            self.set_project(Path(parent) / name, create=True)
        except Exception as error:
            self.fail(str(error))

    def open_project(self):
        path = QFileDialog.getExistingDirectory(
            self, tr("Project folder", "Carpeta de proyecto", "Pasta do projeto")
        )
        if path:
            try:
                self.set_project(path)
            except Exception as error:
                self.fail(str(error))

    def refresh(self):
        selected = set(self.selected_databases())
        self.databases_list.blockSignals(True)
        self.databases_list.clear()
        if self.store:
            for row in self.store.databases():
                item = QListWidgetItem(f"{row['name']} ({row['rows']:,})")
                item.setData(256, row["id"])
                self.databases_list.addItem(item)
                item.setSelected(row["id"] in selected)
            if not self.databases_list.selectedItems() and self.databases_list.count():
                self.databases_list.item(0).setSelected(True)
        self.databases_list.blockSignals(False)
        self.refresh_channels()

    def selected_databases(self):
        return [item.data(256) for item in self.databases_list.selectedItems()]

    def selected_channels(self):
        return [item.data(256) for item in self.channels_list.selectedItems()]

    def refresh_channels(self):
        selected = set(self.selected_channels())
        filter_name = self.filter_channel.currentData()
        choices = [
            (self.profile_compare, self.profile_compare.currentData()),
            (self.profile_channel, self.profile_channel.currentData()),
            (self.profile_axis, self.profile_axis.currentData()),
            (self.profile_group, self.profile_group.currentData()),
            (self.profile_sensor, self.profile_sensor.currentData()),
        ]
        self.channels_list.clear()
        self.filter_channel.clear()
        self.filter_channel.addItem("—", None)
        ids = self.selected_databases()
        changed = tuple(ids) != self._last_db_ids
        self._channel_info = {}
        for combo, _ in choices:
            combo.clear()
            if combo is self.profile_axis:
                combo.addItem(
                    tr(
                        "Selected sample", "Muestra seleccionada", "Amostra selecionada"
                    ),
                    None,
                )
            elif combo is not self.profile_channel:
                combo.addItem("—", None)
        if changed:
            self._last_db_ids = tuple(ids)
            self._page_context = None
            self._page_offset = 0
            self._page_has_next = False
            self.table.setRowCount(0)
            self.page_status.setText(
                tr(
                    "Select channels and load a page.",
                    "Selecciona canales y carga una página.",
                    "Selecione canais e carregue uma página.",
                )
            )
            self.profile_plot.clear()
            self.profile_legend.clear()
            self.profile_statistics.setText(
                tr(
                    "Select a channel to inspect.",
                    "Selecciona un canal para inspeccionar.",
                    "Selecione um canal para inspecionar.",
                )
            )
            self.page_first.setEnabled(False)
            self.page_previous.setEnabled(False)
            self.page_next.setEnabled(False)
            self.group_values.clear()
            self.sensor_values.clear()
            self.filter_values.clear()
            for value_choices in (self.group_choices, self.sensor_choices):
                value_choices.clear()
                value_choices.addItem(
                    tr("Choose value…", "Elegir valor…", "Escolher valor…"), None
                )
        if not ids or not self.store:
            return
        rows = self.store.channels(ids[0])
        common = {c["name"] for c in rows}
        for database in ids[1:]:
            common.intersection_update(c["name"] for c in self.store.channels(database))
        for row in rows:
            if row["name"] not in common:
                continue
            self._channel_info[row["name"]] = row
            suffix = (
                f" · {row['data_type']} · {row['unit']} · v{row['number']}"
                if len(ids) == 1
                else ""
            )
            item = QListWidgetItem(row["name"] + suffix)
            item.setData(256, row["name"])
            self.channels_list.addItem(item)
            item.setSelected(row["name"] in selected)
            self.filter_channel.addItem(row["name"], row["name"])
            for combo, _ in choices:
                combo.addItem(row["name"], row["name"])
        self.filter_channel.setCurrentIndex(
            max(0, self.filter_channel.findData(filter_name))
        )
        for combo, value in choices:
            combo.setCurrentIndex(max(0, combo.findData(value)))
        if changed and len(ids) == 1:
            metadata = json.loads(
                next(d for d in self.store.databases() if d["id"] == ids[0])["metadata"]
            )
            roles = metadata.get("channel_roles", {})
            by_id = {row["id"]: row["name"] for row in rows}
            for combo, role, aliases in (
                (self.profile_group, "line", ("line", "track", "transect", "traverse")),
                (self.profile_sensor, "sensor", ("sensor", "sensor_id", "sensor id")),
            ):
                suggested = by_id.get(roles.get(role)) or next(
                    (name for name in common if name.lower() in aliases), None
                )
                if suggested:
                    combo.setCurrentIndex(max(0, combo.findData(suggested)))

    def require_selection(self, channels=True, single=False):
        ids, names = self.selected_databases(), self.selected_channels()
        if (
            not self.store
            or not ids
            or (channels and not names)
            or (single and len(ids) != 1)
        ):
            self.fail(
                tr(
                    "Select a project, database(s) and channel(s); this action may require one database.",
                    "Selecciona un proyecto, bases y canales; esta acción puede requerir una sola base.",
                    "Selecione um projeto, bancos e canais; esta ação pode exigir apenas um banco.",
                )
            )
            return None
        return ids, names

    def filters(self):
        result = {}
        for combo, entry in (
            (self.filter_channel, self.filter_values),
            (self.profile_group, self.group_values),
            (self.profile_sensor, self.sensor_values),
        ):
            key = combo.currentData()
            values = [
                value
                for value in next(
                    csv.reader([entry.text().strip()], skipinitialspace=True), []
                )
                if value
            ]
            if key and values:
                result[key] = (
                    [v for v in values if v in result[key]] if key in result else values
                )
        return result

    def update_filter_caption(self, *_):
        active = len(self.filters())
        self.filter_toggle.setText(
            tr(
                "View / export filters · {n} active",
                "Filtros de vista / exportación · {n} activos",
                "Filtros de visualização / exportação · {n} ativos",
            ).format(n=active)
        )

    def load_group_values(self):
        selected = self.require_selection(channels=False, single=True)
        if not selected:
            return
        names = [
            name
            for name in (
                self.profile_group.currentData(),
                self.profile_sensor.currentData(),
            )
            if name
        ]
        if not names:
            self.fail(
                tr(
                    "Choose transect/sensor columns first.",
                    "Primero elige los canales de transecta/sensor.",
                    "Primeiro escolha os canais de transecto/sensor.",
                )
            )
            return
        store, database = self.store, selected[0][0]

        def run(cancel, progress):
            return survey_group_values(
                store, database, names, cancel=cancel, progress=progress
            )

        def display(result):
            for source, choices in (
                (self.profile_group, self.group_choices),
                (self.profile_sensor, self.sensor_choices),
            ):
                choices.blockSignals(True)
                choices.setProperty("source_channel", source.currentData())
                choices.clear()
                choices.addItem(
                    tr("Choose value…", "Elegir valor…", "Escolher valor…"), None
                )
                for value in result["values"].get(source.currentData(), []):
                    choices.addItem(value, value)
                choices.blockSignals(False)
                choices.setEnabled(choices.count() > 1)
            message = tr(
                "Read {rows:,} rows · selectors loaded; blank fields include all values",
                "Leídas {rows:,} filas · selectores cargados; campos vacíos incluyen todos los valores",
                "Lidas {rows:,} linhas · seletores carregados; campos vazios incluem todos os valores",
            ).format(rows=result["rows"])
            if any(result["truncated"].values()):
                message += " · " + tr(
                    "List limited to 2000 values per channel; manual values still accepted",
                    "Lista limitada a 2000 valores por canal; se aceptan valores manuales",
                    "Lista limitada a 2000 valores por canal; valores manuais continuam aceitos",
                )
            self.status.setText(message)

        self.start(
            run,
            display,
            tr(
                "Discover transects / sensors",
                "Descubrir transectas / sensores",
                "Descobrir transectos / sensores",
            ),
        )

    def start(self, operation, success=None, title=None):
        if self.worker is not None:
            return
        self._task_state = "running"
        self.tasks.begin(
            title or tr("Database operation", "Operación de base", "Operação de banco")
        )
        self.controls.setEnabled(False)
        self.progress_dialog = QProgressDialog(
            tr("Working…", "Procesando…", "Processando…"),
            tr("Cancel", "Cancelar", "Cancelar"),
            0,
            0,
            self,
        )
        self.worker = StoreWorker(operation, self)
        self.progress_dialog.canceled.connect(self.worker.requestInterruption)
        self.worker.progress.connect(
            lambda n: self.progress_dialog.setLabelText(
                tr("Rows: ", "Filas: ", "Linhas: ") + n
            )
        )
        self.worker.completed.connect(lambda result: self.completed(result, success))
        self.worker.failed.connect(self.task_failed)
        self.worker.progress.connect(self.tasks.progress)
        self.worker.cancelled.connect(lambda: setattr(self, "_task_state", "cancelled"))
        self.worker.cancelled.connect(
            lambda: self.status.setText(
                tr(
                    "Cancelled.",
                    "Cancelado.",
                    "Cancelado.",
                )
            )
        )
        self.worker.finished.connect(self.finished)
        self.progress_dialog.show()
        self.worker.start()

    def completed(self, result, callback):
        self._task_state = "completed"
        if callback is None:
            self.status.setText(str(result))
        self.refresh()
        if callback:
            try:
                callback(result)
            except Exception as error:
                self._task_state = "failed"
                self.fail(str(error))

    def task_failed(self, message):
        self._task_state = "failed"
        self.fail(message)

    def finished(self):
        self.tasks.finish(
            self._task_state if self._task_state != "running" else "failed",
            self.status.text(),
        )
        self.progress_dialog.close()
        self.progress_dialog.deleteLater()
        self.worker.deleteLater()
        self.worker = None
        self.controls.setEnabled(True)
        self.refresh()
        if self._dispose:
            if not getattr(self, "_tw_dispose_pending", 0):
                self.deleteLater()
        elif self._close_requested:
            self.close()

    def fail(self, message):
        self.status.setText(message)
        if not self._dispose:
            QMessageBox.warning(self, "TerraWorkbench", message)

    def closeEvent(self, event):
        if self.worker is not None:
            self._close_requested = True
            self.worker.requestInterruption()
            event.ignore()
        else:
            event.accept()

    def dispose(self):
        self._dispose = True
        from ..qgis_plugin.qgis_compat import dispose_with_workers

        dispose_with_workers(self)

    def import_files(self):
        if not self.store:
            self.fail(
                tr(
                    "Create or open a project first.",
                    "Primero crea o abre un proyecto.",
                    "Crie ou abra um projeto primeiro.",
                )
            )
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            tr("Import observations", "Importar observaciones", "Importar observações"),
            "",
            "Survey text / Parquet (*.csv *.tsv *.txt *.asc *.dat *.xyz *.parquet);;All files (*)",
        )
        if not paths:
            return
        from .text_import_dialog import TextImportDialog

        text_options = {}
        for path in paths:
            if Path(path).suffix.lower() != ".parquet":
                wizard = TextImportDialog(path, self)
                accepted = wizard.exec() == qt_enum(QDialog, "DialogCode", "Accepted")
                if not accepted:
                    wizard.deleteLater()
                    return
                text_options[path] = wizard.options
                wizard.deleteLater()
        store = self.store

        def run(cancel, progress):
            results = []
            used_names = {row["name"] for row in store.databases()}
            for path in paths:
                try:
                    base = Path(path).stem
                    name, suffix = base, 2
                    while name in used_names:
                        name = f"{base} ({suffix})"
                        suffix += 1
                    results.append(
                        store.import_file(
                            path,
                            name=name,
                            canceled=cancel,
                            progress=progress,
                            text_options=text_options.get(path),
                        )
                    )
                    used_names.add(name)
                except Exception as error:
                    raise RuntimeError(
                        f"{len(results)}/{len(paths)} imported; {Path(path).name}: {error}"
                    ) from error
            return tr(
                "Imported databases: ", "Bases importadas: ", "Bancos importados: "
            ) + str(len(results))

        self.start(run)

    def preview(self):
        self.load_page(0)

    def load_page(self, offset=0):
        selection = self.require_selection(single=True)
        if not selection:
            return
        ids, names = selection
        store, filters = self.store, self.filters()
        limit = self.page_size.currentData()
        context = (
            str(store.root),
            ids[0],
            tuple(names),
            repr(sorted(filters.items())),
            limit,
            tuple(self._channel_info[name]["version_id"] for name in names),
        )
        if context != self._page_context:
            offset = 0

        def run(cancel, progress):
            return read_survey_page(
                store,
                ids[0],
                names,
                offset=offset,
                limit=limit,
                filters=filters,
                cancel=cancel,
                progress=progress,
            )

        def display(result):
            data = result["data"]
            self.table.clear()
            self.table.setColumnCount(len(names))
            self.table.setRowCount(result["rows"])
            self.table.setHorizontalHeaderLabels(names)
            # Scientific channel names carry processing history. Keep them
            # readable and allow horizontal scrolling instead of clipping them.
            metrics = self.table.fontMetrics()
            for column, name in enumerate(names):
                self.table.setColumnWidth(column, max(110, metrics.horizontalAdvance(name) + 28))
            self.table.setVerticalHeaderLabels(
                [str(offset + i + 1) for i in range(result["rows"])]
            )
            for col, name in enumerate(names):
                for row, value in enumerate(data[name]):
                    self.table.setItem(
                        row, col, QTableWidgetItem("" if value is None else str(value))
                    )
            self._page_offset, self._page_has_next, self._page_context = (
                offset,
                result["has_next"],
                context,
            )
            self.page_first.setEnabled(offset > 0)
            self.page_previous.setEnabled(offset > 0)
            self.page_next.setEnabled(result["has_next"])
            total = next(d["rows"] for d in store.databases() if d["id"] == ids[0])
            message = tr(
                "Selection rows {first}–{last} · database: {total:,} rows · read-only",
                "Filas {first}–{last} de la selección · base: {total:,} filas · solo lectura",
                "Linhas {first}–{last} da seleção · banco: {total:,} linhas · somente leitura",
            ).format(
                first=offset + 1 if result["rows"] else 0,
                last=offset + result["rows"] if result["rows"] else 0,
                total=total,
            )
            self.page_status.setText(message)
            self.status.setText(message)
            self.views.setCurrentIndex(0)

        self.start(
            run,
            display,
            tr(
                "Load table page", "Cargar página de tabla", "Carregar página da tabela"
            ),
        )

    def load_profile(self):
        selection = self.require_selection(channels=False, single=True)
        if not selection or not self.profile_channel.currentData():
            return
        database = selection[0][0]
        store, filters = self.store, self.filters()
        channel, axis = (
            self.profile_channel.currentData(),
            self.profile_axis.currentData(),
        )
        group, sensor = (
            self.profile_group.currentData(),
            self.profile_sensor.currentData(),
        )
        info = self._channel_info.copy()
        comparison_channel = self.profile_compare.currentData()
        comparison_mode = self.profile_compare_mode.currentData()
        distance_columns, source_crs = None, None
        if self.profile_distance.isChecked():
            metadata = json.loads(
                next(
                    row["metadata"]
                    for row in store.databases()
                    if row["id"] == database
                )
            )
            geometry = metadata.get("geometry", {})
            by_id = {row["id"]: row["name"] for row in info.values()}
            distance_columns = [
                by_id.get(geometry.get("x_channel_id")),
                by_id.get(geometry.get("y_channel_id")),
            ]
            source_crs = geometry.get("crs")
            if not all(distance_columns) or not source_crs:
                self.fail(
                    tr(
                        "Configure database X/Y and CRS before using physical distance.",
                        "Configura X/Y y CRS de la base antes de usar distancia física.",
                        "Configure X/Y e SRC do banco antes de usar distância física.",
                    )
                )
                return
            axis = None

        def run(cancel, progress):
            if comparison_channel:
                return compare_survey_profiles(
                    store,
                    database,
                    channel,
                    comparison_channel,
                    axis=axis,
                    group=group,
                    sensor=sensor,
                    distance_columns=distance_columns,
                    source_crs=source_crs,
                    filters=filters,
                    cancel=cancel,
                    progress=progress,
                )
            return read_survey_profile(
                store,
                database,
                channel,
                axis=axis,
                group=group,
                sensor=sensor,
                distance_columns=distance_columns,
                source_crs=source_crs,
                filters=filters,
                cancel=cancel,
                progress=progress,
            )

        def display(result):
            comparison = result if comparison_channel else None
            if comparison:
                if comparison_mode == "difference":
                    result = comparison["difference"]
                else:
                    result = dict(comparison["primary"])
                    result["segments"] = [
                        {**segment, "label": f"{name} · {segment['label']}"}
                        for name, field in (
                            (channel, "primary"),
                            (comparison_channel, "secondary"),
                        )
                        for segment in comparison[field]["segments"]
                    ]
                    result["display_points"] = sum(
                        len(s["x"]) for s in result["segments"]
                    )
                    result["reduced"] = (
                        comparison["primary"]["reduced"]
                        or comparison["secondary"]["reduced"]
                    )

            def label(name):
                unit = info.get(name, {}).get("unit", "")
                return f"{name} [{unit}]" if unit else name

            self.profile_plot.set_profile(
                result,
                tr(
                    "Distance within continuous segment (m)",
                    "Distancia por tramo continuo (m)",
                    "Distância por trecho contínuo (m)",
                )
                if distance_columns
                else label(axis)
                if axis
                else tr(
                    "Selected sample", "Muestra seleccionada", "Amostra selecionada"
                ),
                f"{comparison_channel} − {channel} [{comparison['unit']}]"
                if comparison and comparison_mode == "difference"
                else f"{channel} / {comparison_channel} [{comparison['unit']}]"
                if comparison
                else label(channel),
            )
            colors = self.profile_plot.series_colors()
            self.profile_legend.setText(
                " &nbsp; ".join(
                    f'<span style="color:{color.name()}">■ {escape(name or channel)}</span>'
                    for name, color in list(colors.items())[:8]
                )
                + (f" · +{len(colors) - 8}" if len(colors) > 8 else "")
            )

            def number(key):
                return "—" if result[key] is None else f"{result[key]:.6g}"

            message = tr(
                "{valid:,}/{rows:,} valid · min {minimum} · max {maximum} · mean {mean} · SD {std}\n{shown:,} display points · gaps preserved · source values unchanged",
                "{valid:,}/{rows:,} válidas · mín. {minimum} · máx. {maximum} · media {mean} · desv. {std}\n{shown:,} puntos de visualización · huecos conservados · valores originales sin cambios",
                "{valid:,}/{rows:,} válidas · mín. {minimum} · máx. {maximum} · média {mean} · desvio {std}\n{shown:,} pontos de visualização · lacunas preservadas · valores originais inalterados",
            ).format(
                valid=result["valid_rows"],
                rows=result["rows"],
                shown=result["display_points"],
                **{key: number(key) for key in ("minimum", "maximum", "mean", "std")},
            )
            if result["reduced"]:
                message += "\n" + tr(
                    "Reduced min/max envelope; statistics use the complete valid selection.",
                    "Envolvente mín./máx. reducida; las estadísticas usan toda la selección válida.",
                    "Envelope mín./máx. reduzido; as estatísticas usam toda a seleção válida.",
                )
            if comparison:
                a, b, delta = (
                    comparison["primary"],
                    comparison["secondary"],
                    comparison["difference"],
                )

                def mean_text(record):
                    return "—" if record["mean"] is None else f"{record['mean']:.6g}"

                message += "\n" + tr(
                    "A: {a} valid, mean {am} · B: {b} valid, mean {bm} · B−A: {d} paired, mean {dm}; same database row positions, no interpolation",
                    "A: {a} válidas, media {am} · B: {b} válidas, media {bm} · B−A: {d} pares, media {dm}; mismas filas de la base, sin interpolación",
                    "A: {a} válidas, média {am} · B: {b} válidas, média {bm} · B−A: {d} pares, média {dm}; mesmas linhas do banco, sem interpolação",
                ).format(
                    a=a["valid_rows"],
                    am=mean_text(a),
                    b=b["valid_rows"],
                    bm=mean_text(b),
                    d=delta["valid_rows"],
                    dm=mean_text(delta),
                )
                if comparison_mode == "overlay":
                    message = (
                        tr(
                            "Primary A statistics · ",
                            "Estadísticas del canal A · ",
                            "Estatísticas do canal A · ",
                        )
                        + message
                    )
            self.profile_statistics.setText(message)
            self.status.setText(
                tr(
                    "Read-only profile loaded",
                    "Perfil de solo lectura cargado",
                    "Perfil somente leitura carregado",
                )
            )
            self.views.setCurrentIndex(1)

        self.start(
            run,
            display,
            tr(
                "Load channel profile",
                "Cargar perfil de canal",
                "Carregar perfil de canal",
            ),
        )

    def export_profile_view(self):
        if not self.profile_plot.profile:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr(
                "Save displayed profile",
                "Guardar perfil mostrado",
                "Salvar perfil exibido",
            ),
            "profile.png",
            "PNG (*.png)",
        )
        if path and not self.profile_plot.grab().save(path, "PNG"):
            self.fail(
                tr(
                    "Could not save the profile view.",
                    "No se pudo guardar la vista del perfil.",
                    "Não foi possível salvar a vista do perfil.",
                )
            )

    def calculate(self):
        selection = self.require_selection(channels=False)
        if not selection:
            return
        ids, _ = selection
        name, ok = QInputDialog.getText(
            self,
            tr("Derived channel", "Canal derivado", "Canal derivado"),
            tr(
                "Output name (existing derived name creates a version)",
                "Nombre de salida (si ya es derivado crea una versión)",
                "Nome de saída (se já for derivado cria uma versão)",
            ),
        )
        if not ok or not name.strip():
            return
        expression, ok = QInputDialog.getText(
            self,
            tr("Formula", "Fórmula", "Fórmula"),
            'c("channel") * 2 + 1; abs, sqrt, log10\n'
            + tr(
                "Full database; preview filter is not applied.",
                "Base completa; no aplica el filtro de vista previa.",
                "Banco completo; não aplica o filtro de prévia.",
            ),
        )
        if not ok:
            return
        unit, ok = QInputDialog.getText(
            self,
            tr("Units", "Unidades", "Unidades"),
            tr("Output units", "Unidades de salida", "Unidades de saída"),
        )
        if not ok:
            return
        store = self.store

        def run(cancel, progress):
            results = []
            for database in ids:
                try:
                    results.append(
                        store.derive(database, name, expression, unit, cancel, progress)
                    )
                except Exception as error:
                    raise RuntimeError(
                        f"{len(results)}/{len(ids)} completed; {database}: {error}"
                    ) from error
            return results

        self.start(run)

    def duplicate(self):
        selection = self.require_selection(single=True)
        if not selection or len(selection[1]) != 1:
            return
        ids, names = selection
        name, ok = QInputDialog.getText(
            self,
            tr("Duplicate channel", "Duplicar canal", "Duplicar canal"),
            tr("New name", "Nuevo nombre", "Novo nome"),
        )
        if ok:
            try:
                self.store.duplicate_channel(ids[0], names[0], name)
                self.refresh_channels()
            except Exception as error:
                self.fail(str(error))

    def rename(self):
        selection = self.require_selection(single=True)
        if not selection or len(selection[1]) != 1:
            return
        ids, names = selection
        name, ok = QInputDialog.getText(
            self,
            tr("Rename channel", "Renombrar canal", "Renomear canal"),
            tr("Name", "Nombre", "Nome"),
            text=names[0],
        )
        if not ok:
            return
        current = next(c for c in self.store.channels(ids[0]) if c["name"] == names[0])
        unit, ok = QInputDialog.getText(
            self,
            tr("Units", "Unidades", "Unidades"),
            tr("Units", "Unidades", "Unidades"),
            text=current["unit"],
        )
        if ok:
            try:
                self.store.rename_channel(ids[0], names[0], name, unit)
                self.refresh_channels()
            except Exception as error:
                self.fail(str(error))

    def export(self):
        selection = self.require_selection()
        if not selection:
            return
        ids, names = selection
        store, filters = self.store, self.filters()

        def run(cancel, progress):
            outputs = []
            for database in ids:
                path = store.root / "results" / f"{database}_{uuid.uuid4().hex[:8]}.csv"
                try:
                    store.export_csv(database, names, path, filters, cancel, progress)
                    outputs.append(str(path))
                except Exception as error:
                    raise RuntimeError(f"Exported {outputs}; {error}") from error
            return outputs

        self.start(run)

    def channel_pipeline(self):
        selection = self.require_selection(single=True)
        if not selection:
            return
        ids, names = selection
        if len(names) != 1:
            self.fail(
                tr(
                    "Select one channel to inspect its pipeline.",
                    "Selecciona un canal para ver su pipeline.",
                    "Selecione um canal para ver seu pipeline.",
                )
            )
            return
        from .channel_pipeline_dialog import ChannelPipelineDialog

        try:
            dialog = ChannelPipelineDialog(
                self.store.channel_pipeline(ids[0], names[0]), self
            )
            dialog.exec()
            requested = dialog.requested_step
            dialog.deleteLater()
            if requested is not None:
                self.reuse_channel_step(ids[0], requested)
        except Exception as error:
            self.fail(str(error))

    def reuse_channel_step(self, database, node):
        from ..terraworkbench_core.survey_recipes import prepare_channel_step
        from ..compat.survey_store import Formula

        plan = prepare_channel_step(self.store, database, node)
        if plan["operation"] == "channel_filter":
            self.filter_signal(template=(node, plan))
            return
        expression, ok = QInputDialog.getText(
            self,
            tr(
                "Edit formula step",
                "Editar etapa de fórmula",
                "Editar etapa de fórmula",
            ),
            tr(
                "Formula · reviewed current input versions only",
                "Fórmula · solo versiones de entrada actuales revisadas",
                "Fórmula · apenas versões de entrada atuais revisadas",
            ),
            text=plan["expression"],
        )
        if not ok:
            return
        existing = {row["name"] for row in self.store.channels(database)}
        stem = node["name"][:175] + "__rerun"
        suggested, index = stem, 2
        while suggested in existing:
            suggested, index = f"{stem}_{index}", index + 1
        output, ok = QInputDialog.getText(
            self,
            tr("New channel", "Canal nuevo", "Novo canal"),
            tr(
                "New output name; originals stay unchanged",
                "Nombre de salida nuevo; originales sin cambios",
                "Novo nome de saída; originais inalterados",
            ),
            text=suggested,
        )
        if not ok:
            return
        if output.strip() in existing or not output.strip():
            raise ValueError(
                tr(
                    "Choose a new channel name.",
                    "Elige un nombre de canal nuevo.",
                    "Escolha um novo nome de canal.",
                )
            )
        unit, ok = QInputDialog.getText(
            self,
            tr("Output unit", "Unidad de salida", "Unidade de saída"),
            tr(
                "Confirm output unit",
                "Confirma la unidad de salida",
                "Confirme a unidade de saída",
            ),
            text=plan["unit"],
        )
        if not ok:
            return
        prepare_channel_step(self.store, database, node)
        names = Formula(expression).channels
        current = {
            row["name"]: row["version_id"] for row in self.store.channels(database)
        }
        expected = {name: current[name] for name in names}
        store = self.store
        self.start(
            lambda cancel, progress: store.derive(
                database,
                output.strip(),
                expression,
                unit,
                cancel,
                progress,
                expected_versions=expected,
                reused_from=plan["source_version"],
                new_channel_only=True,
            ),
            title=tr(
                "Run edited formula as new channel",
                "Ejecutar fórmula editada como canal nuevo",
                "Executar fórmula editada como novo canal",
            ),
        )

    def filter_signal(self, template=None):
        selection = self.require_selection(channels=False, single=True)
        if not selection:
            return
        from .channel_filter_dialog import ChannelFilterDialog

        ids, names = selection
        dialog = ChannelFilterDialog(
            self.store,
            ids[0],
            template[1]["channel"] if template else names[0] if names else "",
            self,
        )
        if template:
            from ..compat.channel_filters import ChannelFilterOptions

            try:
                dialog.apply_options(
                    template[1]["channel"],
                    ChannelFilterOptions(**template[1]["parameters"]),
                )
            except Exception:
                dialog.deleteLater()
                raise
        if dialog.exec() == qt_enum(QDialog, "DialogCode", "Accepted"):
            store, options = self.store, dialog.options
            source, output = dialog.input_name, dialog.output_name
            if template:
                from ..terraworkbench_core.survey_recipes import prepare_channel_step

                prepare_channel_step(store, ids[0], template[0])
            current = {row["name"]: row["version_id"] for row in store.channels(ids[0])}
            expected = {
                name: current[name]
                for name in (source, options.axis, options.group, options.sensor)
                if name
            }

            def run(cancel, progress):
                return store.filter_channel(
                    ids[0],
                    source,
                    output,
                    options,
                    cancel,
                    progress,
                    expected_versions=expected,
                    reused_from=template[1]["source_version"] if template else None,
                )

            def display(result):
                for index in range(self.channels_list.count()):
                    item = self.channels_list.item(index)
                    item.setSelected(item.data(256) == output)
                self.status.setText(
                    tr(
                        "Created {output}: {rows} rows; {output_null_rows} null outputs; {short_segments} short segments; {spikes_replaced} spikes replaced. Open Channel pipeline to inspect.",
                        "Creado {output}: {rows} filas; {output_null_rows} salidas nulas; {short_segments} tramos cortos; {spikes_replaced} picos reemplazados. Abre Pipeline del canal para inspeccionar.",
                        "Criado {output}: {rows} linhas; {output_null_rows} saídas nulas; {short_segments} trechos curtos; {spikes_replaced} picos substituídos. Abra Pipeline do canal para inspecionar.",
                    ).format(**result)
                )

            self.start(run, display)
        dialog.deleteLater()

    def coordinates(self):
        selection = self.require_selection(channels=False, single=True)
        if not selection:
            return
        from .survey_coordinates_dialog import (
            SurveyCoordinatesDialog,
            coordinate_operation,
        )

        database_id = selection[0][0]
        dialog = SurveyCoordinatesDialog(self.store, database_id, self)
        if dialog.exec() == qt_enum(QDialog, "DialogCode", "Accepted"):
            request = dialog.request
            if "target" in request:
                self.start(
                    coordinate_operation(
                        self.store, database_id, request, dialog.context
                    )
                )
            else:
                try:
                    self.store.configure_geometry(
                        database_id, request["x"], request["y"], request["source"]
                    )
                    self.status.setText(
                        tr(
                            "CRS assigned; coordinate values unchanged.",
                            "CRS asignado; valores de coordenadas sin cambios.",
                            "SRC atribuído; valores das coordenadas sem alterações.",
                        )
                    )
                except Exception as error:
                    self.fail(str(error))
        dialog.deleteLater()

    def to_qgis(self):
        selection = self.require_selection(single=True)
        if not selection:
            return
        ids, names = selection
        channel_rows = self.store.channels(ids[0])
        fields = [row["name"] for row in channel_rows]
        channel_names = {row["id"]: row["name"] for row in channel_rows}
        metadata = json.loads(
            next(row for row in self.store.databases() if row["id"] == ids[0])[
                "metadata"
            ]
        )
        roles = metadata.get("channel_roles", {})
        geometry = metadata.get("geometry", {})
        configured_axes = [
            channel_names.get(geometry.get(axis + "_channel_id")) for axis in ("x", "y")
        ]
        configured_crs = QgsCoordinateReferenceSystem(geometry.get("crs", ""))
        use_configured = all(configured_axes) and configured_crs.isValid()
        axes = []
        for label in ("X", "Y"):
            suggested = channel_names.get(
                geometry.get(label.lower() + "_channel_id", roles.get(label.lower())),
                "",
            )
            index = fields.index(suggested) if suggested in fields else 0
            field, ok = (
                (suggested, True)
                if use_configured
                else QInputDialog.getItem(self, "QGIS", label, fields, index, False)
            )
            if not ok:
                return
            axes.append(field)
        if axes[0] == axes[1]:
            self.fail("X and Y must be different channels.")
            return
        crs_text, ok = (
            (geometry["crs"], True)
            if use_configured
            else QInputDialog.getText(
                self,
                "QGIS",
                "CRS (EPSG:...) — " + tr("required", "obligatorio", "obrigatório"),
                text=geometry.get("crs", ""),
            )
        )
        crs = QgsCoordinateReferenceSystem(crs_text)
        if not ok:
            return
        if not crs.isValid():
            self.fail(tr("Invalid CRS", "CRS inválido", "SRC inválido"))
            return
        store, filters = self.store, self.filters()
        try:
            store.configure_geometry(
                ids[0], axes[0], axes[1], crs.authid() or crs.toWkt()
            )
        except Exception as error:
            self.fail(str(error))
            return
        path = store.root / "results" / f"points_{uuid.uuid4().hex}.csv"
        columns = list(dict.fromkeys([*axes, *names]))

        def run(cancel, progress):
            return store.export_csv(ids[0], columns, path, filters, cancel, progress)

        def load(result):
            url, query = QUrl.fromLocalFile(str(path)), QUrlQuery()
            for key, value in {
                "type": "csv",
                "delimiter": ",",
                "xField": axes[0],
                "yField": axes[1],
                "crs": crs.authid() or crs.toWkt(),
                "detectTypes": "yes",
                "decimalPoint": ".",
            }.items():
                query.addQueryItem(key, value)
            url.setQuery(query)
            layer = QgsVectorLayer(url.toString(), path.stem, "delimitedtext")
            if not layer.isValid():
                raise ValueError("QGIS could not load the exported points.")
            if layer.featureCount() != result:
                raise ValueError(
                    "Some exported rows have invalid coordinates. Inspect the CSV before gridding; the incomplete layer was not added."
                )
            layer.setCustomProperty("TerraWorkbench/surveyDatabase", ids[0])
            QgsProject.instance().addMapLayer(layer)

        self.start(run, load)

    def history(self):
        selection = self.require_selection(channels=False, single=True)
        if selection:
            rows = self.store.history(selection[0][0])
            dialog = QMessageBox(self)
            dialog.setWindowTitle(tr("History", "Historial", "Histórico"))
            dialog.setText(
                tr(
                    "Operations recorded: ",
                    "Operaciones registradas: ",
                    "Operações registradas: ",
                )
                + str(len(rows))
            )
            dialog.setDetailedText(json.dumps(rows, ensure_ascii=False, indent=2))
            dialog.exec()
