"""Review and execute a saved multi-process recipe without blocking QGIS."""

import json
from pathlib import Path

from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QListWidget,
    QFileDialog,
    QMessageBox,
)

from ._paths import PLUGIN_ROOT
from .core_presentation import operation_title
from .parameter_json import read_parameter_json
from ..qgis_plugin.dependencies import activate_dependency_path
from .survey_workspace_dialog import tr, StoreWorker
from ..terraworkbench_core.operation_workflows import (
    validate_core_workflow,
    run_core_workflow,
)


class CoreWorkflowDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        activate_dependency_path()
        self.worker = None
        self.close_requested = False
        self.recipe_text = None
        self.result = None
        self.setWindowTitle(
            tr("Process workflow", "Workflow de procesos", "Fluxo de processos")
        )
        self.resize(840, 550)
        layout = QVBoxLayout(self)
        note = QLabel(
            tr(
                "Load a saved recipe, review its ordered steps and choose an output folder. Each step keeps its results and processing history. A failed or nonconverged step stops the workflow; incomplete folders are retained for review.",
                "Carga una receta guardada, revisa el orden de sus pasos y elige una carpeta de salida. Cada paso conserva resultados e historial. Un paso fallido o sin converger detiene el workflow; las carpetas incompletas se conservan para revisión.",
                "Carregue uma receita salva, revise a ordem das etapas e escolha uma pasta de saída. Cada etapa mantém resultados e histórico. Uma etapa com falha ou sem convergência interrompe o fluxo; pastas incompletas são mantidas para revisão.",
            )
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.controls = []
        self.recipe_path = self._path(
            layout, tr("Recipe", "Receta", "Receita"), self.choose_recipe
        )
        self.recipe_path.setReadOnly(True)
        self.input_path = self._path(
            layout,
            tr(
                "Input arrays (optional)",
                "Matrices de entrada (opcional)",
                "Matrizes de entrada (opcional)",
            ),
            self.choose_input,
        )
        self.output_path = self._path(
            layout,
            tr("Output folder", "Carpeta de salida", "Pasta de saída"),
            self.choose_output,
        )
        self.steps = QListWidget()
        layout.addWidget(self.steps, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.run_button = QPushButton(
            tr("Run workflow", "Ejecutar workflow", "Executar fluxo")
        )
        self.run_button.clicked.connect(self.start)
        actions.addWidget(self.run_button)
        self.cancel_button = QPushButton(tr("Cancel", "Cancelar", "Cancelar"))
        self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.setEnabled(False)
        actions.addWidget(self.cancel_button)
        layout.addLayout(actions)

    def _path(self, layout, label, action):
        row = QHBoxLayout()
        caption = QLabel(label)
        field = QLineEdit()
        field.setAccessibleName(label)
        caption.setBuddy(field)
        button = QPushButton(tr("Choose…", "Elegir…", "Escolher…"))
        button.clicked.connect(action)
        row.addWidget(caption)
        row.addWidget(field, 1)
        row.addWidget(button)
        layout.addLayout(row)
        self.controls.extend((field, button))
        return field

    def choose_recipe(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.windowTitle(),
            str(PLUGIN_ROOT / "sample_data" / "workflows"),
            "JSON (*.json)",
        )
        if path:
            try:
                self.load_recipe(path)
            except Exception as error:
                QMessageBox.warning(self, self.windowTitle(), str(error))

    def load_recipe(self, path):
        if self.worker is not None:
            raise ValueError("Workflow is already running")
        plan, text = read_parameter_json(path, None)
        validate_core_workflow(plan)
        labels = [
            f"{index + 1}. {operation_title(step['operation'])} · {step['id']}"
            for index, step in enumerate(plan["steps"])
        ]
        self.steps.clear()
        self.steps.addItems(labels)
        self.recipe_text = text
        self.recipe_path.setText(str(path))
        self.result = None
        self.status.setText(tr("Recipe ready", "Receta lista", "Receita pronta"))

    def choose_input(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.windowTitle(), "", "NPZ (*.npz)"
        )
        if path:
            self.input_path.setText(path)

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(
            self, self.windowTitle(), self.output_path.text()
        )
        if path:
            self.output_path.setText(path)

    def start(self):
        if self.worker is not None:
            return
        if (
            self.recipe_text is None
            or not self.output_path.text().strip()
            or not Path(self.output_path.text()).is_dir()
        ):
            self.status.setText(
                tr(
                    "Choose a recipe and existing output folder",
                    "Elige una receta y una carpeta de salida existente",
                    "Escolha uma receita e uma pasta de saída existente",
                )
            )
            return
        text, source, output = (
            self.recipe_text,
            self.input_path.text().strip() or None,
            self.output_path.text(),
        )
        self.result = None
        self.worker = StoreWorker(
            lambda cancel, progress: run_core_workflow(
                text, output, input_npz=source, cancel=cancel, progress=progress
            ),
            self,
        )
        self.worker.completed.connect(self.completed)
        self.worker.failed.connect(self.failed)
        self.worker.cancelled.connect(self.cancelled)
        self.worker.progress.connect(self.progress)
        self.worker.finished.connect(self.finished)
        for widget in self.controls + [self.run_button]:
            widget.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.status.setText(tr("Running…", "Ejecutando…", "Executando…"))
        self.worker.start()

    def progress(self, message):
        # The engine sends stable step identifiers; display localized process names.
        try:
            plan = json.loads(self.recipe_text)
            current = next(
                step
                for step in plan["steps"]
                if message == "Executing " + step["id"] + " (" + step["operation"] + ")"
            )
            self.status.setText(
                tr("Executing: ", "Ejecutando: ", "Executando: ")
                + operation_title(current["operation"])
            )
        except (StopIteration, ValueError):
            self.status.setText(message)

    def completed(self, result):
        self.result = result
        self.status.setText(
            tr("Workflow saved: ", "Workflow guardado: ", "Fluxo salvo: ")
            + result["folder"]
        )

    def failed(self, error):
        self.status.setText(
            tr("Workflow incomplete: ", "Workflow incompleto: ", "Fluxo incompleto: ")
            + error
        )

    def cancelled(self):
        self.status.setText(
            tr(
                "Workflow cancelled; no completed workflow published",
                "Workflow cancelado; no se publicó como completo",
                "Fluxo cancelado; não publicado como completo",
            )
        )

    def cancel(self):
        if self.worker is not None:
            self.worker.requestInterruption()

    def finished(self):
        self.worker.deleteLater()
        self.worker = None
        for widget in self.controls + [self.run_button]:
            widget.setEnabled(True)
        self.cancel_button.setEnabled(False)
        if self.close_requested:
            self.close()

    def reject(self):
        if self.worker is not None:
            self.close_requested = True
            self.cancel()
        else:
            super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            self.close_requested = True
            self.cancel()
            event.ignore()
        else:
            event.accept()
