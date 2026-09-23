"""Survey project manager. Long I/O runs on a cancellable worker thread."""

from pathlib import Path
import json
import uuid

from qgis.PyQt.QtCore import QSettings, QThread, pyqtSignal, QUrl, QUrlQuery
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFileDialog, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QGridLayout,
    QMessageBox, QProgressDialog, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)
from qgis.core import QgsProject, QgsVectorLayer, QgsCoordinateReferenceSystem

from .i18n import language
from .qgis_compat import qt_enum
from .survey_store import SurveyStore

KEY_WORKSPACE = "TerraWorkbench/surveyWorkspace"


def tr(en, es, pt):
    return {"en": en, "es": es, "pt": pt}.get(language(), en)


class StoreWorker(QThread):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            result = self.operation(self.isInterruptionRequested,
                                    lambda count: self.progress.emit(str(count)))
            self.completed.emit(result)
        except Exception as error:
            self.failed.emit(str(error))


class SurveyWorkspaceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Survey databases", "Bases de levantamientos", "Bancos de levantamentos"))
        self.resize(920, 650)
        self.store = None
        self.worker = None
        self._dispose = False
        self._close_requested = False
        layout = QVBoxLayout(self)
        self.controls = QWidget()
        body = QVBoxLayout(self.controls)
        layout.addWidget(self.controls)
        buttons = QHBoxLayout()
        body.addLayout(buttons)
        for labels, callback in (
            (("New project…", "Nuevo proyecto…", "Novo projeto…"), self.new_project),
            (("Open project…", "Abrir proyecto…", "Abrir projeto…"), self.open_project),
            (("Import text / Parquet…", "Importar texto / Parquet…", "Importar texto / Parquet…"), self.import_files),
        ):
            button = QPushButton(tr(*labels))
            button.clicked.connect(callback)
            buttons.addWidget(button)
        self.path_label = QLabel(tr("Choose a working folder", "Elige una carpeta de trabajo", "Escolha uma pasta de trabalho"))
        self.path_label.setWordWrap(True)
        body.addWidget(self.path_label)
        body.addWidget(QLabel(tr("Select databases; channels below are common to the selection.",
            "Selecciona bases; abajo aparecen los canales comunes a la selección.",
            "Selecione bancos; abaixo aparecem os canais comuns à seleção.")))
        selection = QHBoxLayout()
        self.databases_list = QListWidget()
        self.databases_list.setSelectionMode(qt_enum(QAbstractItemView, "SelectionMode", "ExtendedSelection"))
        self.databases_list.itemSelectionChanged.connect(self.refresh_channels)
        self.channels_list = QListWidget()
        self.channels_list.setSelectionMode(qt_enum(QAbstractItemView, "SelectionMode", "ExtendedSelection"))
        selection.addWidget(self.databases_list)
        selection.addWidget(self.channels_list)
        body.addLayout(selection)
        filtering = QHBoxLayout()
        filtering.addWidget(QLabel(tr("Export/preview filter", "Filtro de exportación/vista", "Filtro de exportação/visualização")))
        self.filter_channel = QComboBox()
        self.filter_values = QLineEdit()
        self.filter_values.setPlaceholderText(tr("Values separated by commas", "Valores separados por comas", "Valores separados por vírgulas"))
        filtering.addWidget(self.filter_channel)
        filtering.addWidget(self.filter_values)
        body.addLayout(filtering)
        actions = QGridLayout()
        body.addLayout(actions)
        for index, (labels, callback) in enumerate((
            (("Preview", "Vista previa", "Prévia"), self.preview),
            (("Calculate…", "Calcular…", "Calcular…"), self.calculate),
            (("Duplicate…", "Duplicar…", "Duplicar…"), self.duplicate),
            (("Rename / units…", "Renombrar / unidades…", "Renomear / unidades…"), self.rename),
            (("Export CSV", "Exportar CSV", "Exportar CSV"), self.export),
            (("To QGIS points…", "A puntos QGIS…", "Para pontos QGIS…"), self.to_qgis),
            (("History", "Historial", "Histórico"), self.history),
            (("Coordinates and CRS…", "Coordenadas y CRS…", "Coordenadas e SRC…"), self.coordinates),
            (("Filter channel…", "Filtrar canal…", "Filtrar canal…"), self.filter_signal),
            (("Channel pipeline…", "Pipeline del canal…", "Pipeline do canal…"), self.channel_pipeline),
        )):
            button = QPushButton(tr(*labels))
            button.clicked.connect(callback)
            actions.addWidget(button, index // 4, index % 4)
        self.table = QTableWidget()
        self.table.setEditTriggers(qt_enum(QAbstractItemView, "EditTrigger", "NoEditTriggers"))
        body.addWidget(self.table)
        self.status = QLabel(tr("Immutable originals · versioned channels · PyArrow/Parquet + SQLite",
            "Originales inmutables · canales versionados · PyArrow/Parquet + SQLite",
            "Originais imutáveis · canais versionados · PyArrow/Parquet + SQLite"))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
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

    def new_project(self):
        parent = QFileDialog.getExistingDirectory(self, tr("Parent folder", "Carpeta contenedora", "Pasta principal"))
        if not parent:
            return
        name, ok = QInputDialog.getText(self, tr("New project", "Nuevo proyecto", "Novo projeto"), tr("Folder name", "Nombre de carpeta", "Nome da pasta"))
        if not ok or not name.strip():
            return
        if name in (".", "..") or any(c in name for c in '/\\:*?"<>|'):
            self.fail(tr("Invalid folder name", "Nombre de carpeta inválido", "Nome de pasta inválido"))
            return
        try:
            self.set_project(Path(parent) / name, create=True)
        except Exception as error:
            self.fail(str(error))

    def open_project(self):
        path = QFileDialog.getExistingDirectory(self, tr("Project folder", "Carpeta de proyecto", "Pasta do projeto"))
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
        self.channels_list.clear()
        self.filter_channel.clear()
        self.filter_channel.addItem("—", None)
        ids = self.selected_databases()
        if not ids or not self.store:
            return
        rows = self.store.channels(ids[0])
        common = {c["name"] for c in rows}
        for database in ids[1:]:
            common.intersection_update(c["name"] for c in self.store.channels(database))
        for row in rows:
            if row["name"] not in common:
                continue
            suffix = f" · {row['data_type']} · {row['unit']} · v{row['number']}" if len(ids) == 1 else ""
            item = QListWidgetItem(row["name"] + suffix)
            item.setData(256, row["name"])
            self.channels_list.addItem(item)
            item.setSelected(row["name"] in selected)
            self.filter_channel.addItem(row["name"], row["name"])
        self.filter_channel.setCurrentIndex(max(0, self.filter_channel.findData(filter_name)))

    def require_selection(self, channels=True, single=False):
        ids, names = self.selected_databases(), self.selected_channels()
        if not self.store or not ids or (channels and not names) or (single and len(ids) != 1):
            self.fail(tr("Select a project, database(s) and channel(s); this action may require one database.",
                "Selecciona un proyecto, bases y canales; esta acción puede requerir una sola base.",
                "Selecione um projeto, bancos e canais; esta ação pode exigir apenas um banco."))
            return None
        return ids, names

    def filters(self):
        key = self.filter_channel.currentData()
        return {key: [v.strip() for v in self.filter_values.text().split(",") if v.strip()]} if key else {}

    def start(self, operation, success=None):
        if self.worker is not None:
            return
        self.controls.setEnabled(False)
        self.progress_dialog = QProgressDialog(tr("Working…", "Procesando…", "Processando…"), tr("Cancel", "Cancelar", "Cancelar"), 0, 0, self)
        self.worker = StoreWorker(operation, self)
        self.progress_dialog.canceled.connect(self.worker.requestInterruption)
        self.worker.progress.connect(lambda n: self.progress_dialog.setLabelText(tr("Rows: ", "Filas: ", "Linhas: ") + n))
        self.worker.completed.connect(lambda result: self.completed(result, success))
        self.worker.failed.connect(self.fail)
        self.worker.finished.connect(self.finished)
        self.progress_dialog.show()
        self.worker.start()

    def completed(self, result, callback):
        self.status.setText(str(result))
        self.refresh()
        if callback:
            try:
                callback(result)
            except Exception as error:
                self.fail(str(error))

    def finished(self):
        self.progress_dialog.close()
        self.progress_dialog.deleteLater()
        self.worker.deleteLater()
        self.worker = None
        self.controls.setEnabled(True)
        self.refresh()
        if self._dispose:
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
        self.hide()
        if self.worker is not None:
            self.worker.requestInterruption()
        else:
            self.deleteLater()

    def import_files(self):
        if not self.store:
            self.fail(tr("Create or open a project first.", "Primero crea o abre un proyecto.", "Crie ou abra um projeto primeiro."))
            return
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Import observations", "Importar observaciones", "Importar observações"), "", "Survey text / Parquet (*.csv *.tsv *.txt *.asc *.dat *.xyz *.parquet);;All files (*)")
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
                    results.append(store.import_file(path, name=name, canceled=cancel, progress=progress, text_options=text_options.get(path)))
                    used_names.add(name)
                except Exception as error:
                    raise RuntimeError(f"{len(results)}/{len(paths)} imported; {Path(path).name}: {error}") from error
            return tr("Imported databases: ", "Bases importadas: ", "Bancos importados: ") + str(len(results))
        self.start(run)

    def preview(self):
        selection = self.require_selection(single=True)
        if not selection:
            return
        ids, names = selection
        store, filters = self.store, self.filters()
        def run(cancel, progress):
            import pyarrow as pa
            batches = store.batches(ids[0], names, batch_size=100, filters=filters, canceled=cancel)
            try:
                first = next(batches, None)
                return pa.Table.from_batches([first]).to_pydict() if first is not None else {n: [] for n in names}
            finally:
                batches.close()
        def display(result):
            self.table.clear()
            self.table.setColumnCount(len(names))
            self.table.setRowCount(len(result[names[0]]))
            self.table.setHorizontalHeaderLabels(names)
            for col, name in enumerate(names):
                for row, value in enumerate(result[name]):
                    self.table.setItem(row, col, QTableWidgetItem("" if value is None else str(value)))
            self.status.setText(tr("Preview: up to 100 rows", "Vista previa: hasta 100 filas", "Prévia: até 100 linhas"))
        self.start(run, display)

    def calculate(self):
        selection = self.require_selection(channels=False)
        if not selection:
            return
        ids, _ = selection
        name, ok = QInputDialog.getText(self, tr("Derived channel", "Canal derivado", "Canal derivado"), tr("Output name (existing derived name creates a version)", "Nombre de salida (si ya es derivado crea una versión)", "Nome de saída (se já for derivado cria uma versão)"))
        if not ok or not name.strip():
            return
        expression, ok = QInputDialog.getText(self, tr("Formula", "Fórmula", "Fórmula"), 'c("channel") * 2 + 1; abs, sqrt, log10\n' + tr("Full database; preview filter is not applied.", "Base completa; no aplica el filtro de vista previa.", "Banco completo; não aplica o filtro de prévia."))
        if not ok:
            return
        unit, ok = QInputDialog.getText(self, tr("Units", "Unidades", "Unidades"), tr("Output units", "Unidades de salida", "Unidades de saída"))
        if not ok:
            return
        store = self.store
        def run(cancel, progress):
            results = []
            for database in ids:
                try:
                    results.append(store.derive(database, name, expression, unit, cancel, progress))
                except Exception as error:
                    raise RuntimeError(f"{len(results)}/{len(ids)} completed; {database}: {error}") from error
            return results
        self.start(run)

    def duplicate(self):
        selection = self.require_selection(single=True)
        if not selection or len(selection[1]) != 1:
            return
        ids, names = selection
        name, ok = QInputDialog.getText(self, tr("Duplicate channel", "Duplicar canal", "Duplicar canal"), tr("New name", "Nuevo nombre", "Novo nome"))
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
        name, ok = QInputDialog.getText(self, tr("Rename channel", "Renombrar canal", "Renomear canal"), tr("Name", "Nombre", "Nome"), text=names[0])
        if not ok:
            return
        current = next(c for c in self.store.channels(ids[0]) if c["name"] == names[0])
        unit, ok = QInputDialog.getText(self, tr("Units", "Unidades", "Unidades"), tr("Units", "Unidades", "Unidades"), text=current["unit"])
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
            self.fail(tr("Select one channel to inspect its pipeline.", "Selecciona un canal para ver su pipeline.", "Selecione um canal para ver seu pipeline."))
            return
        from .channel_pipeline_dialog import ChannelPipelineDialog
        try:
            dialog = ChannelPipelineDialog(self.store.channel_pipeline(ids[0], names[0]), self)
            dialog.exec()
            dialog.deleteLater()
        except Exception as error:
            self.fail(str(error))

    def filter_signal(self):
        selection = self.require_selection(channels=False, single=True)
        if not selection:
            return
        from .channel_filter_dialog import ChannelFilterDialog
        ids, names = selection
        dialog = ChannelFilterDialog(self.store, ids[0], names[0] if names else "", self)
        if dialog.exec() == qt_enum(QDialog, "DialogCode", "Accepted"):
            store, options = self.store, dialog.options
            source, output = dialog.input_name, dialog.output_name
            def run(cancel, progress):
                return store.filter_channel(ids[0], source, output, options, cancel, progress)
            def display(result):
                for index in range(self.channels_list.count()):
                    item = self.channels_list.item(index)
                    item.setSelected(item.data(256) == output)
                self.status.setText(tr(
                    "Created {output}: {rows} rows; {output_null_rows} null outputs; {short_segments} short segments; {spikes_replaced} spikes replaced. Open Channel pipeline to inspect.",
                    "Creado {output}: {rows} filas; {output_null_rows} salidas nulas; {short_segments} tramos cortos; {spikes_replaced} picos reemplazados. Abre Pipeline del canal para inspeccionar.",
                    "Criado {output}: {rows} linhas; {output_null_rows} saídas nulas; {short_segments} trechos curtos; {spikes_replaced} picos substituídos. Abra Pipeline do canal para inspecionar.").format(**result))
            self.start(run, display)
        dialog.deleteLater()

    def coordinates(self):
        selection = self.require_selection(channels=False, single=True)
        if not selection:
            return
        from .survey_coordinates_dialog import SurveyCoordinatesDialog, coordinate_operation
        database_id = selection[0][0]
        dialog = SurveyCoordinatesDialog(self.store, database_id, self)
        if dialog.exec() == qt_enum(QDialog, "DialogCode", "Accepted"):
            request = dialog.request
            if "target" in request:
                self.start(coordinate_operation(self.store, database_id, request, dialog.context))
            else:
                try:
                    self.store.configure_geometry(database_id, request["x"], request["y"], request["source"])
                    self.status.setText(tr("CRS assigned; coordinate values unchanged.",
                        "CRS asignado; valores de coordenadas sin cambios.", "SRC atribuído; valores das coordenadas sem alterações."))
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
        metadata = json.loads(next(row for row in self.store.databases() if row["id"] == ids[0])["metadata"])
        roles = metadata.get("channel_roles", {})
        geometry = metadata.get("geometry", {})
        configured_axes = [channel_names.get(geometry.get(axis + "_channel_id")) for axis in ("x", "y")]
        configured_crs = QgsCoordinateReferenceSystem(geometry.get("crs", ""))
        use_configured = all(configured_axes) and configured_crs.isValid()
        axes = []
        for label in ("X", "Y"):
            suggested = channel_names.get(geometry.get(label.lower() + "_channel_id", roles.get(label.lower())), "")
            index = fields.index(suggested) if suggested in fields else 0
            field, ok = (suggested, True) if use_configured else QInputDialog.getItem(self, "QGIS", label, fields, index, False)
            if not ok:
                return
            axes.append(field)
        if axes[0] == axes[1]:
            self.fail("X and Y must be different channels.")
            return
        crs_text, ok = (geometry["crs"], True) if use_configured else QInputDialog.getText(self, "QGIS", "CRS (EPSG:...) — " + tr("required", "obligatorio", "obrigatório"), text=geometry.get("crs", ""))
        crs = QgsCoordinateReferenceSystem(crs_text)
        if not ok:
            return
        if not crs.isValid():
            self.fail(tr("Invalid CRS", "CRS inválido", "SRC inválido"))
            return
        store, filters = self.store, self.filters()
        try:
            store.configure_geometry(ids[0], axes[0], axes[1], crs.authid() or crs.toWkt())
        except Exception as error:
            self.fail(str(error))
            return
        path = store.root / "results" / f"points_{uuid.uuid4().hex}.csv"
        columns = list(dict.fromkeys([*axes, *names]))
        def run(cancel, progress):
            return store.export_csv(ids[0], columns, path, filters, cancel, progress)
        def load(result):
            url, query = QUrl.fromLocalFile(str(path)), QUrlQuery()
            for key, value in {"type": "csv", "delimiter": ",", "xField": axes[0], "yField": axes[1],
                               "crs": crs.authid() or crs.toWkt(), "detectTypes": "yes", "decimalPoint": "."}.items():
                query.addQueryItem(key, value)
            url.setQuery(query)
            layer = QgsVectorLayer(url.toString(), path.stem, "delimitedtext")
            if not layer.isValid():
                raise ValueError("QGIS could not load the exported points.")
            if layer.featureCount() != result:
                raise ValueError("Some exported rows have invalid coordinates. Inspect the CSV before gridding; the incomplete layer was not added.")
            layer.setCustomProperty("TerraWorkbench/surveyDatabase", ids[0])
            QgsProject.instance().addMapLayer(layer)
        self.start(run, load)

    def history(self):
        selection = self.require_selection(channels=False, single=True)
        if selection:
            rows = self.store.history(selection[0][0])
            dialog = QMessageBox(self)
            dialog.setWindowTitle(tr("History", "Historial", "Histórico"))
            dialog.setText(tr("Operations recorded: ", "Operaciones registradas: ", "Operações registradas: ") + str(len(rows)))
            dialog.setDetailedText(json.dumps(rows, ensure_ascii=False, indent=2))
            dialog.exec()
