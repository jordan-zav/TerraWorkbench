"""Bounded, signature-preserving widgets for scientific argument values."""

import json
from pathlib import Path

from qgis.PyQt.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLineEdit,
    QComboBox,
    QPushButton,
    QFileDialog,
)

from .survey_workspace_dialog import tr
from ..qgis_plugin.qgis_compat import qt_enum


class CoreFieldEditor(QWidget):
    """text()/setText() use serialized JSON, matching the original editor API."""

    def __init__(self, kind, choices=(), parent=None):
        super().__init__(parent)
        self.kind = kind
        self.explicit_empty = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.line = QLineEdit()
        self.line.setMaxLength(1024**2)
        self.line.textEdited.connect(self._edited)
        layout.addWidget(self.line, 1)
        self.choice = QComboBox()
        self.choice.setSizeAdjustPolicy(
            qt_enum(
                QComboBox, "SizeAdjustPolicy", "AdjustToMinimumContentsLengthWithIcon"
            )
        )
        self.choice.setMinimumContentsLength(8)
        self.choice.addItem(tr("Not supplied", "Sin proporcionar", "Não informado"), "")
        for value in (True, False) if kind == "boolean" else choices:
            label = str(value)
            labels = {
                True: ("Yes", "Sí", "Sim"),
                False: ("No", "No", "Não"),
                "half": ("Half-space", "Semiespacio", "Semiespaço"),
                "full": ("Full space", "Espacio completo", "Espaço completo"),
                "mean": ("Mean", "Media", "Média"),
                "median": ("Median", "Mediana", "Mediana"),
                "spherical": ("Spherical", "Esférico", "Esférico"),
                "exponential": ("Exponential", "Exponencial", "Exponencial"),
                "gaussian": ("Gaussian", "Gaussiano", "Gaussiano"),
                "rademacher": (
                    "Random signs (Rademacher)",
                    "Signos aleatorios (Rademacher)",
                    "Sinais aleatórios (Rademacher)",
                ),
                "basis": (
                    "Coordinate basis",
                    "Base de coordenadas",
                    "Base de coordenadas",
                ),
                "hard": ("Hard support", "Soporte duro", "Suporte rígido"),
                "soft": ("Soft penalty", "Penalización suave", "Penalização suave"),
                "density": (
                    "Density contrast",
                    "Contraste de densidad",
                    "Contraste de densidade",
                ),
                "susceptibility": (
                    "Susceptibility (SI)",
                    "Susceptibilidad (SI)",
                    "Suscetibilidade (SI)",
                ),
                "total": (
                    "Total-field anomaly",
                    "Anomalía de campo total",
                    "Anomalia de campo total",
                ),
                "vector": ("ENU vector", "Vector ENU", "Vetor ENU"),
                "east": ("East", "Este", "Leste"),
                "north": ("North", "Norte", "Norte"),
                "up": ("Up", "Arriba", "Cima"),
                "down": ("Down", "Abajo", "Baixo"),
                "both": (
                    "Both polarities",
                    "Ambas polaridades",
                    "Ambas as polaridades",
                ),
                "positive": ("Positive", "Positiva", "Positiva"),
                "negative": ("Negative", "Negativa", "Negativa"),
                "contact": ("Contact", "Contacto", "Contato"),
                "thin_sheet": ("Thin sheet", "Lámina delgada", "Lâmina fina"),
                "horizontal_cylinder": (
                    "Horizontal cylinder",
                    "Cilindro horizontal",
                    "Cilindro horizontal",
                ),
            }
            if value in labels:
                label = tr(*labels[value])
            self.choice.addItem(label, json.dumps(value))
        layout.addWidget(self.choice, 1)
        self.choice.setVisible(kind in ("choice", "boolean"))
        self.line.setVisible(kind not in ("choice", "boolean"))
        self.arrays = QComboBox()
        self.arrays.setMinimumContentsLength(10)
        self.arrays.setMaximumWidth(190)
        self.arrays.setSizeAdjustPolicy(
            qt_enum(
                QComboBox, "SizeAdjustPolicy", "AdjustToMinimumContentsLengthWithIcon"
            )
        )
        self.arrays.addItem(tr("NPZ array…", "Matriz NPZ…", "Matriz NPZ…"), "")
        self.arrays.activated.connect(self._array_selected)
        self.arrays.hide()
        layout.addWidget(self.arrays)
        if kind == "text":
            load = QPushButton(tr("Load text…", "Cargar texto…", "Carregar texto…"))
            load.clicked.connect(self.load_text)
            layout.addWidget(load)

    def _edited(self, *_):
        self.explicit_empty = False

    def _array_selected(self, index):
        name = self.arrays.itemData(index)
        if name:
            self.line.setText("@" + name)
        self.arrays.setCurrentIndex(0)

    def set_arrays(self, arrays):
        self.arrays.clear()
        self.arrays.addItem(tr("NPZ array…", "Matriz NPZ…", "Matriz NPZ…"), "")
        for name, description in arrays.items():
            self.arrays.addItem(name, name)
            self.arrays.setItemData(
                self.arrays.count() - 1, description, 3
            )  # Qt.ToolTipRole
        self.arrays.setVisible(bool(arrays) and self.kind == "json")

    def setPlaceholderText(self, value):
        self.line.setPlaceholderText(value)

    def text(self):
        if self.kind in ("choice", "boolean"):
            return self.choice.currentData()
        value = self.line.text()
        if self.kind in ("string", "text"):
            return (
                json.dumps(value, ensure_ascii=False)
                if value or self.explicit_empty
                else ""
            )
        return value

    def prepare_text(self, value):
        """Check a serialized value without changing any widget or selection."""
        if len(value.encode("utf-8")) > 1024**2:
            raise ValueError(
                tr(
                    "Value exceeds the 1 MiB input budget.",
                    "El valor supera el límite de entrada de 1 MiB.",
                    "O valor excede o limite de entrada de 1 MiB.",
                )
            )
        if self.kind in ("string", "text"):
            try:
                decoded = json.loads(value)
            except (ValueError, TypeError):
                decoded = value
            if not isinstance(decoded, str):
                raise ValueError(
                    tr(
                        "Text value required",
                        "Se requiere un valor de texto",
                        "É necessário um valor de texto",
                    )
                )
            decoded.encode("utf-8")  # reject unpaired surrogates before Qt sees them
            return decoded
        return value

    def setText(self, value):
        decoded = self.prepare_text(value)
        if self.kind in ("choice", "boolean"):
            index = self.choice.findData(value)
            if index < 0:
                self.choice.addItem(
                    value, value
                )  # preserve invalid loaded data for validation
                index = self.choice.count() - 1
            self.choice.setCurrentIndex(index)
        elif self.kind in ("string", "text"):
            self.explicit_empty = decoded == "" and value == '""'
            self.line.setText(decoded)
        else:
            self.line.setText(value)

    def load_text(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr(
                "Load decoded LAS text",
                "Cargar texto LAS decodificado",
                "Carregar texto LAS decodificado",
            ),
            "",
            tr(
                "LAS (*.las *.LAS);;Text (*.txt)",
                "LAS (*.las *.LAS);;Texto (*.txt)",
                "LAS (*.las *.LAS);;Texto (*.txt)",
            ),
        )
        if path:
            source = Path(path)
            try:
                with source.open("rb") as stream:
                    raw = stream.read(1024**2 + 1)
                if len(raw) > 1024**2:
                    raise ValueError(
                        tr(
                            "Text exceeds the 1 MiB JSON input budget.",
                            "El texto supera el límite de entrada JSON de 1 MiB.",
                            "O texto excede o limite de entrada JSON de 1 MiB.",
                        )
                    )
                self.setText(json.dumps(raw.decode("utf-8-sig"), ensure_ascii=False))
            except (OSError, UnicodeError, ValueError) as error:
                from qgis.PyQt.QtWidgets import QMessageBox

                QMessageBox.warning(
                    self,
                    "TerraWorkbench",
                    tr(
                        "Cannot load text. Technical details: ",
                        "No se puede cargar el texto. Detalles técnicos: ",
                        "Não foi possível carregar o texto. Detalhes técnicos: ",
                    )
                    + str(error),
                )
