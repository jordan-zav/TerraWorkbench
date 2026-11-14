"""Dockable acquisition-line editor."""

import numpy as np
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
    QgsPointXY,
    QgsProject,
)
from qgis.gui import QgsVertexMarker

from ..qgis_plugin.qgis_compat import qt_enum
from ..terraworkbench_core.profile_distance import along_profile_distance
from ..terraworkbench_core.survey_map import _line_label, survey_map_channels
from ..terraworkbench_core.survey_profile_edits import (
    ProfileEdits,
    publish_profile_edits,
)
from .profile_canvas import ProfileCanvas
from .survey_sheet import background, line_spans, tr

CHECKED = qt_enum(Qt, "CheckState", "Checked")
UNCHECKED = qt_enum(Qt, "CheckState", "Unchecked")


class SurveyProfileDock(QDockWidget):
    """Navigate survey lines, edit full-resolution samples and publish derivatives."""

    published = pyqtSignal()
    mapPickRequested = pyqtSignal()

    def __init__(self, parent, canvas=None):
        super().__init__(parent)
        self.setObjectName("TerraWorkbenchProfiles")
        self.canvas = canvas
        self.context = None
        self._generation = 0
        self._drafts = {}
        self._data = {}
        self._lines = {}
        self._preview = None
        self._positions = np.empty(0, dtype=int)
        self._fourth = False
        self._saving = False
        self._marker = self._transform = None
        self._labels = []
        self._map_point = None
        body = QWidget()
        self.setWidget(body)
        layout = QVBoxLayout(body)
        top = QHBoxLayout()
        layout.addLayout(top)
        self._button(top, ("‹", "‹", "‹"), lambda: self.navigate(-1))
        self.line = QComboBox()
        top.addWidget(self.line, 1)
        self._button(top, ("›", "›", "›"), lambda: self.navigate(1))
        self.axis = QComboBox()
        top.addWidget(self.axis)
        self._button(
            top, ("Fit", "Ajustar", "Ajustar"), lambda: self.redraw(reset=True)
        )
        if canvas is not None:
            self._button(
                top,
                ("Pick on map", "Elegir en mapa", "Escolher no mapa"),
                self.mapPickRequested.emit,
            )

        middle = QHBoxLayout()
        layout.addLayout(middle, 1)
        self.channels = QListWidget()
        self.channels.setMaximumWidth(155)
        middle.addWidget(self.channels)
        self.plot = ProfileCanvas()
        middle.addWidget(self.plot, 1)
        self.status, self.stats = QLabel(), QLabel()
        for label in (self.status, self.stats):
            label.setWordWrap(True)
            layout.addWidget(label)
        edits = QHBoxLayout()
        layout.addLayout(edits)
        self._button(edits, ("Dummy", "Dummy", "Dummy"), lambda: self.edit("dummy"))
        self._button(edits, ("Undo", "Deshacer", "Desfazer"), lambda: self.edit("undo"))
        self._button(edits, ("Redo", "Rehacer", "Refazer"), lambda: self.edit("redo"))
        self._menu(
            edits,
            ("Interpolate", "Interpolar", "Interpolar"),
            (
                (("Linear", "Lineal", "Linear"), lambda: self.edit("linear")),
                (("Akima", "Akima", "Akima"), lambda: self.edit("akima")),
            ),
        )
        self._menu(
            edits,
            ("Tools", "Herramientas", "Ferramentas"),
            (
                (
                    ("Median / MAD…", "Mediana / MAD…", "Mediana / MAD…"),
                    lambda: self.preview_spikes(True),
                ),
                (
                    ("Absolute threshold…", "Umbral absoluto…", "Limiar absoluto…"),
                    lambda: self.preview_spikes(False),
                ),
                (
                    ("Fourth difference", "Cuarta diferencia", "Quarta diferença"),
                    self.toggle_fourth,
                ),
            ),
        )
        self.apply = self._button(
            edits,
            ("Apply preview", "Aplicar vista previa", "Aplicar prévia"),
            self.apply_preview,
        )
        edits.addStretch(1)
        self.save = self._button(
            edits,
            ("Save channel…", "Guardar canal…", "Salvar canal…"),
            self.save_channel,
        )
        self.line.currentIndexChanged.connect(self.load_line)
        self.axis.currentIndexChanged.connect(lambda: self.redraw(reset=True))
        self.channels.itemChanged.connect(self.load_line)
        self.channels.currentItemChanged.connect(self._activate)
        self.plot.selected.connect(self.update_statistics)
        self.plot.hovered.connect(self.mark_map)
        self.plot.navigate.connect(self.navigate)
        self.plot.channelClicked.connect(self._select_channel)
        self.visibilityChanged.connect(self._visibility)
        self.retranslate()

    def _button(self, layout, labels, callback=None):
        button = QPushButton()
        self._labels.append((button.setText, labels))
        if callback:
            button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def _menu(self, layout, labels, items):
        button = self._button(layout, labels)
        menu = QMenu(button)
        for labels, callback in items:
            action = menu.addAction("")
            self._labels.append((action.setText, labels))
            action.triggered.connect(callback)
        button.setMenu(menu)

    def retranslate(self):
        """Refresh interface text in the active language."""
        self.setWindowTitle(tr("Profiles", "Perfiles", "Perfis"))
        for setter, labels in self._labels:
            setter(tr(*labels))
        for index in range(self.axis.count()):
            self.axis.setItemText(index, self._axis_caption(self.axis.itemData(index)))
        self.redraw()

    @staticmethod
    def _axis_caption(key):
        return {
            "distance": tr("Distance (m)", "Distancia (m)", "Distância (m)"),
            "fiducial": tr("Fiducial", "Fiducial", "Fiducial"),
            "sample": tr("Sample", "Muestra", "Amostra"),
        }[key]

    def open_survey(
        self,
        store,
        database,
        *,
        line=None,
        field=None,
        channels=(),
        indexed=None,
        point=None,
    ):
        """Open a database at an optional line and map position."""
        if self._saving:
            return
        roles, metadata = survey_map_channels(store, database)
        field = field or roles.line
        self.show()
        if not field:
            self.status.setText(
                tr(
                    "Choose a line channel.",
                    "Elige un canal de línea.",
                    "Escolha um canal de linha.",
                )
            )
            return
        snapshots = {row["name"]: row for row in store._sheet_channels(database)}
        context = (store.root, database, field, roles, snapshots[field]["version_id"])
        self._map_point = point
        if context == self.context and snapshots == self._snapshots and self._lines:
            if channels:
                self._fill_channels(channels)
            self._select_line(line)
            return
        self.context = context
        self.store, self.database, self.roles = store, database, roles
        self._snapshots = snapshots
        self._lines, self._data = {}, {}
        self._generation += 1
        self._fill_channels(channels)
        self.axis.blockSignals(True)
        self.axis.clear()
        keys = ["fiducial"] if roles.fiducial else []
        if roles.x and roles.y and roles.crs:
            keys.append("distance")
        for key in [*keys, "sample"]:
            self.axis.addItem(self._axis_caption(key), key)
        self.axis.blockSignals(False)
        self.status.setText(tr("Reading lines…", "Leyendo líneas…", "Lendo linhas…"))
        self.redraw(reset=True)
        key = self._generation, line
        if indexed is not None:
            self._index_ready(key, indexed, None)
        else:
            background(
                key,
                lambda: line_spans(
                    store,
                    database,
                    field,
                    roles.line_type,
                    metadata,
                    None,
                ),
                self._index_ready,
            )

    def _fill_channels(self, selected):
        self.channels.blockSignals(True)
        self.channels.clear()
        roles = {
            self.roles.x,
            self.roles.y,
            self.roles.fiducial,
            self.roles.time,
            self.context[2],
        }
        names = [
            name
            for name, row in self._snapshots.items()
            if row["data_type"].startswith(
                ("int", "uint", "float", "double", "decimal")
            )
        ]
        selected = [name for name in selected if name in names]
        if not selected and names:
            selected = [next((name for name in names if name not in roles), names[0])]
        for index, name in enumerate(names):
            self.channels.addItem(name)
            self.channels.item(index).setCheckState(
                CHECKED if name in selected else UNCHECKED
            )
        if selected:
            self._select_channel(selected[0])
        self.channels.blockSignals(False)

    def _index_ready(self, key, result, error):
        generation, line = key
        if generation != self._generation:
            return
        self._lines = result or {}
        self.line.blockSignals(True)
        self.line.clear()
        for value in self._lines:
            self.line.addItem(str(value), value)
        self.line.blockSignals(False)
        if self._lines:
            self._select_line(line)
        else:
            self.status.setText(error or tr("No lines", "Sin líneas", "Sem linhas"))

    def _select_line(self, line):
        index = next(
            (
                i
                for i, key in enumerate(self._lines)
                if line is not None and _line_label(key) == _line_label(line)
            ),
            -1,
        )
        if index >= 0 and index != self.line.currentIndex():
            self.line.setCurrentIndex(index)
        else:
            self.load_line()

    def navigate(self, step):
        """Move to the neighboring line in catalogue order."""
        index = self.line.currentIndex() + step
        if 0 <= index < self.line.count():
            self.line.setCurrentIndex(index)

    def _checked(self):
        return [
            self.channels.item(i).text()
            for i in range(self.channels.count())
            if self.channels.item(i).checkState() == CHECKED
        ]

    def _select_channel(self, name):
        for index in range(self.channels.count()):
            if self.channels.item(index).text() == name:
                self.channels.setCurrentRow(index)
                break

    def _active(self):
        item = self.channels.currentItem()
        return item.text() if item else ""

    def _activate(self, *_):
        self._preview = None
        self.redraw()

    def load_line(self, *_):
        """Load checked channels and geometry from pinned Parquet versions."""
        if not self._lines:
            return
        line = self.line.currentData()
        names = self._checked()
        roles, store = self.roles, self.store
        fields = dict.fromkeys(filter(None, [*names, roles.x, roles.y, roles.fiducial]))
        snapshot = [self._snapshots[name] for name in fields]
        spans = self._lines[line][0]
        self._generation += 1
        self._data = {}
        self._preview = None
        self._visibility(False)
        self.redraw(reset=True)
        self.status.setText(
            tr("Reading samples…", "Leyendo muestras…", "Lendo amostras…")
        )

        def read():
            positions = [
                position for start, stop in spans for position in range(start, stop)
            ]
            rows = store._sheet_rows(snapshot, positions)
            arrays = {
                name: np.asarray(values, dtype=float) for name, values in rows.items()
            }
            axes = {"sample": np.arange(1, len(positions) + 1, dtype=float)}
            if roles.fiducial:
                axes["fiducial"] = arrays[roles.fiducial]
            return np.asarray(positions), arrays, axes, names

        background(self._generation, read, self._line_ready)

    def _key(self, name, line):
        fields = dict.fromkeys(
            filter(
                None,
                (
                    name,
                    self.roles.fiducial,
                    self.roles.x,
                    self.roles.y,
                ),
            )
        )
        versions = tuple(self._snapshots[field]["version_id"] for field in fields)
        return self.context, name, versions, line

    def _line_ready(self, generation, result, error):
        if generation != self._generation:
            return
        if error:
            self.status.setText(error)
            return
        self._positions, self._arrays, self._axes, names = result
        self.status.clear()
        roles = self.roles
        if roles.x and roles.y and roles.crs:
            x, y = self._arrays[roles.x], self._arrays[roles.y]
            self._axes["distance"] = np.full(x.shape, np.nan)
            if (np.isfinite(x) & np.isfinite(y)).any():
                try:
                    # QGIS LTR on Windows can crash initializing pyproj in pooled threads.
                    self._axes["distance"] = along_profile_distance(x, y, roles.crs)
                except (ValueError, ImportError) as error:
                    self.status.setText(str(error))
        for name in names:
            key = self._key(name, self.line.currentData())
            draft = self._drafts.get(key)
            self._data[name] = draft[1] if draft else ProfileEdits(self._arrays[name])
        if names and self._active() not in names:
            self._select_channel(names[0])
        self.redraw(reset=True)
        if self._map_point is not None:
            point, crs = self._map_point
            self._map_point = None
            self.mark_profile(point, crs)

    def redraw(self, *, reset=False):
        """Redraw the visible tracks and their selection."""
        active = self._active()
        series = {}
        for name, model in self._data.items():
            unit = self._snapshots[name]["unit"]
            series[name] = (f"{name} ({unit})" if unit else name, model.values)
        if self._fourth and active in self._data:
            caption = tr("Fourth difference", "Cuarta diferencia", "Quarta diferença")
            series[""] = (caption, self._data[active].fourth_difference())
        key = self.axis.currentData()
        axis = self._axes[key] if self._data else np.empty(0)
        preview = (
            self._preview[0] if self._preview is not None else np.empty(0, dtype=int)
        )
        self.plot.set_data(
            axis, series, self.axis.currentText(), active, preview, reset=reset
        )
        self.apply.setVisible(self._preview is not None)
        self.save.setEnabled(active in self._data and not self._saving)
        self.update_statistics()

    def update_statistics(self, *_):
        """Summarize the selected full-resolution samples."""
        model = self._data.get(self._active())
        if model is None or self.plot.selection is None:
            self.stats.clear()
            return
        valid, dummy, low, high, mean, sd = model.statistics(*self.plot.selection)
        self.stats.setText(
            tr(
                "{n} valid · {d} dummy · Min {low:.5g} · Max {high:.5g} · Mean {mean:.5g} · SD {sd:.5g}",
                "{n} válidas · {d} dummy · Mín {low:.5g} · Máx {high:.5g} · Media {mean:.5g} · DE {sd:.5g}",
                "{n} válidas · {d} dummy · Mín {low:.5g} · Máx {high:.5g} · Média {mean:.5g} · DP {sd:.5g}",
            ).format(n=valid, d=dummy, low=low, high=high, mean=mean, sd=sd)
        )

    def edit(self, method):
        """Edit the active channel or navigate its undo history."""
        model = self._data.get(self._active())
        if model is None or self._saving:
            return
        selection = self.plot.selection
        try:
            if method == "undo":
                model.undo()
            elif method == "redo":
                model.redo()
            elif method == "dummy":
                if selection:
                    model.dummy(*selection)
            else:
                axis = self.axis.currentData()
                model.interpolate(
                    self._axes[axis],
                    *(selection or (0, model.values.size - 1)),
                    method,
                    axis_name=axis,
                )
        except ValueError as error:
            self.status.setText(str(error))
            return
        self._remember_edit(model)
        self._preview = None
        self.status.clear()
        self.redraw()

    def _remember_edit(self, model):
        key = self._key(self._active(), self.line.currentData())
        self._drafts[key] = self._positions, model

    def preview_spikes(self, relative):
        """Highlight outliers for review before applying dummies."""
        model = self._data.get(self._active())
        if model is None or self._saving:
            return
        label = (
            tr("MAD multiplier", "Multiplicador MAD", "Multiplicador MAD")
            if relative
            else tr("Channel units", "Unidades del canal", "Unidades do canal")
        )
        threshold, ok = QInputDialog.getDouble(
            self, self.windowTitle(), label, 3, 0.000001, 1e12, 6
        )
        if ok:
            indices = model.spike_candidates(threshold, relative=relative)
            if self.plot.selection:
                first, last = self.plot.selection
                indices = indices[(indices >= first) & (indices <= last)]
            self._preview = indices, threshold, relative
            self.status.setText(
                tr("Candidates: {}", "Candidatos: {}", "Candidatos: {}").format(
                    len(indices)
                )
            )
            self.redraw()

    def apply_preview(self):
        """Mark reviewed candidates dummy as one reversible operation."""
        if self._preview is not None and not self._saving:
            indices, threshold, relative = self._preview
            model = self._data[self._active()]
            model.apply_spikes(indices, threshold, relative=relative)
            self._remember_edit(model)
            self._preview = None
            self.status.clear()
            self.redraw()

    def toggle_fourth(self):
        """Toggle the centered fourth-difference track."""
        self._fourth = not self._fourth
        self.redraw()

    def save_channel(self):
        """Publish the active channel's edits across all visited lines."""
        name = self._active()
        if name not in self._data or self._saving:
            return
        edits = []
        fields = {name, self.context[2]}
        versions = self._key(name, self.line.currentData())[2]
        for (context, channel, source_versions, line), (
            positions,
            model,
        ) in self._drafts.items():
            if (context, channel, source_versions) != (self.context, name, versions):
                continue
            indices, values = model.changes()
            if indices.size:
                edits.append(
                    (
                        positions[indices],
                        values,
                        {
                            "line": str(line),
                            "physical_rows": positions[indices].tolist(),
                            "operations": model.operations,
                        },
                    )
                )
                axes = {operation.get("axis") for operation in model.operations}
                if "fiducial" in axes:
                    fields.add(self.roles.fiducial)
                if "distance" in axes:
                    fields.update((self.roles.x, self.roles.y))
        if not edits:
            self.status.setText(
                tr(
                    "No edits to save.",
                    "No hay cambios que guardar.",
                    "Sem edições para salvar.",
                )
            )
            return
        caption = tr("New channel", "Canal nuevo", "Novo canal")
        output, ok = QInputDialog.getText(
            self, self.windowTitle(), caption, text=name + "_edited"
        )
        if not ok or not output.strip():
            return
        store, database = self.store, self.database
        unit = self._snapshots[name]["unit"]
        inputs = {field: self._snapshots[field]["version_id"] for field in fields}
        self._saving = True
        self.redraw()
        background(
            output.strip(),
            lambda: publish_profile_edits(
                store,
                database,
                name,
                output.strip(),
                inputs,
                unit,
                edits,
            ),
            self._saved,
        )

    def _saved(self, output, result, error):
        self._saving = False
        if not error:
            for row in self.store.channels(self.database):
                self._snapshots.setdefault(row["name"], row)
            active = self._active()
            self._fill_channels(self._checked())
            self.channels.blockSignals(True)
            self._select_channel(active)
            self.channels.blockSignals(False)
            self.published.emit()
        self.status.setText(
            error or tr("Saved {}", "Guardado {}", "Salvo {}").format(output)
        )
        self.redraw()

    def mark_map(self, sample):
        """Place a QGIS marker at the exact hovered sample."""
        roles = self.roles
        if self.canvas is None or not (roles.crs and roles.x and roles.y):
            return
        x, y = self._arrays[roles.x][sample], self._arrays[roles.y][sample]
        if not np.isfinite([x, y]).all():
            self._visibility(False)
            return
        target = self.canvas.mapSettings().destinationCrs()
        key = roles.crs, target
        if self._transform is None or self._transform[0] != key:
            source = QgsCoordinateReferenceSystem(roles.crs)
            self._transform = (
                key,
                QgsCoordinateTransform(source, target, QgsProject.instance()),
            )
        try:
            center = self._transform[1].transform(QgsPointXY(x, y))
        except QgsCsException:
            self._visibility(False)
            return
        if self._marker is None:
            self._marker = QgsVertexMarker(self.canvas)
            self._marker.setColor(QColor("#da652a"))
            self._marker.setIconSize(13)
            self._marker.setPenWidth(2)
        self._marker.setCenter(center)
        self._marker.show()

    def mark_profile(self, point, crs):
        """Mark the closest plottable sample to a map position."""
        roles = self.roles
        if not self._data or not (roles.crs and roles.x and roles.y):
            return
        transform = QgsCoordinateTransform(
            crs,
            QgsCoordinateReferenceSystem(roles.crs),
            QgsProject.instance(),
        )
        try:
            point = transform.transform(point)
        except QgsCsException:
            return
        x, y = self._arrays[roles.x], self._arrays[roles.y]
        distance = np.hypot(x - point.x(), y - point.y())
        distance[~np.isfinite(self.plot.axis)] = np.nan
        if np.isfinite(distance).any():
            self.plot.cursor = int(np.nanargmin(distance))
            self.plot.update()

    def _visibility(self, visible):
        if not visible and self._marker is not None:
            self._marker.hide()

    def dispose(self):
        """Release the map marker and invalidate queued profile reads."""
        self._generation += 1
        if self._marker is not None:
            self.canvas.scene().removeItem(self._marker)
            self._marker = None
