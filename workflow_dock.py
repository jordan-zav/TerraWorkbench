"""Dockable filter-stack workflow for TerraWorkbench."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re

import numpy as np

from qgis.PyQt.QtCore import QPoint, QPointF, QProcess, QRectF, Qt, QUrl, QUrlQuery
from qgis.PyQt.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen
from qgis.PyQt.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QMenu,
    QPushButton,
    QProgressDialog,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsProcessing,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingMultiStepFeedback,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsProject,
    QgsRasterLayer,
    QgsSettings,
    QgsVectorLayer,
)

from .qgis_compat import (
    PROCESSING_NUMBER_INTEGER,
    processing_parameter_is_optional,
    qt_enum,
)
from .raster_io import read_raster, to_regular_data_array
from .spectral import apply_transfer, frequency_grid, radial_power_spectrum
from .data_import import import_survey_grid, list_raster_subdatasets
from .geosoft_runtime import find_geosoft_runtime, validate_geosoft_location


PLUGIN_PREFIX = "terraworkbench:"
PIPELINE_FORMAT_VERSION = 1
_FIXED_PARAMETERS = {"INPUT", "BAND", "OUTPUT"}


@dataclass
class PipelineStep:
    """A serializable Processing algorithm invocation."""

    algorithm_id: str
    parameters: dict[str, int | float | None] = field(default_factory=dict)

    def to_dict(self):
        return {
            "algorithm": self.algorithm_id,
            "parameters": dict(self.parameters),
        }

    @classmethod
    def from_dict(cls, value):
        algorithm_id = str(value.get("algorithm", ""))
        parameters = value.get("parameters", {})
        if not algorithm_id.startswith(PLUGIN_PREFIX) or not isinstance(
            parameters, dict
        ):
            raise ValueError("Invalid TerraWorkbench pipeline step")
        if _FIXED_PARAMETERS.intersection(parameters):
            raise ValueError("Pipeline steps cannot override input, band or output")
        return cls(algorithm_id, dict(parameters))


def available_algorithms():
    """Return registered TerraWorkbench algorithms in display order."""
    algorithms = [
        algorithm
        for algorithm in QgsApplication.processingRegistry().algorithms()
        if algorithm.id().startswith(PLUGIN_PREFIX)
        and isinstance(
            algorithm.parameterDefinition("INPUT"), QgsProcessingParameterRasterLayer
        )
    ]
    return sorted(
        algorithms, key=lambda algorithm: (algorithm.group(), algorithm.displayName())
    )


def algorithm_defaults(algorithm):
    """Return editable numeric defaults for an algorithm."""
    defaults = {}
    for parameter in algorithm.parameterDefinitions():
        if parameter.name() in _FIXED_PARAMETERS:
            continue
        if not isinstance(parameter, QgsProcessingParameterNumber):
            raise ValueError(
                f"Unsupported pipeline parameter {parameter.name()} in {algorithm.id()}"
            )
        defaults[parameter.name()] = parameter.defaultValue()
    return defaults


def _safe_output_stem(index, algorithm):
    stem = re.sub(r"[^0-9A-Za-z_-]+", "_", algorithm.name()).strip("_")
    return f"{index:02d}_{stem or 'result'}"


def run_filter_stack(
    input_raster,
    band,
    steps,
    *,
    context=None,
    feedback=None,
    output_directory=None,
    keep_intermediate=False,
):
    """Run steps sequentially, feeding each raster output into the next step."""
    if not steps:
        raise QgsProcessingException("Add at least one filter to the stack.")

    import processing

    context = context or QgsProcessingContext()
    if context.project() is None:
        context.setProject(QgsProject.instance())
    base_feedback = feedback or QgsProcessingFeedback()
    multi_feedback = QgsProcessingMultiStepFeedback(len(steps), base_feedback)
    output_path = Path(output_directory) if output_directory else None
    if output_path is not None:
        output_path.mkdir(parents=True, exist_ok=True)

    current_input = input_raster
    outputs = []
    last_index = len(steps)
    for index, step in enumerate(steps, start=1):
        if multi_feedback.isCanceled():
            raise QgsProcessingException("Filter stack was canceled.")
        algorithm = QgsApplication.processingRegistry().algorithmById(step.algorithm_id)
        if algorithm is None or not step.algorithm_id.startswith(PLUGIN_PREFIX):
            raise QgsProcessingException(
                f"Algorithm is not available: {step.algorithm_id}"
            )

        multi_feedback.setCurrentStep(index - 1)
        parameters = {
            **step.parameters,
            "INPUT": current_input,
            "BAND": int(band),
        }
        persist = output_path is not None and (keep_intermediate or index == last_index)
        if persist:
            parameters["OUTPUT"] = str(
                output_path / f"{_safe_output_stem(index, algorithm)}.tif"
            )
        else:
            parameters["OUTPUT"] = QgsProcessing.TEMPORARY_OUTPUT

        result = processing.run(
            step.algorithm_id,
            parameters,
            context=context,
            feedback=multi_feedback,
            is_child_algorithm=True,
        )
        current_input = result["OUTPUT"]
        outputs.append(current_input)

    return current_input, outputs


class SpectrumPlot(QWidget):
    """Small dependency-free Qt plot for radial power spectra."""

    def __init__(self, frequencies, original, filtered=None, parent=None):
        super().__init__(parent)
        self.frequencies = np.asarray(frequencies, dtype=float)
        self.original = np.asarray(original, dtype=float)
        self.filtered = None if filtered is None else np.asarray(filtered, dtype=float)
        self.setMinimumSize(560, 300)

    def _curve(self, painter, rectangle, values, color, lower, upper):
        logged = np.log10(np.maximum(values, np.finfo(float).tiny))
        span = max(upper - lower, np.finfo(float).eps)
        points = []
        for index, value in enumerate(logged):
            x = rectangle.left() + rectangle.width() * index / max(len(logged) - 1, 1)
            y = rectangle.bottom() - rectangle.height() * (value - lower) / span
            points.append(QPointF(x, y))
        if not points:
            return
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        painter.setPen(QPen(color, 2.0))
        painter.drawPath(path)

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(qt_enum(QPainter, "RenderHint", "Antialiasing"))
        painter.fillRect(self.rect(), self.palette().base())
        plot = QRectF(
            58.0, 18.0, max(self.width() - 82.0, 10.0), max(self.height() - 68.0, 10.0)
        )
        curves = [self.original]
        if self.filtered is not None:
            curves.append(self.filtered)
        logs = [np.log10(np.maximum(curve, np.finfo(float).tiny)) for curve in curves]
        lower = min(float(np.nanmin(curve)) for curve in logs)
        upper = max(float(np.nanmax(curve)) for curve in logs)
        painter.setPen(QPen(self.palette().mid().color(), 1.0))
        painter.drawRect(plot)
        self._curve(painter, plot, self.original, QColor("#202020"), lower, upper)
        if self.filtered is not None:
            self._curve(painter, plot, self.filtered, QColor("#d32f2f"), lower, upper)
        painter.setPen(self.palette().text().color())
        painter.drawText(8, 20, "log power")
        painter.drawText(int(plot.left()), self.height() - 16, "0")
        maximum = float(self.frequencies[-1]) if self.frequencies.size else 0.0
        painter.drawText(
            int(plot.right()) - 125,
            self.height() - 16,
            f"{maximum:.4g} rad/unit",
        )
        painter.drawText(int(plot.center().x()) - 45, self.height() - 16, "wavenumber")
        painter.setPen(QPen(QColor("#202020"), 2.0))
        painter.drawLine(65, 34, 92, 34)
        painter.setPen(self.palette().text().color())
        painter.drawText(98, 39, "Input")
        if self.filtered is not None:
            painter.setPen(QPen(QColor("#d32f2f"), 2.0))
            painter.drawLine(155, 34, 182, 34)
            painter.setPen(self.palette().text().color())
            painter.drawText(188, 39, "Predicted output")
        painter.end()


class SpectrumDialog(QDialog):
    def __init__(self, frequencies, original, filtered, note, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TerraWorkbench — Radial spectrum preview")
        layout = QVBoxLayout(self)
        description = QLabel(note)
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addWidget(SpectrumPlot(frequencies, original, filtered, self), 1)
        buttons = QDialogButtonBox(
            qt_enum(QDialogButtonBox, "StandardButton", "Close"), parent=self
        )
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class FilterStackDock(QDockWidget):
    """Right-side QGIS panel for composing sequential raster filters."""

    def __init__(self, parent=None):
        super().__init__("TerraWorkbench — Filter Stack", parent)
        self.setObjectName("TerraWorkbenchFilterStackDock")
        self.setMinimumWidth(300)
        self.setMaximumWidth(380)
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("icon.svg"))))
        self._parameter_editors = {}
        self._build_ui()
        self._connect_project()
        self.refresh_layers()
        self.refresh_algorithms()

    def _build_ui(self):
        body = QWidget(self)
        layout = QVBoxLayout(body)

        source_group = QGroupBox("Input raster")
        source_layout = QFormLayout(source_group)
        self.layer_combo = QComboBox()
        self.layer_combo.setSizeAdjustPolicy(
            qt_enum(
                QComboBox,
                "SizeAdjustPolicy",
                "AdjustToMinimumContentsLengthWithIcon",
            )
        )
        self.band_spin = QSpinBox()
        self.band_spin.setRange(1, 9999)
        self.band_spin.setValue(1)
        source_layout.addRow("Layer", self.layer_combo)
        source_layout.addRow("Band", self.band_spin)
        layout.addWidget(source_group)

        add_row = QHBoxLayout()
        self.algorithm_combo = QComboBox()
        self.algorithm_combo.setMinimumContentsLength(22)
        self.algorithm_combo.setSizeAdjustPolicy(
            qt_enum(
                QComboBox, "SizeAdjustPolicy", "AdjustToMinimumContentsLengthWithIcon"
            )
        )
        self.add_button = QPushButton("Add filter")
        add_row.addWidget(self.algorithm_combo, 1)
        add_row.addWidget(self.add_button)
        layout.addLayout(add_row)

        self.step_list = QListWidget()
        self.step_list.setAlternatingRowColors(True)
        layout.addWidget(self.step_list, 1)

        move_grid = QGridLayout()
        self.up_button = QPushButton("Up")
        self.down_button = QPushButton("Down")
        self.duplicate_button = QPushButton("Duplicate")
        self.remove_button = QPushButton("Remove")
        self.clear_button = QPushButton("Clear")
        for column, button in enumerate(
            (
                self.up_button,
                self.down_button,
                self.duplicate_button,
                self.remove_button,
            )
        ):
            move_grid.addWidget(button, 0, column)
        move_grid.addWidget(self.clear_button, 1, 3)
        layout.addLayout(move_grid)

        self.inspector = QDialog(self.parentWidget() or self)
        self.inspector.setObjectName("TerraWorkbenchFilterInspector")
        self.inspector.setWindowTitle("TerraWorkbench — Filter inspector")
        self.inspector.setWindowFlags(
            self.inspector.windowFlags() | qt_enum(Qt, "WindowType", "Tool")
        )
        self.inspector.resize(440, 620)
        inspector_layout = QVBoxLayout(self.inspector)
        tabs = QTabWidget()
        parameter_tab = QWidget()
        parameter_tab_layout = QVBoxLayout(parameter_tab)
        self.parameter_group = QGroupBox("Selected filter parameters")
        self.parameter_form = QFormLayout(self.parameter_group)
        self.empty_parameters = QLabel("Select a filter to edit its parameters.")
        self.parameter_form.addRow(self.empty_parameters)
        parameter_tab_layout.addWidget(self.parameter_group)
        parameter_tab_layout.addStretch(1)
        spectrum_tab = QWidget()
        spectrum_layout = QVBoxLayout(spectrum_tab)
        spectrum_layout.addWidget(
            QLabel(
                "Compare the radial power spectrum of the input with the predicted FFT stack."
            )
        )
        self.preview_button = QPushButton("Open spectrum preview…")
        spectrum_layout.addWidget(self.preview_button)
        spectrum_layout.addStretch(1)
        igrf_tab = QWidget()
        igrf_layout = QVBoxLayout(igrf_tab)
        igrf_note = QLabel(
            "IGRF mode 1 evaluates IGRF-14 at the raster center, survey date and altitude. "
            "Use mode 0 to enter inclination and declination manually. Positive inclination "
            "is downward; declination is clockwise from geographic North."
        )
        igrf_note.setWordWrap(True)
        igrf_layout.addWidget(igrf_note)
        igrf_layout.addStretch(1)
        tabs.addTab(parameter_tab, "Parameters")
        tabs.addTab(spectrum_tab, "Spectrum")
        tabs.addTab(igrf_tab, "IGRF")
        inspector_layout.addWidget(tabs)
        close_inspector = QPushButton("Close")
        close_inspector.clicked.connect(self.inspector.hide)
        inspector_layout.addWidget(close_inspector)
        geometry = QgsSettings().value("TerraWorkbench/filterInspectorGeometry")
        if geometry:
            self.inspector.restoreGeometry(geometry)

        output_group = QGroupBox("Outputs")
        output_layout = QGridLayout(output_group)
        self.output_directory = QLineEdit()
        self.output_directory.setPlaceholderText(
            "Temporary output (or choose a folder)"
        )
        self.output_browse = QPushButton("Browse…")
        self.keep_intermediate = QCheckBox("Save every intermediate raster")
        self.keep_intermediate.setEnabled(False)
        output_layout.addWidget(self.output_directory, 0, 0)
        output_layout.addWidget(self.output_browse, 0, 1)
        output_layout.addWidget(self.keep_intermediate, 1, 0, 1, 2)
        layout.addWidget(output_group)

        file_row = QHBoxLayout()
        self.import_button = QPushButton("Import…")
        import_menu = QMenu(self.import_button)
        import_menu.addAction("Survey grid file…", self.import_grid)
        import_menu.addAction("Esri FileGDB folder…", self.import_filegdb)
        import_menu.addAction(
            "GeoDatabase (Oasis montaj) inventory/export…", self.import_geosoft_gdb
        )
        self.import_button.setMenu(import_menu)
        self.load_button = QPushButton("Load stack…")
        self.save_button = QPushButton("Save stack…")
        self.run_button = QPushButton("Run stack")
        file_row.addWidget(self.import_button)
        file_row.addWidget(self.load_button)
        file_row.addWidget(self.save_button)
        file_row.addStretch(1)
        file_row.addWidget(self.run_button)
        layout.addLayout(file_row)

        self.setWidget(body)
        self.add_button.clicked.connect(self.add_step)
        self.step_list.currentRowChanged.connect(self.show_step_parameters)
        self.up_button.clicked.connect(lambda: self.move_step(-1))
        self.down_button.clicked.connect(lambda: self.move_step(1))
        self.duplicate_button.clicked.connect(self.duplicate_step)
        self.remove_button.clicked.connect(self.remove_step)
        self.clear_button.clicked.connect(self.step_list.clear)
        self.output_browse.clicked.connect(self.choose_output_directory)
        self.output_directory.textChanged.connect(
            lambda text: self.keep_intermediate.setEnabled(bool(text.strip()))
        )
        self.load_button.clicked.connect(self.load_stack)
        self.save_button.clicked.connect(self.save_stack)
        self.preview_button.clicked.connect(self.preview_spectrum)
        self.run_button.clicked.connect(self.run_stack)

    def _connect_project(self):
        project = QgsProject.instance()
        project.layersAdded.connect(self.refresh_layers)
        project.layersRemoved.connect(self.refresh_layers)

    def disconnect_project(self):
        project = QgsProject.instance()
        for signal in (project.layersAdded, project.layersRemoved):
            try:
                signal.disconnect(self.refresh_layers)
            except (TypeError, RuntimeError):
                pass
        QgsSettings().setValue(
            "TerraWorkbench/filterInspectorGeometry", self.inspector.saveGeometry()
        )
        self.inspector.close()

    def showEvent(self, event):
        self.refresh_layers()
        self.refresh_algorithms()
        super().showEvent(event)

    def refresh_layers(self, *_args):
        selected_id = self.layer_combo.currentData()
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        layers = [
            layer
            for layer in QgsProject.instance().mapLayers().values()
            if isinstance(layer, QgsRasterLayer) and layer.isValid()
        ]
        for layer in sorted(layers, key=lambda item: item.name().casefold()):
            self.layer_combo.addItem(layer.name(), layer.id())
        selected_index = self.layer_combo.findData(selected_id)
        if selected_index >= 0:
            self.layer_combo.setCurrentIndex(selected_index)
        self.layer_combo.blockSignals(False)

    def refresh_algorithms(self):
        selected_id = self.algorithm_combo.currentData()
        self.algorithm_combo.clear()
        for algorithm in available_algorithms():
            label = f"{algorithm.group()} — {algorithm.displayName()}"
            self.algorithm_combo.addItem(label, algorithm.id())
            self.algorithm_combo.setItemData(
                self.algorithm_combo.count() - 1,
                label,
                qt_enum(Qt, "ItemDataRole", "ToolTipRole"),
            )
        selected_index = self.algorithm_combo.findData(selected_id)
        if selected_index >= 0:
            self.algorithm_combo.setCurrentIndex(selected_index)

    def _algorithm(self, algorithm_id):
        return QgsApplication.processingRegistry().algorithmById(algorithm_id)

    def _item_step(self, item):
        return PipelineStep.from_dict(
            item.data(qt_enum(Qt, "ItemDataRole", "UserRole"))
        )

    def _set_item_step(self, item, step):
        algorithm = self._algorithm(step.algorithm_id)
        label = algorithm.displayName() if algorithm else step.algorithm_id
        item.setText(label)
        item.setToolTip(f"{algorithm.group()} — {label}" if algorithm else label)
        item.setData(qt_enum(Qt, "ItemDataRole", "UserRole"), step.to_dict())

    def steps(self):
        return [
            self._item_step(self.step_list.item(index))
            for index in range(self.step_list.count())
        ]

    def add_step(self):
        algorithm_id = self.algorithm_combo.currentData()
        algorithm = self._algorithm(algorithm_id)
        if algorithm is None:
            QMessageBox.warning(self, "TerraWorkbench", "No filter is selected.")
            return
        try:
            step = PipelineStep(algorithm_id, algorithm_defaults(algorithm))
        except ValueError as error:
            QMessageBox.warning(self, "TerraWorkbench", str(error))
            return
        item = QListWidgetItem()
        self._set_item_step(item, step)
        self.step_list.addItem(item)
        self.step_list.setCurrentItem(item)

    def move_step(self, offset):
        row = self.step_list.currentRow()
        destination = row + offset
        if row < 0 or destination < 0 or destination >= self.step_list.count():
            return
        item = self.step_list.takeItem(row)
        self.step_list.insertItem(destination, item)
        self.step_list.setCurrentRow(destination)

    def duplicate_step(self):
        item = self.step_list.currentItem()
        if item is None:
            return
        row = self.step_list.currentRow() + 1
        copy_item = QListWidgetItem()
        step = self._item_step(item)
        self._set_item_step(
            copy_item, PipelineStep(step.algorithm_id, dict(step.parameters))
        )
        self.step_list.insertItem(row, copy_item)
        self.step_list.setCurrentItem(copy_item)

    def remove_step(self):
        row = self.step_list.currentRow()
        if row >= 0:
            self.step_list.takeItem(row)

    def _clear_parameter_form(self):
        while self.parameter_form.count():
            item = self.parameter_form.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._parameter_editors.clear()

    def show_step_parameters(self, row):
        self._clear_parameter_form()
        if row < 0:
            self.parameter_form.addRow(
                QLabel("Select a filter to edit its parameters.")
            )
            return
        item = self.step_list.item(row)
        step = self._item_step(item)
        algorithm = self._algorithm(step.algorithm_id)
        if algorithm is None:
            self.parameter_form.addRow(
                QLabel("This filter is not currently available.")
            )
            return

        editable = 0
        for parameter in algorithm.parameterDefinitions():
            if parameter.name() in _FIXED_PARAMETERS:
                continue
            editor = QLineEdit()
            value = step.parameters.get(parameter.name())
            editor.setText("" if value is None else str(value))
            optional = processing_parameter_is_optional(parameter)
            editor.setPlaceholderText("Optional" if optional else "Required")
            editor.editingFinished.connect(self.update_current_parameters)
            self._parameter_editors[parameter.name()] = (editor, parameter)
            self.parameter_form.addRow(parameter.description(), editor)
            editable += 1
        if not editable:
            self.parameter_form.addRow(
                QLabel("This filter has no additional parameters.")
            )
        self._show_inspector_left()

    def _show_inspector_left(self):
        if not self.inspector.isVisible():
            dock_top_left = self.mapToGlobal(QPoint(0, 0))
            screen = QApplication.screenAt(dock_top_left)
            available = (
                screen.availableGeometry()
                if screen
                else QApplication.primaryScreen().availableGeometry()
            )
            x = max(available.left(), dock_top_left.x() - self.inspector.width() - 8)
            y = min(
                max(available.top(), dock_top_left.y()),
                available.bottom() - self.inspector.height(),
            )
            self.inspector.move(x, y)
            self.inspector.show()
        self.inspector.raise_()

    def import_grid(self):
        source, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Import survey grid",
            "",
            "Survey grids (*.grd *.GRD *.gxf *.GXF *.tif *.tiff *.asc *.xyz *.csv *.txt *.gdb);;All files (*)",
        )
        if not source:
            return
        if Path(source).suffix.lower() == ".gdb":
            self.import_geosoft_gdb(source)
            return
        self._finish_import(source)

    def _geosoft_runtime(self):
        settings = QgsSettings()
        runtime = find_geosoft_runtime(
            settings.value("TerraWorkbench/geosoftLocation", "")
        )
        if runtime:
            settings.setValue("TerraWorkbench/geosoftLocation", str(runtime.root))
            return runtime
        selected = QFileDialog.getExistingDirectory(
            self,
            "Locate the Geosoft or Oasis montaj installation folder",
            "",
        )
        if not selected:
            return None
        runtime = validate_geosoft_location(selected)
        if runtime is None:
            QMessageBox.critical(
                self,
                "TerraWorkbench",
                "That folder does not contain both bin\\omscore.exe and the bundled "
                "python\\python.exe. Choose the Geosoft Desktop Applications folder.",
            )
            return None
        settings.setValue("TerraWorkbench/geosoftLocation", str(runtime.root))
        return runtime

    def import_geosoft_gdb(self, source=None):
        if not source:
            source, _selected_filter = QFileDialog.getOpenFileName(
                self,
                "Choose GeoDatabase (Oasis montaj)",
                "",
                "GeoDatabase (Oasis montaj) (*.gdb)",
            )
        if not source:
            return
        runtime = self._geosoft_runtime()
        if runtime is None:
            return
        choice_dialog = QMessageBox(self)
        choice_dialog.setWindowTitle("GeoDatabase (Oasis montaj) export")
        choice_dialog.setText(
            "Choose what to recover from the Oasis montaj GeoDatabase."
        )
        choice_dialog.setInformativeText(
            "Full extraction writes every numeric channel to open CSV, loads the points "
            "and inventories into QGIS, and may require substantially more disk space "
            "than the compressed GDB."
        )
        inventory_button = choice_dialog.addButton(
            "Inventory only", qt_enum(QMessageBox, "ButtonRole", "ActionRole")
        )
        extract_button = choice_dialog.addButton(
            "Extract all and load into QGIS",
            qt_enum(QMessageBox, "ButtonRole", "AcceptRole"),
        )
        cancel_button = choice_dialog.addButton(
            qt_enum(QMessageBox, "StandardButton", "Cancel")
        )
        execute = getattr(choice_dialog, "exec", None) or choice_dialog.exec_
        execute()
        if choice_dialog.clickedButton() == cancel_button:
            return
        extract_all = choice_dialog.clickedButton() == extract_button
        if choice_dialog.clickedButton() not in (inventory_button, extract_button):
            return
        output = QFileDialog.getExistingDirectory(self, "Choose GDB export folder")
        if not output:
            return
        bridge = Path(__file__).with_name("geosoft_bridge.py")
        arguments = [str(bridge), "--input", str(source), "--output", str(output)]
        if extract_all:
            arguments.append("--extract-all")
        process = QProcess(self)
        progress = QProgressDialog(
            "Starting licensed Geosoft engine…", "Cancel", 0, 0, self
        )
        progress.setWindowTitle("TerraWorkbench — GeoDatabase (Oasis montaj)")
        progress.setWindowModality(qt_enum(Qt, "WindowModality", "WindowModal"))
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        self._geosoft_process = process
        self._geosoft_progress = progress

        def update_progress():
            output_text = (
                bytes(process.readAllStandardOutput()).decode(errors="replace").strip()
            )
            if output_text:
                progress.setLabelText(output_text.splitlines()[-1])

        def finished(exit_code, _exit_status):
            update_progress()
            error_text = (
                bytes(process.readAllStandardError()).decode(errors="replace").strip()
            )
            progress.close()
            process.deleteLater()
            self._geosoft_process = None
            self._geosoft_progress = None
            if exit_code == 0:
                loaded = self._load_geosoft_outputs(source, output)
                QMessageBox.information(
                    self,
                    "TerraWorkbench",
                    f"GeoDatabase (Oasis montaj) {'export' if extract_all else 'inventory'} completed.\n"
                    f"Added {loaded} open-data layer(s)/table(s) to QGIS.\n{output}\n\n"
                    "These exported files no longer require Oasis montaj.",
                )
                if extract_all and self._last_geosoft_point_layer is not None:
                    self._offer_survey_gridding(self._last_geosoft_point_layer)
            else:
                QMessageBox.critical(
                    self,
                    "TerraWorkbench",
                    "The Geosoft engine failed. Confirm that Oasis montaj is licensed for "
                    f"this user.\n\n{error_text or 'No diagnostic was returned.'}",
                )

        process.readyReadStandardOutput.connect(update_progress)
        process.finished.connect(finished)
        progress.canceled.connect(process.kill)
        progress.show()
        process.start(str(runtime.python), arguments)

    def _load_geosoft_outputs(self, source, output):
        self._last_geosoft_point_layer = None
        manifest_path = Path(output) / f"{Path(source).stem}_inventory.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return 0
        loaded = 0
        for key, suffix in (("channels_csv", "channels"), ("lines_csv", "lines")):
            path = manifest.get(key)
            if not path or not Path(path).is_file():
                continue
            url = QUrl.fromLocalFile(path)
            query = QUrlQuery()
            query.addQueryItem("type", "csv")
            query.addQueryItem("detectTypes", "yes")
            query.addQueryItem("geomType", "none")
            url.setQuery(query)
            layer = QgsVectorLayer(
                url.toString(),
                f"{Path(source).stem} — {suffix} — GeoDatabase (Oasis montaj)",
                "delimitedtext",
            )
            if layer.isValid():
                self._mark_oasis_source(layer, source, manifest)
                QgsProject.instance().addMapLayer(layer)
                loaded += 1
        csv_path = manifest.get("csv")
        x_field, y_field = manifest.get("x_field"), manifest.get("y_field")
        if csv_path and x_field and y_field and Path(csv_path).is_file():
            url = QUrl.fromLocalFile(csv_path)
            query = QUrlQuery()
            for key, value in (
                ("type", "csv"),
                ("detectTypes", "yes"),
                ("xField", x_field),
                ("yField", y_field),
                ("geomType", "point"),
                ("subsetIndex", "no"),
                ("watchFile", "no"),
            ):
                query.addQueryItem(key, value)
            url.setQuery(query)
            layer = QgsVectorLayer(
                url.toString(),
                f"{Path(source).stem} — all channels — GeoDatabase (Oasis montaj)",
                "delimitedtext",
            )
            wkt = manifest.get("coordinate_system", {}).get("wkt", "")
            if wkt:
                layer.setCrs(QgsCoordinateReferenceSystem.fromWkt(wkt))
            if layer.isValid():
                self._mark_oasis_source(layer, source, manifest)
                QgsProject.instance().addMapLayer(layer)
                self._last_geosoft_point_layer = layer
                loaded += 1
        return loaded

    def _offer_survey_gridding(self, point_layer):
        answer = QMessageBox.question(
            self,
            "Create analysis grid",
            "The GeoDatabase points are now independent from Oasis montaj. Open the "
            "gridding tool to select a channel and create a GeoTIFF for RTP/RTE and "
            "the Filter Stack?",
            qt_enum(QMessageBox, "StandardButton", "Yes")
            | qt_enum(QMessageBox, "StandardButton", "No"),
            qt_enum(QMessageBox, "StandardButton", "Yes"),
        )
        if answer != qt_enum(QMessageBox, "StandardButton", "Yes"):
            return
        fields = {name.casefold(): name for name in point_layer.fields().names()}
        preferred = ("magcom", "magdiur", "magraw", "maguncom", "srvmglev", "f_nadr")
        value_field = next((fields[name] for name in preferred if name in fields), "")
        import processing

        processing.execAlgorithmDialog(
            "terraworkbench:grid_survey_points",
            {
                "INPUT": point_layer,
                "VALUE_FIELD": value_field,
                "CELL_SIZE": 0.0,
                "METHOD": 0,
                "POWER": 2.0,
                "NEIGHBORS": 12,
                "SEARCH_RADIUS": 0.0,
            },
        )

    @staticmethod
    def _mark_oasis_source(layer, source, manifest):
        layer.setCustomProperty(
            "TerraWorkbench/sourceFormat",
            manifest.get("source_format", "GeoDatabase (Oasis montaj)"),
        )
        layer.setCustomProperty("TerraWorkbench/sourceFile", str(source))
        layer.setCustomProperty(
            "TerraWorkbench/conversionEngine",
            manifest.get("conversion_engine", "Geosoft gxpy licensed runtime"),
        )
        metadata = layer.metadata()
        metadata.setTitle(layer.name())
        metadata.setAbstract(
            "Imported from GeoDatabase (Oasis montaj) and converted to open CSV by "
            "TerraWorkbench. The exported layer is usable without Oasis montaj."
        )
        metadata.addHistoryItem(
            f"Source: GeoDatabase (Oasis montaj): {Path(source).name}"
        )
        layer.setMetadata(metadata)

    def import_filegdb(self):
        source = QFileDialog.getExistingDirectory(self, "Choose Esri FileGDB folder")
        if not source:
            return
        if Path(source).suffix.lower() != ".gdb":
            QMessageBox.warning(
                self, "TerraWorkbench", "Choose a folder ending in .gdb."
            )
            return
        subdatasets = list_raster_subdatasets(source)
        subdataset = None
        if subdatasets:
            descriptions = [description for _name, description in subdatasets]
            selected, accepted = QInputDialog.getItem(
                self, "Select FileGDB raster", "Raster dataset", descriptions, 0, False
            )
            if not accepted:
                return
            subdataset = subdatasets[descriptions.index(selected)][0]
        self._finish_import(source, subdataset)

    def _finish_import(self, source, subdataset=None):
        suggested = str(Path(source).with_suffix(".tif"))
        output, _selected_filter = QFileDialog.getSaveFileName(
            self, "Save imported GeoTIFF", suggested, "GeoTIFF (*.tif *.tiff)"
        )
        if not output:
            return
        QApplication.setOverrideCursor(qt_enum(Qt, "CursorShape", "WaitCursor"))
        try:
            imported, metadata = import_survey_grid(
                source, output, subdataset=subdataset
            )
            layer = QgsRasterLayer(imported, Path(imported).stem)
            if not layer.isValid():
                raise QgsProcessingException(
                    "The imported GeoTIFF is not a valid QGIS raster."
                )
            QgsProject.instance().addMapLayer(layer)
            details = "\n".join(
                f"{key}: {value}"
                for key, value in metadata.items()
                if key
                in {
                    "TITLE",
                    "EPSG",
                    "SURVEY_START",
                    "SURVEY_END",
                    "LINE_DIRECTION",
                    "LINE_SPACING",
                }
            )
            QMessageBox.information(
                self,
                "TerraWorkbench",
                "Grid imported and added to the map."
                + (f"\n\n{details}" if details else ""),
            )
        except (OSError, ValueError, QgsProcessingException) as error:
            QMessageBox.critical(self, "TerraWorkbench", f"Import failed:\n{error}")
        finally:
            QApplication.restoreOverrideCursor()

    def update_current_parameters(self):
        item = self.step_list.currentItem()
        if item is None:
            return True
        step = self._item_step(item)
        valid = True
        for name, (editor, parameter) in self._parameter_editors.items():
            text = editor.text().strip()
            try:
                if not text and processing_parameter_is_optional(parameter):
                    value = None
                elif parameter.dataType() == PROCESSING_NUMBER_INTEGER:
                    value = int(text) if text else parameter.defaultValue()
                else:
                    value = float(text) if text else parameter.defaultValue()
                if value is not None and not parameter.checkValueIsAcceptable(value):
                    raise ValueError
                step.parameters[name] = value
                editor.setStyleSheet("")
            except (TypeError, ValueError):
                valid = False
                editor.setStyleSheet("border: 1px solid #d32f2f;")
        self._set_item_step(item, step)
        return valid

    def choose_output_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Choose output folder", self.output_directory.text()
        )
        if directory:
            self.output_directory.setText(directory)

    def save_stack(self):
        if not self.update_current_parameters():
            QMessageBox.warning(
                self, "TerraWorkbench", "Correct the highlighted parameter values."
            )
            return
        if not self.steps():
            QMessageBox.warning(self, "TerraWorkbench", "The filter stack is empty.")
            return
        path, _selected_filter = QFileDialog.getSaveFileName(
            self, "Save filter stack", "terraworkbench-stack.json", "JSON (*.json)"
        )
        if not path:
            return
        payload = {
            "format": PIPELINE_FORMAT_VERSION,
            "steps": [step.to_dict() for step in self.steps()],
        }
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_stack(self):
        path, _selected_filter = QFileDialog.getOpenFileName(
            self, "Load filter stack", "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            if payload.get("format") != PIPELINE_FORMAT_VERSION:
                raise ValueError("Unsupported filter-stack format")
            steps = [
                PipelineStep.from_dict(value) for value in payload.get("steps", [])
            ]
            if not steps:
                raise ValueError("The saved filter stack is empty")
            missing = [
                step.algorithm_id
                for step in steps
                if self._algorithm(step.algorithm_id) is None
            ]
            if missing:
                raise ValueError(f"Unavailable filters: {', '.join(missing)}")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            QMessageBox.critical(
                self, "TerraWorkbench", f"Could not load stack:\n{error}"
            )
            return

        self.step_list.clear()
        for step in steps:
            item = QListWidgetItem()
            self._set_item_step(item, step)
            self.step_list.addItem(item)
        self.step_list.setCurrentRow(0)

    def _selected_raster(self):
        layer_id = self.layer_combo.currentData()
        layer = QgsProject.instance().mapLayer(layer_id) if layer_id else None
        return layer if isinstance(layer, QgsRasterLayer) and layer.isValid() else None

    def preview_spectrum(self):
        if not self.update_current_parameters():
            QMessageBox.warning(
                self, "TerraWorkbench", "Correct the highlighted parameter values."
            )
            return
        layer = self._selected_raster()
        if layer is None:
            QMessageBox.warning(
                self, "TerraWorkbench", "Choose a valid input raster layer."
            )
            return

        QApplication.setOverrideCursor(qt_enum(Qt, "CursorShape", "WaitCursor"))
        try:
            grid = read_raster(layer, self.band_spin.value())
            orientation = to_regular_data_array(grid)
            data = orientation.data
            northing = np.asarray(data.coords["northing"])
            easting = np.asarray(data.coords["easting"])
            spacing_northing = abs(float(northing[1] - northing[0]))
            spacing_easting = abs(float(easting[1] - easting[0]))
            frequencies, original_power = radial_power_spectrum(
                data.values, spacing_northing, spacing_easting
            )

            from .algorithms.spectral_filters import SpectralFilterBase

            context = QgsProcessingContext()
            context.setProject(QgsProject.instance())
            k_east, k_north, radial = frequency_grid(
                data.shape, spacing_northing, spacing_easting
            )
            combined = np.ones(data.shape, dtype=np.complex128)
            spectral_steps = True
            preview_feedback = QgsProcessingFeedback()
            for step in self.steps():
                algorithm = self._algorithm(step.algorithm_id)
                if not isinstance(algorithm, SpectralFilterBase):
                    spectral_steps = False
                    break
                algorithm.prepare(grid, step.parameters, context, preview_feedback)
                combined *= algorithm.transfer(
                    k_east, k_north, radial, step.parameters, context
                )

            if spectral_steps and self.steps():
                predicted = apply_transfer(data.values, combined)
                _frequencies, filtered_power = radial_power_spectrum(
                    predicted, spacing_northing, spacing_easting
                )
                note = (
                    "Black: input radial power spectrum. Red: predicted result from "
                    "the combined FFT spectral filters in this stack."
                )
            else:
                filtered_power = None
                note = (
                    "Input radial power spectrum. A predicted output is shown only "
                    "when every stack step belongs to the FFT spectral filters group."
                )
        except (OSError, ValueError, QgsProcessingException) as error:
            QMessageBox.critical(
                self, "TerraWorkbench", f"Spectrum preview failed:\n{error}"
            )
            return
        finally:
            QApplication.restoreOverrideCursor()

        dialog = SpectrumDialog(frequencies, original_power, filtered_power, note, self)
        execute = getattr(dialog, "exec", None) or dialog.exec_
        execute()

    def run_stack(self):
        if not self.update_current_parameters():
            QMessageBox.warning(
                self, "TerraWorkbench", "Correct the highlighted parameter values."
            )
            return
        layer = self._selected_raster()
        if layer is None:
            QMessageBox.warning(
                self, "TerraWorkbench", "Choose a valid input raster layer."
            )
            return
        steps = self.steps()
        if not steps:
            QMessageBox.warning(self, "TerraWorkbench", "Add at least one filter.")
            return

        output_directory = self.output_directory.text().strip() or None
        progress = QProgressDialog("Running filter stack…", "Cancel", 0, 100, self)
        progress.setWindowModality(qt_enum(Qt, "WindowModality", "WindowModal"))
        progress.setMinimumDuration(0)
        feedback = QgsProcessingFeedback()
        feedback.progressChanged.connect(lambda value: progress.setValue(int(value)))
        progress.canceled.connect(feedback.cancel)
        progress.show()
        QApplication.setOverrideCursor(qt_enum(Qt, "CursorShape", "WaitCursor"))
        try:
            final_output, outputs = run_filter_stack(
                layer,
                self.band_spin.value(),
                steps,
                feedback=feedback,
                output_directory=output_directory,
                keep_intermediate=self.keep_intermediate.isChecked(),
            )
            if feedback.isCanceled():
                return
            result_layer = QgsRasterLayer(
                str(final_output),
                f"TerraWorkbench — {steps[-1].algorithm_id.split(':', 1)[1]}",
            )
            if not result_layer.isValid():
                raise QgsProcessingException(
                    f"The final output is invalid: {final_output}"
                )
            QgsProject.instance().addMapLayer(result_layer)
            QMessageBox.information(
                self,
                "TerraWorkbench",
                f"Completed {len(outputs)} filter(s). The final result was added to the map.",
            )
        except (OSError, ValueError, QgsProcessingException) as error:
            QMessageBox.critical(
                self, "TerraWorkbench", f"Filter stack failed:\n{error}"
            )
        finally:
            QApplication.restoreOverrideCursor()
            progress.close()
