"""Quick QGIS hillshade actions and dialogs."""

from dataclasses import replace
from pathlib import Path
import weakref

from qgis.PyQt.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QGridLayout, QMenu, QMessageBox, QToolButton, QWidget,
)
from qgis.core import QgsApplication, QgsProject, QgsRasterLayer, QgsTask

from .i18n import text
from ..qgis_plugin.data_import import mark_temporary_import
from ..qgis_plugin.hillshade import (
    DIRECTIONS, EFFECT, GROUP, ShadeStyle, apply_effect, calculate_shades, effect_layer,
    source_group, visual_statistics,
)
from ..qgis_plugin.qgis_compat import qt_enum


def _angle(value, maximum, parent):
    spin = QDoubleSpinBox(parent)
    spin.setRange(0, maximum)
    spin.setDecimals(1)
    spin.setValue(value)
    spin.setSuffix("°")
    return spin


def _directions():
    return ("N", "NE", "E", "SE", "S", text("SW", "SO"), text("W", "O"), text("NW", "NO"))


def _form(parent, title):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    form = QFormLayout(dialog)
    return dialog, form


class HillshadeActions:
    def __init__(self, dock, iface):
        self.dock = dock
        self.iface = iface
        self.project = QgsProject.instance()
        self.tasks = set()
        self.watched = {}
        self.closed = False
        self.button = QToolButton(dock)
        self.menu = QMenu(self.button)
        self.toggle_action = self.menu.addAction("", self.toggle)
        self.calculate_action = self.menu.addAction("", self.calculate)
        self.settings_action = self.menu.addAction("", self.settings)
        self.button.setDefaultAction(self.toggle_action)
        self.button.setMenu(self.menu)
        self.button.setPopupMode(qt_enum(QToolButton, "ToolButtonPopupMode", "MenuButtonPopup"))
        self.context_menu = QMenu(self.button)
        self.context_menu.addActions(self.menu.actions())
        if iface is not None:
            from qgis.core import Qgis

            iface.addCustomActionForLayerType(self.context_menu.menuAction(), "", Qgis.LayerType.Raster, True)
            iface.currentLayerChanged.connect(self.refresh)
        self.project.readProject.connect(self._project_read)
        self.project.layersWillBeRemoved["QStringList"].connect(self._layers_removed)
        self._project_read()
        self.retranslate()

    def retranslate(self):
        self.toggle_action.setText(text("Hillshade", "Sombreado"))
        self.context_menu.setTitle(self.toggle_action.text())
        self.calculate_action.setText(text("Calculate hillshade…", "Calcular sombreado…"))
        self.settings_action.setText(text("Visual hillshade settings…", "Ajustes del sombreado visual…"))
        for shade in self.project.mapLayers().values():
            source = self.project.mapLayer(shade.customProperty(EFFECT, ""))
            if source is not None:
                shade.setName(self._effect_name(source))
        self.refresh()

    def _source(self):
        if self.iface is None and not hasattr(self.dock, "layer_combo"):
            return None
        layer = self.iface.activeLayer() if self.iface is not None else self.dock._selected_raster()
        if isinstance(layer, QgsRasterLayer):
            layer = self.project.mapLayer(layer.customProperty(EFFECT, "")) or layer
            if layer.isValid() and layer.bandCount() == 1:
                return layer
        return None

    def refresh(self, *_args):
        enabled = self._source() is not None
        for action in (self.toggle_action, self.calculate_action, self.settings_action, self.context_menu.menuAction()):
            action.setEnabled(enabled)
        self.button.setToolTip(
            text("Toggle visual hillshade", "Mostrar u ocultar el sombreado visual") if enabled else
            text("Select a single-band raster", "Seleccione un ráster de una banda")
        )

    def _effect_name(self, source):
        return f"{source.name()} ({text('hillshade effect', 'efecto de sombreado')})"

    def _error(self, error):
        QMessageBox.warning(
            self.dock, "TerraWorkbench",
            text("Hillshade failed: {error}", "Falló el sombreado: {error}").format(error=error),
        )

    def toggle(self):
        source = self._source()
        if source is None:
            return
        shade = effect_layer(self.project, source)
        if shade is not None:
            node = self.project.layerTreeRoot().findLayer(shade.id())
            node.setItemVisibilityChecked(not node.itemVisibilityChecked())
            return
        try:
            statistics = visual_statistics(source)
            shade = QgsRasterLayer(source.source(), self._effect_name(source), source.providerType())
            if not shade.isValid():
                raise ValueError("QGIS could not reopen the raster source.")
            shade.setCrs(source.crs())
            shade.setCustomProperty(EFFECT, source.id())
            apply_effect(source, shade, ShadeStyle.from_layer(source), statistics)
            group = source_group(self.project, source)
            self.project.addMapLayer(shade, False)
            group.insertLayer(0, shade)
            root = self.project.layerTreeRoot()
            if root.hasCustomLayerOrder():
                order = [layer for layer in root.customLayerOrder() if layer != shade]
                if source in order:
                    order.insert(order.index(source), shade)
                    root.setCustomLayerOrder(order)
            self._watch(source)
            if self.iface is not None:
                self.iface.setActiveLayer(source)
        except (ValueError, RuntimeError) as error:
            self._error(error)

    def _watch(self, source):
        source_id = source.id()
        if source_id not in self.watched:
            def sync():
                self._sync_effect(source_id)

            source.dataSourceChanged.connect(sync)
            source.nameChanged.connect(sync)
            self.watched[source_id] = (source, sync)

    def _unwatch(self, layer_id):
        connection = self.watched.pop(layer_id, None)
        if connection is not None:
            source, sync = connection
            source.dataSourceChanged.disconnect(sync)
            source.nameChanged.disconnect(sync)

    def _layers_removed(self, layer_ids):
        for layer_id in layer_ids:
            self._unwatch(layer_id)

    def _project_read(self, *_args):
        for shade in self.project.mapLayers().values():
            source = self.project.mapLayer(shade.customProperty(EFFECT, ""))
            if source is not None:
                self._watch(source)

    def _sync_effect(self, source_id):
        source = self.project.mapLayer(source_id)
        shade = effect_layer(self.project, source) if source is not None else None
        if shade is None:
            return
        shade.setName(self._effect_name(source))
        node = self.project.layerTreeRoot().findLayer(source_id)
        if node is not None and node.parent().customProperty(GROUP) == source_id:
            node.parent().setName(source.name())
        if shade.source() != source.source():
            shade.setDataSource(source.source(), shade.name(), source.providerType())
            shade.setCrs(source.crs())
            if shade.isValid():
                apply_effect(source, shade, ShadeStyle.from_layer(source), visual_statistics(source))

    def settings(self):
        source = self._source()
        if source is None:
            return
        shade = effect_layer(self.project, source)
        try:
            statistics = visual_statistics(source) if shade is not None else None
        except (ValueError, RuntimeError) as error:
            self._error(error)
            return
        style = ShadeStyle.from_layer(source)
        dialog, form = _form(self.dock, self.settings_action.text())
        azimuth = _angle(style.azimuth, 359.9, dialog)
        altitude = _angle(style.altitude, 90, dialog)
        intensity = QComboBox(dialog)
        for multiplier in (0.5, 1.0, 2.0, 4.0):
            intensity.addItem(f"× {multiplier:g}", multiplier)
        intensity.setCurrentIndex(intensity.findData(style.intensity))
        palette = QComboBox(dialog)
        palette.addItem(text("Classic geophysics", "Geofísica clásica"), "classic")
        palette.addItem(text("Grayscale", "Escala de grises"), "gray")
        palette.setCurrentIndex(palette.findData(style.palette))
        form.addRow(text("Light direction (azimuth)", "Dirección de la luz (azimut)"), azimuth)
        form.addRow(text("Altitude", "Altura"), altitude)
        form.addRow(text("Intensity", "Intensidad"), intensity)
        form.addRow(text("Palette", "Paleta"), palette)
        buttons = QDialogButtonBox(qt_enum(QDialogButtonBox, "StandardButton", "Close"), parent=dialog)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        def update(*_args):
            updated = replace(
                style, azimuth=azimuth.value(), altitude=altitude.value(),
                intensity=intensity.currentData(), palette=palette.currentData(),
            )
            if shade is not None:
                apply_effect(source, shade, updated, statistics)
            else:
                updated.save_to_layer(source)

        for control in (azimuth, altitude):
            control.valueChanged.connect(update)
        for control in (intensity, palette):
            control.currentIndexChanged.connect(update)
        dialog.exec()
        dialog.deleteLater()

    def calculate(self):
        source = self._source()
        if source is None:
            return
        dialog, form = _form(self.dock, self.calculate_action.text())
        azimuth = _angle(315, 359.9, dialog)
        altitude = _angle(45, 90, dialog)
        shortcut = QComboBox(dialog)
        shortcut.addItem(text("Custom", "Personalizado"), None)
        for direction, value in zip(_directions(), DIRECTIONS):
            shortcut.addItem(f"{direction} ({value}°)", value)

        def choose_shortcut():
            value = shortcut.currentData()
            if value is not None:
                azimuth.setValue(value)

        shortcut.currentIndexChanged.connect(choose_shortcut)
        azimuth.valueChanged.connect(
            lambda value: shortcut.setCurrentIndex(max(0, shortcut.findData(value)))
        )
        shortcut.setCurrentIndex(shortcut.findData(315))
        factor = QDoubleSpinBox(dialog)
        factor.setDecimals(12)
        factor.setRange(1e-12, 1e12)
        factor.setValue(1)
        auto = QCheckBox(text("Automatic z factor", "Factor z automático"), dialog)
        auto.setChecked(True)
        factor.setEnabled(False)
        auto.toggled.connect(factor.setDisabled)
        multi = QCheckBox(text("Several directions", "Varias direcciones"), dialog)
        combined = QCheckBox(text("Combined (multidirectional)", "Combinado (multidireccional)"), dialog)
        choices = QWidget(dialog)
        layout = QGridLayout(choices)
        layout.setContentsMargins(0, 0, 0, 0)
        directions = []
        for i, (direction, value) in enumerate(zip(_directions(), DIRECTIONS)):
            check = QCheckBox(direction, choices)
            check.setToolTip(f"{value}°")
            check.setChecked(True)
            layout.addWidget(check, i // 4, i % 4)
            directions.append(check)
        form.addRow(text("Azimuth", "Azimut"), azimuth)
        form.addRow(text("Direction", "Dirección"), shortcut)
        form.addRow(text("Altitude", "Altura"), altitude)
        form.addRow(auto)
        form.addRow(text("Z factor", "Factor z"), factor)
        form.addRow(multi)
        form.addRow(combined)
        form.addRow(choices)
        buttons = QDialogButtonBox(
            qt_enum(QDialogButtonBox, "StandardButton", "Ok") |
            qt_enum(QDialogButtonBox, "StandardButton", "Cancel"), parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        def update():
            many = multi.isChecked() or combined.isChecked()
            azimuth.setEnabled(not many)
            shortcut.setEnabled(not many)
            choices.setVisible(many)
            count = sum(check.isChecked() for check in directions)
            buttons.button(qt_enum(QDialogButtonBox, "StandardButton", "Ok")).setEnabled(
                not many or count >= (2 if combined.isChecked() else 1)
            )

        for control in (multi, combined, *directions):
            control.toggled.connect(update)
        update()
        if dialog.exec():
            azimuths = (azimuth.value(),)
            if multi.isChecked() or combined.isChecked():
                azimuths = tuple(value for check, value in zip(directions, DIRECTIONS) if check.isChecked())
            self.start_calculation(source, azimuths, altitude.value(), None if auto.isChecked() else factor.value(),
                                   combined.isChecked())
        dialog.deleteLater()

    def start_calculation(self, source, directions, altitude, factor, combined):
        path = source.source().split("|", 1)[0]
        source_id = source.id()
        stem = Path(path).stem
        crs = source.crs()
        crs_override = crs.toWkt() if crs != source.dataProvider().crs() else None
        try:
            destination, temporary = self.dock._import_destination(stem)
        except OSError as error:
            self._error(error)
            return None
        controller = weakref.ref(self)

        def finished(error, outputs=None):
            owner = controller()
            if owner is None or owner.closed:
                return
            owner.tasks.discard(task)
            layer = owner.project.mapLayer(source_id)
            if layer is None or task.isCanceled():
                return
            if error:
                owner._error(error)
                return
            group = source_group(owner.project, layer)
            for output in outputs:
                result = QgsRasterLayer(str(output), output.stem)
                if not result.isValid():
                    owner._error(output.name)
                    continue
                if temporary is not None:
                    mark_temporary_import(result, text("temporary", "temporal"), temporary)
                owner.project.addMapLayer(result, False)
                group.addLayer(result)

        task = QgsTask.fromFunction(
            self.calculate_action.text(), calculate_shades, on_finished=finished,
            source=path, destination=destination, stem=stem, directions=directions,
            altitude=altitude, z_factor=factor, combined=combined, crs_override=crs_override,
        )
        task.setDependentLayers([source])
        self.tasks.add(task)
        QgsApplication.taskManager().addTask(task)
        return task

    def close(self):
        self.closed = True
        if self.iface is not None:
            self.iface.removeCustomActionForLayerType(self.context_menu.menuAction())
            self.iface.currentLayerChanged.disconnect(self.refresh)
        self.project.readProject.disconnect(self._project_read)
        self.project.layersWillBeRemoved["QStringList"].disconnect(self._layers_removed)
        for layer_id in list(self.watched):
            self._unwatch(layer_id)
        for task in self.tasks:
            task.cancel()
        self.tasks.clear()
