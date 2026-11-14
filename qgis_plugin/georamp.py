"""Optional GeoRamp integration through its public plugin/dialog interface."""

from ..terraworkbench_core.live_preview import product_palette


def installed_georamp(plugins=None):
    """Return an active GeoRamp plugin without importing or enabling it."""
    if plugins is None:
        from qgis.utils import plugins
    return plugins.get("georamp")


def open_georamp(iface, layer, algorithm_id="", plugins=None):
    """Open GeoRamp on a layer, or its QGIS plugin-manager details if absent.

    GeoRampPlugin.run and ColourDialog's named public controls are used; no
    private methods, numerical routines or copied palette tables are involved.
    """
    plugin = installed_georamp(plugins)
    if plugin is None:
        show_georamp_manager(iface)
        return False
    if layer is None:
        return False
    iface.setActiveLayer(layer)
    plugin.run()
    dialog = plugin.dialog
    index = dialog.layer_combo.findData(layer.id())
    if index >= 0:
        dialog.layer_combo.setCurrentIndex(index)
    palette = product_palette(algorithm_id)
    index = dialog.palette_combo.findData(palette)
    if index >= 0:
        dialog.palette_combo.setCurrentIndex(index)
    if palette == "blue_white_red":
        from qgis.core import QgsRasterBandStats

        stats = layer.dataProvider().bandStatistics(
            1, QgsRasterBandStats.All, layer.extent(), 65536
        )
        limit = max(abs(stats.minimumValue), abs(stats.maximumValue))
        if limit > 0:
            dialog.minimum_spin.setValue(-limit)
            dialog.maximum_spin.setValue(limit)
            dialog.manual_check.setChecked(True)
    return True


def show_georamp_manager(iface):
    """Select GeoRamp in QGIS 3's manager using Qt's public widget API.

    QGIS 3's manager interface only accepts a tab number, not a plugin ID.
    A queued callback filters its named search control after the modal opens.
    """
    from qgis.PyQt.QtCore import QTimer
    from qgis.PyQt.QtWidgets import QApplication, QLineEdit, QListView

    def select(attempt=0):
        for window in QApplication.topLevelWidgets():
            search = window.findChild(QLineEdit, "leFilter")
            listing = window.findChild(QListView, "vwPlugins")
            if window.isVisible() and search is not None and listing is not None:
                search.setText("GeoRamp")
                if listing.model().rowCount():
                    listing.setCurrentIndex(listing.model().index(0, 0))
                return
        if attempt < 150:
            QTimer.singleShot(200, lambda: select(attempt + 1))

    QTimer.singleShot(0, select)
    try:
        from pyplugin_installer import instance
    except ImportError:
        iface.pluginManagerInterface().showPluginManager(0)
    else:
        instance().showPluginManagerWhenReady(0)
