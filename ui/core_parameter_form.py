"""Per-argument editor generated from the actual API, never guessed physics."""

import inspect
import json

from qgis.PyQt.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QScrollArea,
    QPlainTextEdit,
    QPushButton,
)

from .survey_workspace_dialog import tr
from .i18n import language
from .core_field_editor import CoreFieldEditor
from .core_parameter_schema import (
    parameter_label,
    parameter_hint,
    field_kind,
    choices_for,
    validate_scalar,
    validate_relationships,
)


def _unique(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(
                tr(
                    "Duplicate parameter: ",
                    "Parámetro duplicado: ",
                    "Parâmetro duplicado: ",
                )
                + key
            )
        result[key] = value
    return result


class CoreParameterForm(QWidget):
    def __init__(self, signature, parent=None, *, operation_id=None):
        super().__init__(parent)
        self.fields = {}
        self.operation_id = operation_id
        self.kinds = {}
        self.allow_extra = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in signature.parameters.values()
        )
        layout = QVBoxLayout(self)
        note = QLabel(
            tr(
                "Each API argument has its own label and units where declared. Use numbers, selectors or text as indicated; array fields accept JSON or @array_name. Blank optional fields use the API default. Required physical values are never guessed.",
                "Cada argumento tiene etiqueta y unidades cuando están declaradas. Usa números, selectores o texto según corresponda; las matrices aceptan JSON o @nombre_matriz. Un opcional vacío usa el valor de la API. Nunca se inventan valores físicos obligatorios.",
                "Cada argumento tem rótulo e unidades quando declaradas. Use números, seletores ou texto conforme indicado; matrizes aceitam JSON ou @nome_matriz. Um opcional vazio usa o valor da API. Valores físicos obrigatórios nunca são inventados.",
            )
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        form = QVBoxLayout(body)
        form.setSpacing(5)
        for name, parameter in signature.parameters.items():
            if parameter.kind in (
                inspect.Parameter.VAR_KEYWORD,
                inspect.Parameter.VAR_POSITIONAL,
            ) or name in ("canceled", "cancelled", "cancel"):
                continue
            kind = field_kind(operation_id, parameter)
            field = CoreFieldEditor(kind, choices_for(operation_id, name))
            self.kinds[name] = kind
            required = parameter.default is inspect.Parameter.empty
            self.fields[name] = (field, required)
            if required:
                prompts = {
                    "json": tr(
                        "Required · JSON or @array",
                        "Obligatorio · JSON o @matriz",
                        "Obrigatório · JSON ou @matriz",
                    ),
                    "integer": tr(
                        "Required · integer",
                        "Obligatorio · número entero",
                        "Obrigatório · número inteiro",
                    ),
                    "number": tr(
                        "Required · number (decimal point)",
                        "Obligatorio · número (punto decimal)",
                        "Obrigatório · número (ponto decimal)",
                    ),
                    "text": tr(
                        "Required · decoded text",
                        "Obligatorio · texto decodificado",
                        "Obrigatório · texto decodificado",
                    ),
                    "string": tr(
                        "Required · text",
                        "Obligatorio · texto",
                        "Obrigatório · texto",
                    ),
                }
                field.setPlaceholderText(prompts.get(kind, ""))
            else:
                field.setPlaceholderText(
                    tr(
                        "Optional · blank = API default",
                        "Opcional · vacío = valor de la API",
                        "Opcional · vazio = valor da API",
                    )
                )
                field.setToolTip(
                    tr(
                        "API default: ",
                        "Valor predeterminado de la API: ",
                        "Valor padrão da API: ",
                    )
                    + repr(parameter.default)
                )
            label = QLabel(
                parameter_label(name, language()) + (" *" if required else "")
            )
            label.setWordWrap(True)
            label.setToolTip("API: " + name)
            hint = parameter_hint(name, language())
            if hint:
                label.setToolTip(label.toolTip() + "\n" + hint)
                field.setToolTip(field.toolTip() + "\n" + hint)
            field.line.setToolTip(field.toolTip())
            field.choice.setToolTip(field.toolTip())
            field.setAccessibleName(label.text())
            field.line.setAccessibleName(label.text())
            field.choice.setAccessibleName(label.text())
            label.setBuddy(
                field.choice if kind in ("choice", "boolean") else field.line
            )
            form.addWidget(label)
            form.addWidget(field)
            form.addSpacing(8)
        form.addStretch(1)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        self.extra = QPlainTextEdit("{}")
        self.extra.setMaximumHeight(75)
        self.extra_toggle = None
        if self.allow_extra:
            self.extra_toggle = QPushButton(
                tr(
                    "Additional API options (JSON)",
                    "Opciones adicionales de la API (JSON)",
                    "Opções adicionais da API (JSON)",
                )
            )
            self.extra_toggle.setCheckable(True)
            self.extra_toggle.toggled.connect(self.extra.setVisible)
            layout.addWidget(self.extra_toggle)
            layout.addWidget(self.extra)
        self.extra.hide()

    def parameters(self):
        result = {}
        for name, (field, required) in self.fields.items():
            text = field.text().strip()
            if not text:
                if required:
                    raise ValueError(
                        tr(
                            "Required argument: ",
                            "Argumento obligatorio: ",
                            "Argumento obrigatório: ",
                        )
                        + name
                    )
                continue
            result[name] = (
                {"$array": text[1:]}
                if text.startswith("@")
                else json.loads(text, object_pairs_hook=_unique)
            )
            if required and result[name] is None:
                raise ValueError(
                    tr(
                        "Required argument: ",
                        "Argumento obligatorio: ",
                        "Argumento obrigatório: ",
                    )
                    + parameter_label(name, language())
                )
            try:
                validate_scalar(self.kinds[name], result[name])
                choices = choices_for(self.operation_id, name)
                if choices and result[name] not in choices:
                    raise ValueError("choice")
            except ValueError as error:
                raise ValueError(
                    tr(
                        "Invalid value for ",
                        "Valor inválido para ",
                        "Valor inválido para ",
                    )
                    + parameter_label(name, language())
                    + ": "
                    + validation_message(str(error))
                ) from error
        if self.allow_extra:
            extra = json.loads(self.extra.toPlainText(), object_pairs_hook=_unique)
            if not isinstance(extra, dict) or set(extra).intersection(self.fields):
                raise ValueError(
                    tr(
                        "Extra options must be an object without duplicate named fields",
                        "Las opciones adicionales deben ser un objeto sin campos duplicados",
                        "As opções adicionais devem ser um objeto sem campos duplicados",
                    )
                )
            result.update(extra)
        try:
            validate_relationships(self.operation_id, result)
        except ValueError as error:
            raise ValueError(validation_message(str(error))) from error
        json.dumps(result, allow_nan=False)
        return result

    def set_arrays(self, arrays):
        for field, _ in self.fields.values():
            field.set_arrays(arrays)

    def prepare_parameters(self, parameters):
        """Preflight every field before committing any visible edits."""
        if len(json.dumps(parameters, allow_nan=False).encode("utf-8")) > 1024**2:
            raise ValueError(
                tr(
                    "Parameters exceed the 1 MiB JSON budget.",
                    "Los parámetros superan el límite JSON de 1 MiB.",
                    "Os parâmetros excedem o limite JSON de 1 MiB.",
                )
            )
        if not isinstance(parameters, dict):
            raise ValueError(
                tr(
                    "Parameters must be a JSON object",
                    "Los parámetros deben ser un objeto JSON",
                    "Os parâmetros devem ser um objeto JSON",
                )
            )
        extra = {
            name: value for name, value in parameters.items() if name not in self.fields
        }
        if extra and not self.allow_extra:
            raise ValueError(
                tr(
                    "Unknown arguments: ",
                    "Argumentos desconocidos: ",
                    "Argumentos desconhecidos: ",
                )
                + ", ".join(extra)
            )
        values = {}
        for name, (field, _) in self.fields.items():
            if name not in parameters:
                values[name] = ""
            else:
                value = parameters[name]
                values[name] = (
                    "@" + value["$array"]
                    if isinstance(value, dict)
                    and set(value) == {"$array"}
                    and isinstance(value["$array"], str)
                    else json.dumps(value, allow_nan=False)
                )
        for name, (field, _) in self.fields.items():
            field.prepare_text(values[name])
        return values, json.dumps(extra, indent=2, allow_nan=False), bool(extra)

    def set_parameters(self, parameters):
        values, extra, has_extra = self.prepare_parameters(parameters)
        for name, (field, _) in self.fields.items():
            field.setText(values[name])
        self.extra.setPlainText(extra)
        if self.extra_toggle is not None:
            self.extra_toggle.setChecked(has_extra)


def validation_message(code):
    messages = {
        "finite_number": (
            "A finite number is required.",
            "Se requiere un número finito.",
            "É necessário um número finito.",
        ),
        "integer": (
            "An integer is required.",
            "Se requiere un entero.",
            "É necessário um inteiro.",
        ),
        "boolean": ("Choose yes or no.", "Elige sí o no.", "Escolha sim ou não."),
        "string": (
            "A text value is required.",
            "Se requiere texto.",
            "É necessário texto.",
        ),
        "choice": (
            "Choose one of the supported options.",
            "Elige una de las opciones admitidas.",
            "Escolha uma das opções aceitas.",
        ),
        "positive_dt": (
            "The sampling interval must be positive.",
            "El intervalo de muestreo debe ser positivo.",
            "O intervalo de amostragem deve ser positivo.",
        ),
        "nyquist": (
            "Require 0 < low < high < Nyquist.",
            "Se requiere 0 < inferior < superior < Nyquist.",
            "É necessário 0 < inferior < superior < Nyquist.",
        ),
        "odd_window": (
            "Use an odd window of at least 3 samples.",
            "Usa una ventana impar de al menos 3 muestras.",
            "Use uma janela ímpar de pelo menos 3 amostras.",
        ),
        "window_length": (
            "The window exceeds the trace length.",
            "La ventana supera la longitud de la traza.",
            "A janela excede o comprimento do traço.",
        ),
    }
    return tr(*messages[code]) if code in messages else code
