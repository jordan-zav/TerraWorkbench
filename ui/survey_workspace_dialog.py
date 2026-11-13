"""Survey project manager. Long I/O runs on a cancellable worker thread."""

from pathlib import Path
import json
import csv
import uuid
from html import escape
from threading import Event
import weakref

from qgis.PyQt.QtCore import QSettings, QThread, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
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
    QTableView,
    QHeaderView,
    QVBoxLayout,
    QWidget,
    QSplitter,
    QTabWidget,
    QMenu,
)
from qgis.core import QgsProject, QgsCoordinateReferenceSystem

from ..qgis_plugin.qgis_compat import qt_enum
from ..compat.survey_store import SurveyStore
from ..terraworkbench_core.survey_explorer import (
    read_survey_page,
    read_survey_profile,
    survey_group_values,
    compare_survey_profiles,
)
from .survey_profile_widget import SurveyProfileWidget
from .survey_sheet import (
    SurveySheetModel, background, channel_description, channel_tooltip, line_spans, tr,
)
from qgis.PyQt.QtCore import Qt

KEY_WORKSPACE = "TerraWorkbench/surveyWorkspace"


def notify_survey_database(iface, root, database_id, name, owner):
    if iface is None:
        return
    message_bar = iface.messageBar()
    widget = message_bar.createMessage("TerraWorkbench", name)
    button = QPushButton(widget)
    widget.setWidget(button)
    notices = owner.__dict__.setdefault("_survey_notices", {})
    notices[id(widget)] = widget, button, name, message_bar
    widget.destroyed.connect(lambda _object=None, key=id(widget): notices.pop(key, None))
    translate_survey_notices(owner)
    reference = weakref.ref(owner)

    def open_database():
        target = reference()
        if target is None or getattr(target, "_tw_disposing", False):
            return
        if isinstance(target, SurveyWorkspaceDialog):
            target._close_requested = False
            target.select_database(root, database_id)
            target.show()
            target.raise_()
        else:
            target.workspaceRequested.emit(str(root), database_id)
        message_bar.popWidget(widget)

    button.clicked.connect(open_database)
    widget.setDuration(0)
    message_bar.pushItem(widget)


def translate_survey_notices(owner):
    for widget, button, name, _bar in getattr(owner, "_survey_notices", {}).values():
        widget.setText(tr("Survey imported", "Levantamiento importado", "Levantamento importado") + f" · {name}")
        button.setText(tr("Open database", "Abrir base de datos", "Abrir banco de dados"))


def close_survey_notices(owner):
    for widget, _button, _name, bar in tuple(getattr(owner, "_survey_notices", {}).values()):
        bar.popWidget(widget)


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
    def __init__(self, parent=None, *, iface=None):
        super().__init__(parent)
        self._translations = []
        self._results = {}
        self._profile_axis_text = None
        self._bind_text(
            self.setWindowTitle,
            "Survey databases",
            "Bases de levantamientos",
            "Bancos de levantamentos",
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
        self._sheet_key = None
        self._sheet_columns = []
        self._sheet_channel = None
        self._sheet_row = None
        self._lines = {}
        self._index_cancel = Event()
        self._page_generation = 0
        self._profile_generation = 0
        self._auto_profile = False
        self._show_all_requested = False
        self.iface = iface
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
            button = self._translated_widget(QPushButton, *labels)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        self.path_label = self._result_label(
            "Choose a working folder",
            "Elige una carpeta de trabajo",
            "Escolha uma pasta de trabalho",
        )
        self.path_label.setWordWrap(True)
        processes = self._translated_widget(
            QPushButton,
            "All geophysical processes…",
            "Todos los procesos geofísicos…",
            "Todos os processos geofísicos…",
        )
        processes.clicked.connect(self.show_processes)
        buttons.addWidget(processes)
        body.addWidget(self.path_label)
        splitter = QSplitter(qt_enum(Qt, "Orientation", "Horizontal"))
        body.addWidget(splitter, 1)
        sidebar = QWidget()
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 0, 6, 0)
        side.addWidget(self._translated_widget(QLabel, "Databases", "Bases", "Bancos"))
        hint = self._translated_widget(
            QLabel,
            "Select databases to see their common channels.",
            "Selecciona bases para ver sus canales comunes.",
            "Selecione bancos para ver seus canais comuns.",
        )
        hint.setWordWrap(True)
        side.addWidget(hint)
        splitter.addWidget(sidebar)
        viewer = QWidget()
        view = QVBoxLayout(viewer)
        view.setContentsMargins(6, 0, 0, 0)
        splitter.addWidget(viewer)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([275, 825])
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
            self._translated_widget(
                QLabel,
                "Channels · units · version",
                "Canales · unidades · versión",
                "Canais · unidades · versão",
            )
        )
        side.addWidget(self.channels_list, 2)
        filtering = QHBoxLayout()
        self.filter_toggle = self._translated_widget(
            QPushButton,
            "View / export filters…",
            "Filtros de vista / exportación…",
            "Filtros de visualização / exportação…",
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
            self._translated_widget(
                QLabel,
                "Additional view/export filter",
                "Filtro adicional de vista/exportación",
                "Filtro adicional de visualização/exportação",
            )
        )
        self.filter_channel = QComboBox()
        self.filter_values = QLineEdit()
        self._bind_text(
            self.filter_values.setPlaceholderText,
            "Values separated by commas",
            "Valores separados por comas",
            "Valores separados por vírgulas",
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
            self._translated_option(
                choices, None, "Choose value…", "Elegir valor…", "Escolher valor…"
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
        self._bind_text(
            self.group_values.setPlaceholderText,
            "All / comma-separated values",
            "Todas / valores separados por comas",
            "Todos / valores separados por vírgulas",
        )
        self._bind_text(
            self.sensor_values.setPlaceholderText,
            "All / comma-separated values",
            "Todos / valores separados por comas",
            "Todos / valores separados por vírgulas",
        )
        for row, (label, combo, values) in enumerate(
            (
                (
                    ("Transect channel", "Canal de transecta", "Canal de transecto"),
                    self.profile_group,
                    self.group_values,
                ),
                (
                    ("Sensor channel", "Canal de sensor", "Canal de sensor"),
                    self.profile_sensor,
                    self.sensor_values,
                ),
            )
        ):
            grouping.addWidget(self._translated_widget(QLabel, *label), row, 0)
            grouping.addWidget(combo, row, 1)
            grouping.addWidget(values, row, 2)
        grouping.setColumnStretch(2, 1)
        grouping.addWidget(self.group_choices, 0, 3)
        grouping.addWidget(self.sensor_choices, 1, 3)
        self.discover_groups = self._translated_widget(
            QPushButton,
            "Find transects / sensors",
            "Buscar transectas / sensores",
            "Buscar transectos / sensores",
        )
        self.discover_groups.clicked.connect(self.load_group_values)
        grouping.addWidget(self.discover_groups, 2, 1, 1, 3)
        filter_layout.addLayout(grouping)
        for entry in (self.filter_values, self.group_values, self.sensor_values):
            entry.textChanged.connect(self.update_filter_caption)
        self.actions_button = self._translated_widget(
            QPushButton, "Channel actions…", "Acciones de canales…", "Ações de canais…"
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
                    (
                        "Add survey to map…",
                        "Añadir levantamiento al mapa…",
                        "Adicionar levantamento ao mapa…",
                    ),
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
            action = menu.addAction("")
            self._bind_text(action.setText, *labels)
            action.triggered.connect(lambda checked=False, fn=callback: fn())
        self.views = QTabWidget()
        view.addWidget(self.views, 1)
        table_page = QWidget()
        table_layout = QVBoxLayout(table_page)
        table_layout.setContentsMargins(0, 6, 0, 0)
        line_tools = QHBoxLayout()
        self.line_selector = QComboBox()
        self.line_selector.setEditable(True)
        self.line_selector.setInsertPolicy(qt_enum(QComboBox, "InsertPolicy", "NoInsert"))
        self.line_selector.completer().setFilterMode(qt_enum(Qt, "MatchFlag", "MatchContains"))
        self.line_previous = self._translated_widget(QPushButton, "‹", "‹", "‹")
        self.line_next = self._translated_widget(QPushButton, "›", "›", "›")
        self.line_previous.setFixedWidth(30)
        self.line_next.setFixedWidth(30)
        self._bind_text(self.line_previous.setToolTip, "Previous line", "Línea anterior", "Linha anterior")
        self._bind_text(self.line_next.setToolTip, "Next line", "Línea siguiente", "Próxima linha")
        self.line_field = self._translated_widget(QPushButton, "Line channel…", "Canal de línea…", "Canal de linha…")
        self.line_field.clicked.connect(self._choose_line_channel)
        columns = self._translated_widget(QPushButton, "Columns…", "Columnas…", "Colunas…")
        columns.clicked.connect(self._choose_columns)
        for widget in (self.line_previous, self.line_selector, self.line_next, self.line_field, columns):
            line_tools.addWidget(widget, 1 if widget is self.line_selector else 0)
        table_layout.addLayout(line_tools)
        self.line_previous.clicked.connect(lambda: self.line_selector.setCurrentIndex(self.line_selector.currentIndex() - 1))
        self.line_next.clicked.connect(lambda: self.line_selector.setCurrentIndex(self.line_selector.currentIndex() + 1))
        self.line_selector.currentIndexChanged.connect(self._select_line)
        navigation = QHBoxLayout()
        self.page_first = self._translated_widget(
            QPushButton, "First", "Primera", "Primeira"
        )
        self.page_previous = self._translated_widget(
            QPushButton, "Previous", "Anterior", "Anterior"
        )
        self.page_next = self._translated_widget(
            QPushButton, "Next", "Siguiente", "Próxima"
        )
        self.page_reload = self._translated_widget(
            QPushButton, "Load selection", "Cargar selección", "Carregar seleção"
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
        self._bind_text(
            self.page_size.setToolTip,
            "Rows per page",
            "Filas por página",
            "Linhas por página",
        )
        self.page_first.setEnabled(False)
        self.page_previous.setEnabled(False)
        self.page_next.setEnabled(False)
        self.page_controls = QWidget()
        navigation.setContentsMargins(0, 0, 0, 0)
        self.page_controls.setLayout(navigation)
        table_layout.addWidget(self.page_controls)
        self.table = QTableView()
        self.sheet_model = SurveySheetModel(self.table)
        self.sheet_model.failed.connect(lambda error: self._set_result(self.page_status, error))
        self.table.setModel(self.sheet_model)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setSectionResizeMode(qt_enum(QHeaderView, "ResizeMode", "Fixed"))
        self.table.verticalHeader().setDefaultSectionSize(self.table.fontMetrics().height() + 8)
        self.table.horizontalHeader().setContextMenuPolicy(qt_enum(Qt, "ContextMenuPolicy", "CustomContextMenu"))
        self.table.horizontalHeader().customContextMenuRequested.connect(self._column_menu)
        self.table.clicked.connect(self._sheet_clicked)
        self.table.setEditTriggers(
            qt_enum(QAbstractItemView, "EditTrigger", "NoEditTriggers")
        )
        table_layout.addWidget(self.table, 1)
        self.page_status = self._result_label(
            "Select one database to open its sheet.",
            "Selecciona una base para abrir su hoja.",
            "Selecione um banco para abrir sua planilha.",
        )
        self.page_status.setWordWrap(True)
        table_layout.addWidget(self.page_status)
        self._translated_tab(table_page, "Table", "Tabla", "Tabela")
        profile_page = QWidget()
        profile_layout = QVBoxLayout(profile_page)
        profile_controls = QGridLayout()
        self.profile_channel = QComboBox()
        self.profile_axis = QComboBox()
        self.profile_compare = QComboBox()
        self.profile_compare_mode = QComboBox()
        self._translated_option(
            self.profile_compare_mode,
            "overlay",
            "Overlay A / B",
            "Superponer A / B",
            "Sobrepor A / B",
        )
        self._translated_option(
            self.profile_compare_mode,
            "difference",
            "Difference B − A",
            "Diferencia B − A",
            "Diferença B − A",
        )
        self.profile_load = self._translated_widget(
            QPushButton, "Draw profile", "Dibujar perfil", "Desenhar perfil"
        )
        profile_controls.addWidget(
            self._translated_widget(QLabel, "Channel", "Canal", "Canal"), 0, 0
        )
        profile_controls.addWidget(self.profile_channel, 0, 1)
        profile_controls.addWidget(
            self._translated_widget(QLabel, "X axis", "Eje X", "Eixo X"), 1, 0
        )
        profile_controls.addWidget(self.profile_axis, 1, 1)
        profile_controls.addWidget(self.profile_load, 0, 2, 2, 1)
        profile_controls.setColumnStretch(1, 1)
        self.profile_distance = self._translated_widget(
            QCheckBox,
            "Distance along profile (m), using saved XY / CRS",
            "Distancia del perfil (m), usando XY / CRS guardados",
            "Distância do perfil (m), usando XY / SRC salvos",
        )
        self.profile_distance.toggled.connect(
            lambda checked: self.profile_axis.setEnabled(not checked)
        )
        self._bind_text(
            self.profile_distance.setToolTip,
            "PyProj: CRS unit conversion and ellipsoidal horizontal distance. No vertical datum correction or 3-D path is inferred.",
            "PyProj: conversión de unidades del CRS y distancia horizontal elipsoidal. No se infiere corrección de datum vertical ni trayectoria 3D.",
            "PyProj: conversão de unidades do SRC e distância horizontal elipsoidal. Não se infere correção de datum vertical nem trajetória 3D.",
        )
        profile_controls.addWidget(self.profile_distance, 2, 0, 1, 3)
        profile_controls.addWidget(
            self._translated_widget(QLabel, "Compare B", "Comparar B", "Comparar B"),
            3,
            0,
        )
        profile_controls.addWidget(self.profile_compare, 3, 1)
        profile_controls.addWidget(self.profile_compare_mode, 3, 2)
        profile_layout.addLayout(profile_controls)
        self.profile_legend = QLabel()
        self.profile_legend.setWordWrap(True)
        self.profile_legend.setTextFormat(qt_enum(Qt, "TextFormat", "RichText"))
        profile_layout.addWidget(self.profile_legend)
        self.profile_plot = SurveyProfileWidget()
        self._bind_text(
            self._set_profile_empty_text,
            "Choose a numeric channel and draw its profile.",
            "Elige un canal numérico y dibuja su perfil.",
            "Escolha um canal numérico e desenhe seu perfil.",
        )
        self._bind_text(
            self.profile_plot.setAccessibleName,
            "Channel profile",
            "Perfil de canal",
            "Perfil de canal",
        )
        profile_layout.addWidget(self.profile_plot, 1)
        toolbar = QHBoxLayout()
        for caption, callback in (
            (("+", "+", "+"), lambda: self.profile_plot.zoom(0.8)),
            (("−", "−", "−"), lambda: self.profile_plot.zoom(1.25)),
            (("Fit", "Ajustar", "Ajustar"), self.profile_plot.fit),
            (
                ("Save view PNG…", "Guardar vista PNG…", "Salvar vista PNG…"),
                self.export_profile_view,
            ),
        ):
            button = self._translated_widget(QPushButton, *caption)
            button.clicked.connect(callback)
            toolbar.addWidget(button)
        profile_layout.addLayout(toolbar)
        self.profile_cursor = self._result_label(
            "Wheel: zoom · drag: pan · statistics refer to the full loaded selection",
            "Rueda: zoom · arrastrar: desplazar · estadísticas de toda la selección cargada",
            "Roda: zoom · arrastar: deslocar · estatísticas de toda a seleção carregada",
        )
        self.profile_cursor.setWordWrap(True)
        self.profile_plot.positionChanged.connect(
            lambda value: self._set_result(self.profile_cursor, value)
        )
        profile_layout.addWidget(self.profile_cursor)
        self.profile_statistics = self._result_label(
            "Display only. No channel values are changed.",
            "Solo visualización. No se modifica ningún valor.",
            "Apenas visualização. Nenhum valor é alterado.",
        )
        self.profile_statistics.setWordWrap(True)
        profile_layout.addWidget(self.profile_statistics)
        self.profile_load.clicked.connect(self.load_profile)
        self._translated_tab(profile_page, "Profiles", "Perfiles", "Perfis")
        self.views.currentChanged.connect(self._refresh_sheet_profile)
        self.channels_list.itemSelectionChanged.connect(self._sidebar_channels_changed)
        self.status = self._result_label(
            "Immutable originals · versioned channels · PyArrow/Parquet + SQLite",
            "Originales inmutables · canales versionados · PyArrow/Parquet + SQLite",
            "Originais imutáveis · canais versionados · PyArrow/Parquet + SQLite",
        )
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        from .task_history_widget import TaskHistoryWidget

        self.tasks = TaskHistoryWidget(tr, self)
        self._bind_option(
            self.profile_axis,
            None,
            "Selected sample",
            "Muestra seleccionada",
            "Amostra selecionada",
        )
        self.tasks.cancelRequested.connect(
            lambda: (
                self.worker.requestInterruption() if self.worker is not None else None
            )
        )
        layout.addWidget(self.tasks)
        self._fill_line_selector()
        self.line_field.setEnabled(False)
        saved = QSettings().value(KEY_WORKSPACE, "", type=str)
        if saved and (Path(saved) / "catalog.sqlite").is_file():
            try:
                self.set_project(saved)
            except Exception as error:
                self._set_result(self.status, str(error))

    def _bind_text(self, setter, *labels):
        self._translations.append((setter, labels))
        setter(tr(*labels))

    def _translated_widget(self, widget_class, *labels):
        widget = widget_class()
        self._bind_text(widget.setText, *labels)
        return widget

    def _translated_tab(self, page, *labels):
        index = self.views.addTab(page, "")
        self._bind_text(lambda value: self.views.setTabText(index, value), *labels)

    def _bind_option(self, combo, key, *labels):
        def update(value):
            index = combo.findData(key)
            if index >= 0:
                combo.setItemText(index, value)

        self._bind_text(update, *labels)

    def _translated_option(self, combo, key, *labels):
        combo.addItem("", key)
        self._bind_option(combo, key, *labels)

    def _set_profile_empty_text(self, value):
        self.profile_plot.empty_text = value
        self.profile_plot.update()

    def _result_label(self, *labels):
        widget = QLabel()
        self._set_result(widget, lambda: tr(*labels))
        return widget

    def _set_result(self, widget, value):
        if callable(value):
            self._results[widget] = value
            widget.setText(value())
        else:
            self._results.pop(widget, None)
            widget.setText(value)

    def retranslate(self):
        for setter, labels in self._translations:
            setter(tr(*labels))
        for widget, render in self._results.items():
            widget.setText(render())
        self.update_filter_caption()
        self.sheet_model.retranslate()
        translate_survey_notices(self)
        self._fill_line_selector(preserve=True)
        for index in range(self.channels_list.count()):
            item = self.channels_list.item(index)
            if channel := self._channel_info.get(item.data(256)):
                item.setToolTip(channel_tooltip(channel))
        if self._profile_axis_text is not None:
            self.profile_plot.x_label = self._profile_axis_text()
            self.profile_plot.update()
        self.tasks.retranslate()
        if self.worker is not None:
            self.progress_dialog.setCancelButtonText(
                tr("Cancel", "Cancelar", "Cancelar")
            )
            rows = self.tasks.active["rows"] if self.tasks.active else None
            self.progress_dialog.setLabelText(
                tr("Rows: ", "Filas: ", "Linhas: ") + rows
                if rows is not None
                else tr("Working…", "Procesando…", "Processando…")
            )

    def set_project(self, path, create=False):
        self.store = SurveyStore(path, create=create)
        QSettings().setValue(KEY_WORKSPACE, str(self.store.root))
        self._set_result(self.path_label, str(self.store.root))
        self.refresh()

    def select_database(self, path, database_id):
        if self.store is None or self.store.root != Path(path).resolve():
            self.set_project(path)
        else:
            self.refresh()
        for index in range(self.databases_list.count()):
            item = self.databases_list.item(index)
            if item.data(256) == database_id:
                self.databases_list.blockSignals(True)
                self.databases_list.clearSelection()
                self.databases_list.setCurrentRow(index)
                item.setSelected(True)
                self.databases_list.blockSignals(False)
                self.refresh_channels()
                self._show_all_requested = False
                self.views.setCurrentIndex(0)
                if self._lines:
                    self.line_selector.setCurrentIndex(0)
                break

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
        if self._sheet_channel in self._channel_info:
            return [self._sheet_channel]
        return self._sidebar_channels()

    def _sidebar_channels(self):
        return [item.data(256) for item in self.channels_list.selectedItems()]

    def refresh_channels(self):
        selected = set(self._sidebar_channels())
        self.channels_list.blockSignals(True)
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
            self._show_all_requested = False
            self._set_result(
                self.page_status,
                lambda: tr(
                    "Select one database to open its sheet.",
                    "Selecciona una base para abrir su hoja.",
                    "Selecione um banco para abrir sua planilha.",
                ),
            )
            self.profile_plot.clear()
            self._profile_axis_text = None
            self.profile_legend.clear()
            self._set_result(
                self.profile_statistics,
                lambda: tr(
                    "Select a channel to inspect.",
                    "Selecciona un canal para inspeccionar.",
                    "Selecione um canal para inspecionar.",
                ),
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
            self.channels_list.blockSignals(False)
            self._refresh_sheet(ids)
            return
        rows = self.store.channels(ids[0])
        common = {c["name"] for c in rows}
        for database in ids[1:]:
            common.intersection_update(c["name"] for c in self.store.channels(database))
        for row in rows:
            if row["name"] not in common:
                continue
            self._channel_info[row["name"]] = row
            item = QListWidgetItem(channel_description(row) if len(ids) == 1 else row["name"])
            item.setData(256, row["name"])
            item.setToolTip(channel_tooltip(row))
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
        self.channels_list.blockSignals(False)
        self._refresh_sheet(ids)

    def _sheet_setting(self, name):
        return f"TerraWorkbench/surveySheet/{self.selected_databases()[0]}/{name}"

    def _refresh_sheet(self, ids, force=False):
        if len(ids) != 1 or self.store is None:
            self._index_cancel.set()
            self._page_generation += 1
            self._profile_generation += 1
            self._sheet_key = None
            self._sheet_columns = []
            self._line_channel = None
            self._lines = {}
            self.sheet_model.reset([])
            self._fill_line_selector()
            self.line_field.setEnabled(False)
            self.page_controls.hide()
            return
        from ..terraworkbench_core.survey_map import survey_map_channels

        database = next(row for row in self.store.databases() if row["id"] == ids[0])
        stored = self.store._sheet_channels(ids[0])
        key = (self.store.root, ids[0], database["metadata"],
               tuple((row["name"], row["unit"], row["version_id"]) for row in stored))
        if key == self._sheet_key and not force:
            return
        previous = self.line_selector.currentData() if self._sheet_key and key[:2] == self._sheet_key[:2] else None
        self._sheet_key = key
        self._index_cancel.set()
        self._index_cancel = Event()
        self._page_generation += 1
        self._profile_generation += 1
        self._sheet_channel = self._sheet_row = None
        channels, metadata = survey_map_channels(self.store, ids[0])
        by_id = {channel["id"]: channel["name"] for channel in stored}
        by_name = {channel["name"]: channel for channel in stored}
        roles = metadata.get("channel_roles", {})
        override = QSettings().value(self._sheet_setting("line"), "", type=str)
        self._line_channel = by_id.get(override) or by_id.get(roles.get("line")) or channels.line
        leading = [self._line_channel, channels.fiducial or channels.time, channels.x, channels.y]
        ordered = dict.fromkeys(name for name in [*leading, *by_name] if name in by_name)
        self._sheet_columns = [by_name[name] for name in ordered]
        self._lines = {}
        self.sheet_model.reset(self._sheet_columns)
        self._apply_columns()
        self._fill_line_selector()
        self.line_field.setEnabled(bool(stored))
        self.page_controls.hide()
        if not self._line_channel:
            self._select_line()
            return
        self._set_result(self.page_status, lambda: tr(
            "Reading line identifiers…", "Leyendo identificadores de línea…",
            "Lendo identificadores de linha…",
        ))
        store, field, canceled = self.store, self._line_channel, self._index_cancel
        background(
            (canceled, previous),
            lambda: line_spans(store, ids[0], field, channels.line_type, metadata, canceled.is_set),
            self._line_index_ready,
        )

    def _line_index_ready(self, key, result, error):
        canceled, previous = key
        if canceled is not self._index_cancel or canceled.is_set():
            return
        self._lines = result or {}
        self._fill_line_selector(value=previous)
        if self._show_all_requested:
            self.line_selector.blockSignals(True)
            self.line_selector.setCurrentIndex(self.line_selector.count() - 1)
            self.line_selector.blockSignals(False)
            self._update_line_arrows()
            if self._page_context is not None or self.worker is not None:
                return
        self._select_line()
        if error:
            self._set_result(self.status, error)

    def _fill_line_selector(self, preserve=False, value=None):
        if preserve:
            value = self.line_selector.currentData()
        was_all = preserve and value is None
        self.line_selector.blockSignals(True)
        self.line_selector.clear()
        for line, (_, _, kind) in self._lines.items():
            title = str(line)
            label = {
                "traverse": tr("Traverse", "Vuelo", "Voo"),
                "tie": tr("Tie", "Control", "Controle"),
                "other": tr("Other", "Otra", "Outra"),
            }.get(kind)
            self.line_selector.addItem(f"{title} · {label}" if label else title, line)
        self.line_selector.addItem(tr("All rows", "Todas las filas", "Todas as linhas"), None)
        index = self.line_selector.count() - 1 if was_all else self.line_selector.findData(value)
        self.line_selector.setCurrentIndex(max(0, index) if value is not None or was_all else 0)
        self.line_selector.setEnabled(bool(self._lines))
        self.line_selector.blockSignals(False)
        channel = getattr(self, "_line_channel", None)
        caption = tr("Line channel…", "Canal de línea…", "Canal de linha…")
        if channel:
            short = self.line_field.fontMetrics().elidedText(
                channel, qt_enum(Qt, "TextElideMode", "ElideMiddle"), 135
            )
            self.line_field.setText(f"{caption.rstrip('…')}: {short}")
            self.line_field.setToolTip(f"{caption.rstrip('…')}: {channel}")
        else:
            self.line_field.setText(caption)
            self.line_field.setToolTip(caption)
        self._update_line_arrows()

    def _update_line_arrows(self):
        current = self.line_selector.currentIndex()
        count = len(self._lines)
        self.line_previous.setEnabled(count > 0 and current > 0)
        self.line_next.setEnabled(0 <= current < count - 1)

    def _select_line(self, *_args):
        self._update_line_arrows()
        self._sheet_row = None
        self.profile_plot.set_selected_sample(None)
        self._page_generation += 1
        line = self.line_selector.currentData()
        self._show_all_requested = line is None and bool(self._lines)
        self.page_controls.setVisible(line is None and bool(self._sheet_columns))
        if line is None:
            if self._sheet_columns:
                self.sheet_model.reset(self._sheet_columns)
                self._apply_columns()
                self.load_page(0, automatic=True)
            return
        spans, ends, _ = self._lines[line]
        self.sheet_model.reset(self._sheet_columns, store=self.store, spans=spans, ends=ends)
        self._apply_columns()
        self.table.scrollToTop()
        self._set_result(self.page_status, lambda: tr(
            "{count:,} rows · read-only", "{count:,} filas · solo lectura",
            "{count:,} linhas · somente leitura",
        ).format(count=ends[-1]))
        self._refresh_sheet_profile()

    def _choose_line_channel(self):
        if not self._sheet_columns:
            return
        automatic = tr("Automatic", "Automático", "Automático")
        names = [channel["name"] for channel in self._sheet_columns]
        options = [automatic, *names]
        initial = options.index(self._line_channel) if self._line_channel in names else 0
        chosen, ok = QInputDialog.getItem(self, self.line_field.text(), tr(
            "Line identifier", "Identificador de línea", "Identificador de linha",
        ), options, initial, False)
        if ok:
            value = self._channel_info[chosen]["id"] if chosen in names else ""
            QSettings().setValue(self._sheet_setting("line"), value)
            self._refresh_sheet(self.selected_databases(), force=True)

    def _hidden_columns(self):
        return set(QSettings().value(self._sheet_setting("hidden"), [], type=list)) if self._sheet_columns else set()

    def _apply_columns(self):
        hidden = self._hidden_columns()
        metrics = self.table.fontMetrics()
        for index, channel in enumerate(self.sheet_model.channels):
            self.table.setColumnHidden(index, channel["id"] in hidden)
            width = max(metrics.horizontalAdvance(channel[key]) for key in ("name", "unit"))
            self.table.setColumnWidth(index, max(92, width + 24))
        self.table.horizontalHeader().setMinimumHeight(metrics.height() * 2 + 8)

    def _save_columns(self, hidden):
        if self._sheet_columns and len(hidden) < len(self._sheet_columns):
            QSettings().setValue(self._sheet_setting("hidden"), sorted(hidden))
            self._apply_columns()
            self._refresh_sheet_profile()

    def _choose_columns(self):
        if not self._sheet_columns:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Columns", "Columnas", "Colunas"))
        layout = QVBoxLayout(dialog)
        checks = QListWidget(dialog)
        layout.addWidget(checks)
        hidden = self._hidden_columns()
        checked = qt_enum(Qt, "CheckState", "Checked")
        unchecked = qt_enum(Qt, "CheckState", "Unchecked")
        for channel in self._sheet_columns:
            item = QListWidgetItem(channel_description(channel), checks)
            item.setData(256, channel["id"])
            item.setCheckState(unchecked if channel["id"] in hidden else checked)
        ok = qt_enum(QDialogButtonBox, "StandardButton", "Ok")
        cancel = qt_enum(QDialogButtonBox, "StandardButton", "Cancel")
        buttons = QDialogButtonBox(ok | cancel, parent=dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        checks.itemChanged.connect(lambda _item: buttons.button(ok).setEnabled(
            any(checks.item(index).checkState() == checked for index in range(checks.count()))
        ))
        if dialog.exec():
            self._save_columns({checks.item(index).data(256) for index in range(checks.count())
                                if checks.item(index).checkState() != checked})
        dialog.deleteLater()

    def _column_menu(self, point):
        header = self.table.horizontalHeader()
        section = header.logicalIndexAt(point)
        if section < 0:
            return
        channel = self.sheet_model.channels[section]
        hidden = self._hidden_columns()
        menu = QMenu(header)
        hide = menu.addAction(tr("Hide column", "Ocultar columna", "Ocultar coluna"))
        hide.setEnabled(len(hidden) < len(self._sheet_columns) - 1)
        hide.triggered.connect(lambda: self._save_columns(hidden | {channel["id"]}))
        menu.addAction(tr("Columns…", "Columnas…", "Colunas…"), self._choose_columns)
        menu.exec(header.mapToGlobal(point))
        menu.deleteLater()

    def _sidebar_channels_changed(self):
        self._sheet_channel = None
        self._refresh_sheet_profile()

    def _sheet_clicked(self, index):
        self._sheet_channel = self.sheet_model.channels[index.column()]["name"]
        self._sheet_row = index.row() + 1 if self.line_selector.currentData() is not None else None
        if self._auto_profile:
            self.profile_plot.set_selected_sample(self._sheet_row)

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

            def summary():
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
                return message

            self._set_result(self.status, summary)

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
            lambda: self._set_result(
                self.status,
                lambda: tr(
                    "Cancelled.",
                    "Cancelado.",
                    "Cancelado.",
                ),
            )
        )
        self.worker.finished.connect(self.finished)
        self.progress_dialog.show()
        self.worker.start()

    def completed(self, result, callback):
        self._task_state = "completed"
        if callback is None:
            self._set_result(self.status, str(result))
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
        self._set_result(self.status, message)
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
        self._index_cancel.set()
        self.sheet_model.canceled.set()
        self._profile_generation += 1
        close_survey_notices(self)
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

        text_options, import_metadata = {}, {}
        for path in paths:
            if Path(path).suffix.lower() != ".parquet":
                wizard = TextImportDialog(path, self)
                accepted = wizard.exec() == qt_enum(QDialog, "DialogCode", "Accepted")
                if not accepted:
                    wizard.deleteLater()
                    return
                text_options[path] = wizard.options
                import_metadata[path] = wizard.survey_metadata
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
                    database_id = store.import_file(
                        path,
                        name=name,
                        canceled=cancel,
                        progress=progress,
                        text_options=text_options.get(path),
                        metadata=import_metadata.get(path),
                    )
                    used_names.add(name)
                    results.append(
                        self._try_survey_map(store, database_id, cancel, progress)
                    )
                except InterruptedError:
                    raise
                except Exception as error:
                    results.append((None, Path(path).name, None, str(error)))
            return results

        def imported(results):
            for database_id, name, _package, _error in results:
                if database_id:
                    notify_survey_database(self.iface, store.root, database_id, name, self)
            self._show_survey_maps(store, results)

        self.start(run, imported)

    def preview(self):
        self._show_all_requested = True
        self.line_selector.blockSignals(True)
        self.line_selector.setCurrentIndex(self.line_selector.count() - 1)
        self.line_selector.blockSignals(False)
        self._update_line_arrows()
        self.page_controls.show()
        self.load_page(0)

    def load_page(self, offset=0, *, automatic=False):
        ids = self.selected_databases()
        if len(ids) != 1 or not self._sheet_columns:
            if not automatic:
                self.require_selection(channels=False, single=True)
            return
        columns = self._sheet_columns
        names = [channel["name"] for channel in columns]
        store, filters = self.store, self.filters()
        limit = self.page_size.currentData()
        self._page_generation += 1
        generation = self._page_generation
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
            if generation != self._page_generation or self.line_selector.currentData() is not None:
                return
            self.sheet_model.reset(columns, page=result["data"], offset=offset)
            self._apply_columns()
            self.table.scrollToTop()
            self._page_offset, self._page_has_next, self._page_context = (
                offset,
                result["has_next"],
                context,
            )
            self.page_first.setEnabled(offset > 0)
            self.page_previous.setEnabled(offset > 0)
            self.page_next.setEnabled(result["has_next"])
            total = next(d["rows"] for d in store.databases() if d["id"] == ids[0])

            def summary():
                message = tr(
                    "Selection rows {first}–{last} · database: {total:,} rows · read-only",
                    "Filas {first}–{last} de la selección · base: {total:,} filas · solo lectura",
                    "Linhas {first}–{last} da seleção · banco: {total:,} linhas · somente leitura",
                ).format(
                    first=offset + 1 if result["rows"] else 0,
                    last=offset + result["rows"] if result["rows"] else 0,
                    total=total,
                )
                return message

            self._set_result(self.page_status, summary)
            self._set_result(self.status, summary)
            self.views.setCurrentIndex(0)

        if automatic:
            canceled = self._index_cancel
            self._auto_page = generation, display
            background(generation, lambda: run(canceled.is_set, None), self._automatic_page_ready)
        else:
            self.start(
                run, display,
                tr("Load table page", "Cargar página de tabla", "Carregar página da tabela"),
            )

    def _automatic_page_ready(self, generation, result, error):
        if generation != self._page_generation or self._auto_page[0] != generation:
            return
        if error:
            self._set_result(self.page_status, error)
        else:
            self._auto_page[1](result)

    def _refresh_sheet_profile(self, *_args):
        self._profile_generation += 1
        if self.views.currentIndex() != 1 or self.line_selector.currentData() is None:
            return
        line, field = self.line_selector.currentData(), self._line_channel
        store, database = self.store, self.selected_databases()[0]
        hidden = self._hidden_columns()
        selected = self._sidebar_channels() or ([self._sheet_channel] if self._sheet_channel else [])
        numeric = [
            channel for channel in self._sheet_columns if channel["id"] not in hidden
            and channel["name"] != field
            and channel["data_type"].startswith(("double", "float", "int", "uint", "decimal"))
        ]
        selected_rows = [channel for channel in numeric if channel["name"] in selected]
        channel = self.profile_channel.currentData()
        if not selected_rows and not selected:
            selected_rows = [row for row in numeric if row["name"] == channel] or numeric[:1]
        self._auto_profile = True
        self.profile_plot.clear()
        self.profile_legend.clear()
        if not selected_rows:
            return
        self._set_result(self.profile_statistics, lambda: tr(
            "Reading line profiles…", "Leyendo perfiles de línea…", "Lendo perfis de linha…",
        ))
        filters = {field: [line]}
        canceled = self._index_cancel

        def run():
            profiles = []
            for row in selected_rows:
                result = read_survey_profile(
                    store, database, row["name"], filters=filters, cancel=canceled.is_set,
                )
                label = f"{row['name']} [{row['unit']}]" if row["unit"] else row["name"]
                profiles.extend({**segment, "label": label} for segment in result["segments"])
            return profiles

        background(self._profile_generation, run, self._sheet_profile_ready)

    def _sheet_profile_ready(self, generation, segments, error):
        if generation != self._profile_generation:
            return
        if error:
            self._set_result(self.profile_statistics, error)
            return
        self._profile_axis_text = lambda: tr("Selected sample", "Muestra seleccionada", "Amostra selecionada")
        self.profile_plot.set_profile({"segments": segments}, self._profile_axis_text(), "")
        self.profile_plot.set_selected_sample(self._sheet_row)
        self.profile_legend.setText(" &nbsp; ".join(
            f'<span style="color:{color.name()}">■ {escape(name)}</span>'
            for name, color in self.profile_plot.series_colors().items()
        ))
        self._set_result(self.profile_statistics, lambda: tr(
            "Line profiles · units shown in the legend",
            "Perfiles de la línea · unidades en la leyenda",
            "Perfis da linha · unidades na legenda",
        ))

    def load_profile(self):
        selection = self.require_selection(channels=False, single=True)
        if not selection or not self.profile_channel.currentData():
            return
        database = selection[0][0]
        store, filters = self.store, self.filters()
        if self.line_selector.currentData() is not None:
            filters[self._line_channel] = [self.line_selector.currentData()]
        self._profile_generation += 1
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
            self._auto_profile = False
            self.profile_plot.set_selected_sample(None)
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

            self._profile_axis_text = lambda: (
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
                )
            )
            self.profile_plot.set_profile(
                result,
                self._profile_axis_text(),
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

            def statistics():
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
                    **{
                        key: number(key)
                        for key in ("minimum", "maximum", "mean", "std")
                    },
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
                        return (
                            "—" if record["mean"] is None else f"{record['mean']:.6g}"
                        )

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
                return message

            self._set_result(self.profile_statistics, statistics)
            self._set_result(
                self.status,
                lambda: tr(
                    "Read-only profile loaded",
                    "Perfil de solo lectura cargado",
                    "Perfil somente leitura carregado",
                ),
            )
            self.views.blockSignals(True)
            self.views.setCurrentIndex(1)
            self.views.blockSignals(False)

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
                self._set_result(
                    self.status,
                    lambda: tr(
                        "Created {output}: {rows} rows; {output_null_rows} null outputs; {short_segments} short segments; {spikes_replaced} spikes replaced. Open Channel pipeline to inspect.",
                        "Creado {output}: {rows} filas; {output_null_rows} salidas nulas; {short_segments} tramos cortos; {spikes_replaced} picos reemplazados. Abre Pipeline del canal para inspeccionar.",
                        "Criado {output}: {rows} linhas; {output_null_rows} saídas nulas; {short_segments} trechos curtos; {spikes_replaced} picos substituídos. Abra Pipeline do canal para inspecionar.",
                    ).format(**result),
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
                    self._set_result(
                        self.status,
                        lambda: tr(
                            "CRS assigned; coordinate values unchanged.",
                            "CRS asignado; valores de coordenadas sin cambios.",
                            "SRC atribuído; valores das coordenadas sem alterações.",
                        ),
                    )
                except Exception as error:
                    self.fail(str(error))
        dialog.deleteLater()

    @staticmethod
    def _try_survey_map(
        store, database_id, cancel, progress, channels=None, columns=None, filters=None
    ):
        from ..qgis_plugin.survey_map_layers import (
            write_survey_geopackage,
            qgis_boundary,
        )
        from ..terraworkbench_core.survey_map import (
            build_survey_map,
            survey_map_channels,
        )

        name = next(
            row["name"] for row in store.databases() if row["id"] == database_id
        )
        try:
            channels = channels or survey_map_channels(store, database_id)[0]
            if not (
                channels.x
                and channels.y
                and channels.x != channels.y
                and QgsCoordinateReferenceSystem(channels.crs or "").isValid()
            ):
                return database_id, name, None, None
            if columns is None:
                columns = [row["name"] for row in store.channels(database_id)]
            survey = build_survey_map(
                store,
                database_id,
                channels=channels,
                sample_columns=columns,
                filters=filters,
                canceled=cancel,
                boundary_builder=qgis_boundary,
            )
            return (
                database_id,
                name,
                write_survey_geopackage(store, database_id, survey, cancel, progress),
                None,
            )
        except InterruptedError:
            raise
        except Exception as error:
            return database_id, name, None, str(error)

    def _show_survey_maps(self, store, results):
        from ..qgis_plugin.survey_map_layers import add_survey_map

        if self._dispose or self._close_requested:
            return
        messages, retry = [], []
        for database_id, name, package, error in results:
            if error:
                messages.append(f"{name}: {error}")
            elif package is None:
                from .survey_map_dialog import choose_map_channels
                from ..terraworkbench_core.survey_map import survey_map_channels

                fields = [row["name"] for row in store.channels(database_id)]
                current = survey_map_channels(store, database_id)[0]
                channels = choose_map_channels(self, current, fields)
                if channels is not None:
                    store.configure_geometry(
                        database_id,
                        channels.x,
                        channels.y,
                        channels.crs,
                        line=channels.line,
                    )
                    retry.append(database_id)
            else:
                add_survey_map(QgsProject.instance(), store, database_id, name, package)
                summary = package[2]

                def describe(name=name, summary=summary):
                    message = tr(
                        "Survey added to map",
                        "Levantamiento añadido al mapa",
                        "Levantamento adicionado ao mapa",
                    )
                    if not summary["has_line_channel"]:
                        message += " · " + tr(
                            "No line channel; samples and boundary only",
                            "Sin canal de línea; solo muestras y contorno",
                            "Sem canal de linha; apenas amostras e limite",
                        )
                    if summary["invalid_samples"]:
                        message += " · " + tr(
                            "{n} invalid coordinate pairs omitted",
                            "{n} pares de coordenadas inválidos omitidos",
                            "{n} pares de coordenadas inválidos omitidos",
                        ).format(n=summary["invalid_samples"])
                    return f"{name}: {message}"

                messages.append(describe)
        self._set_result(
            self.status,
            lambda: " | ".join(
                message() if callable(message) else message for message in messages
            ),
        )
        if retry:
            # completed is emitted before finished; wait until start can own a new worker.
            from qgis.PyQt.QtCore import QTimer

            def rebuild():
                if self._dispose or self._close_requested:
                    return
                if self.worker is not None:
                    QTimer.singleShot(10, rebuild)
                    return
                self.start(
                    lambda cancel, progress: [
                        self._try_survey_map(store, db, cancel, progress)
                        for db in retry
                    ],
                    lambda value: self._show_survey_maps(store, value),
                )

            QTimer.singleShot(0, rebuild)

    def to_qgis(self):
        from .survey_map_dialog import choose_map_channels
        from ..terraworkbench_core.survey_map import survey_map_channels

        selection = self.require_selection(channels=False, single=True)
        if not selection:
            return
        ids, names = selection
        database_id = ids[0]
        store, filters = self.store, self.filters()
        channels, _ = survey_map_channels(store, database_id)
        fields = [row["name"] for row in store.channels(database_id)]
        if (
            not channels.x
            or not channels.y
            or channels.x == channels.y
            or not QgsCoordinateReferenceSystem(channels.crs or "").isValid()
        ):
            channels = choose_map_channels(self, channels, fields)
            if channels is None:
                return
            try:
                store.configure_geometry(
                    database_id,
                    channels.x,
                    channels.y,
                    channels.crs,
                    line=channels.line,
                )
            except Exception as error:
                self.fail(str(error))
                return

        def run(cancel, progress):
            return [
                self._try_survey_map(
                    store,
                    database_id,
                    cancel,
                    progress,
                    channels,
                    names or fields,
                    filters,
                )
            ]

        self.start(
            run,
            lambda results: self._show_survey_maps(store, results),
            tr("Build survey map", "Construir mapa", "Gerar mapa"),
        )

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
