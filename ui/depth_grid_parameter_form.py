"""Method-aware GUI adapter for the unchanged grid source-depth API."""

import inspect
import json

from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QLabel

from .core_parameter_form import CoreParameterForm
from .core_parameter_schema import depth_grid_options, DEPTH_GRID_INTERNAL_ARGUMENTS
from .survey_workspace_dialog import tr


class DepthGridParameterForm(QWidget):
    def __init__(self, module, parent=None):
        super().__init__(parent)
        self.module = module
        self.option_form = None
        self.method = None
        self.drafts = {}
        self.arrays = {}
        self.loading = False
        signature = inspect.signature(module.interpret_grid)
        signature = signature.replace(
            parameters=[
                p
                for p in signature.parameters.values()
                if p.kind != inspect.Parameter.VAR_KEYWORD
            ]
        )
        self.base = CoreParameterForm(signature, operation_id="depth.interpret_grid")
        self.tabs = QTabWidget()
        self.tabs.addTab(
            self.base, tr("Grid inputs", "Entradas de la grilla", "Entradas da grade")
        )
        self.empty = QLabel(
            tr(
                "Choose Euler, Werner or SPI to review its method-specific controls.",
                "Elige Euler, Werner o SPI para revisar sus controles específicos.",
                "Escolha Euler, Werner ou SPI para revisar seus controles específicos.",
            )
        )
        self.empty.setWordWrap(True)
        self.tabs.addTab(
            self.empty,
            tr("Method controls", "Controles del método", "Controles do método"),
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)
        self.base.fields["method"][0].choice.currentIndexChanged.connect(
            self.change_method
        )
        self._update_fields()

    def _update_fields(self):
        self.fields = dict(self.base.fields)
        self.kinds = dict(self.base.kinds)
        if self.option_form is not None:
            self.fields.update(self.option_form.fields)
            self.kinds.update(self.option_form.kinds)

    def change_method(self, *_):
        raw = self.base.fields["method"][0].text()
        method = json.loads(raw) if raw else None
        if method == self.method:
            return
        if self.option_form is not None:
            if not self.loading:
                self.drafts[self.method] = (
                    {
                        name: field.text()
                        for name, (field, _) in self.option_form.fields.items()
                    },
                    self.option_form.extra.toPlainText(),
                )
            self.tabs.removeTab(1)
            self.option_form.hide()
            self.option_form.deleteLater()
            self.option_form = None
        else:
            self.tabs.removeTab(1)
        self.method = method
        if method in ("euler", "werner", "spi"):
            operation_id, signature = depth_grid_options(self.module, method)
            self.option_form = CoreParameterForm(signature, operation_id=operation_id)
            self.option_form.set_arrays(self.arrays)
            if not self.loading and method in self.drafts:
                values, extra = self.drafts[method]
                for name, raw in values.items():
                    self.option_form.fields[name][0].setText(raw)
                self.option_form.extra.setPlainText(extra)
                self.option_form.extra_toggle.setChecked(extra.strip() != "{}")
            content = self.option_form
        else:
            content = self.empty
        title = tr("Method controls", "Controles del método", "Controles do método")
        if method in ("euler", "werner", "spi"):
            title = (
                {"euler": "Euler", "werner": "Werner", "spi": "SPI"}[method]
                + " · "
                + title
            )
        self.tabs.addTab(content, title)
        self._update_fields()

    def parameters(self):
        parameters = self.base.parameters()
        options = self.option_form.parameters() if self.option_form is not None else {}
        if set(options).intersection(
            set(self.base.fields) | DEPTH_GRID_INTERNAL_ARGUMENTS
        ):
            raise ValueError(
                tr(
                    "Method options cannot override grid inputs.",
                    "Las opciones del método no pueden sustituir entradas de la grilla.",
                    "As opções do método não podem substituir entradas da grade.",
                )
            )
        parameters.update(options)
        return parameters

    def set_arrays(self, arrays):
        self.arrays = dict(arrays)
        self.base.set_arrays(arrays)
        if self.option_form is not None:
            self.option_form.set_arrays(arrays)

    def set_parameters(self, parameters):
        if not isinstance(parameters, dict):
            raise ValueError(
                tr(
                    "Parameters must be a JSON object",
                    "Los parámetros deben ser un objeto JSON",
                    "Os parâmetros devem ser um objeto JSON",
                )
            )
        if len(json.dumps(parameters, allow_nan=False).encode("utf-8")) > 1024**2:
            raise ValueError(
                tr(
                    "Parameters exceed the 1 MiB JSON budget.",
                    "Los parámetros superan el límite JSON de 1 MiB.",
                    "Os parâmetros excedem o limite JSON de 1 MiB.",
                )
            )
        options = {
            name: value
            for name, value in parameters.items()
            if name not in self.base.fields
        }
        if options and parameters.get("method") not in ("euler", "werner", "spi"):
            raise ValueError(
                tr(
                    "Choose a valid method before loading method options.",
                    "Elige un método válido antes de cargar sus opciones.",
                    "Escolha um método válido antes de carregar suas opções.",
                )
            )
        base_parameters = {
            name: value
            for name, value in parameters.items()
            if name in self.base.fields
        }
        self.base.prepare_parameters(base_parameters)
        if parameters.get("method") in ("euler", "werner", "spi"):
            operation_id, signature = depth_grid_options(
                self.module, parameters["method"]
            )
            probe = CoreParameterForm(signature, operation_id=operation_id, parent=self)
            try:
                probe.prepare_parameters(options)
            finally:
                probe.deleteLater()
        self.loading = True
        self.drafts.clear()
        try:
            self.base.set_parameters(base_parameters)
            if self.option_form is not None:
                self.option_form.set_parameters(options)
        finally:
            self.loading = False
