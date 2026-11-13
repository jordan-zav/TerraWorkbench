"""One prompt for a survey whose map roles are incomplete."""

from dataclasses import replace

from qgis.core import QgsCoordinateReferenceSystem
from qgis.gui import QgsProjectionSelectionWidget
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
)

from .i18n import language
from ..qgis_plugin.qgis_compat import qt_enum


def tr(en, es, pt):
    return {"en": en, "es": es, "pt": pt}.get(language(), en)


def choose_map_channels(parent, channels, names):
    dialog = QDialog(parent)
    dialog.setWindowTitle(
        tr("Survey map coordinates", "Coordenadas del mapa", "Coordenadas do mapa")
    )
    layout = QFormLayout(dialog)
    fields = {}
    for role, label in (
        ("x", "X"),
        ("y", "Y"),
        ("line", tr("Line (optional)", "Línea (opcional)", "Linha (opcional)")),
    ):
        combo = QComboBox()
        combo.addItem(tr("None", "Ninguno", "Nenhum"), None)
        for name in names:
            combo.addItem(name, name)
        combo.setCurrentIndex(max(0, combo.findData(getattr(channels, role))))
        fields[role] = combo
        layout.addRow(label, combo)
    crs = QgsProjectionSelectionWidget()
    crs.setCrs(QgsCoordinateReferenceSystem(channels.crs or ""))
    layout.addRow(tr("Source CRS", "CRS de origen", "SRC de origem"), crs)
    warning = QLabel()
    warning.setWordWrap(True)
    layout.addRow(warning)
    ok = qt_enum(QDialogButtonBox, "StandardButton", "Ok")
    cancel = qt_enum(QDialogButtonBox, "StandardButton", "Cancel")
    buttons = QDialogButtonBox(ok | cancel)
    layout.addRow(buttons)

    def validate():
        x, y = (fields[role].currentData() for role in ("x", "y"))
        if x and y and x != y and crs.crs().isValid():
            dialog.accept()
        else:
            warning.setText(
                tr(
                    "Select different X and Y channels and a valid CRS.",
                    "Elige canales X e Y distintos y un CRS válido.",
                    "Escolha canais X e Y diferentes e um SRC válido.",
                )
            )

    buttons.accepted.connect(validate)
    buttons.rejected.connect(dialog.reject)
    if dialog.exec() != qt_enum(QDialog, "DialogCode", "Accepted"):
        dialog.deleteLater()
        return None
    result = replace(
        channels,
        x=fields["x"].currentData(),
        y=fields["y"].currentData(),
        line=fields["line"].currentData(),
        crs=crs.crs().authid() or crs.crs().toWkt(),
    )
    dialog.deleteLater()
    return result
