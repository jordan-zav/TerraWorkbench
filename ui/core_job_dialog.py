"""Explicit technical console for the registered experimental scientific Core."""

import importlib
import json
import os
from zipfile import BadZipFile
from pathlib import Path

from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QFileDialog,
    QListWidget,
    QTabWidget,
    QTextBrowser,
)

from .survey_workspace_dialog import tr, StoreWorker
from .task_history_widget import TaskHistoryWidget
from ..terraworkbench_core.operations import operation_info
from ..terraworkbench_core.operation_jobs import run_core_job
from .core_parameter_form import CoreParameterForm
from .depth_grid_parameter_form import DepthGridParameterForm
from .core_parameter_schema import presentation_signature
from .npz_inspector import describe_npz
from .parameter_json import ParameterJSONError, read_parameter_json
from ..qgis_plugin.dependencies import activate_dependency_path
from .core_presentation import operation_title, operation_guidance


class CoreJobDialog(QDialog):
    def __init__(self, operation_id, parent=None):
        super().__init__(parent)
        activate_dependency_path()
        self.operation_id = operation_id
        self.info = operation_info(operation_id)
        self.worker = None
        self.close_requested = False
        self.result = None
        self.pending = []
        self.queue_paused = False
        self.sequence = 0
        self.setWindowTitle("TerraWorkbench — " + operation_title(operation_id))
        self.resize(1000, 800)
        layout = QVBoxLayout(self)
        warning = QLabel(
            tr(
                "Advanced experimental console. Review the function contract, units and array shapes. Synthetic validation only; input/output size budgets do not limit solver RAM or runtime. Kernels without cancellation checkpoints finish computing before cancellation takes effect.",
                "Consola avanzada experimental. Revisa el contrato, unidades y formas de las matrices. Solo validación sintética; los límites de entrada/salida no limitan RAM ni duración del solver. Los kernels sin puntos de cancelación terminan el cálculo antes de atenderla.",
                "Console avançado experimental. Revise o contrato, unidades e formas das matrizes. Apenas validação sintética; limites de entrada/saída não limitam RAM nem duração do solver. Kernels sem pontos de cancelamento terminam o cálculo antes de atendê-lo.",
            )
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)
        guidance = QTextBrowser()
        guidance.setMarkdown(operation_guidance(operation_id))
        guidance.setOpenExternalLinks(True)
        guidance.setMaximumHeight(120)
        layout.addWidget(guidance)
        technical_toggle = QPushButton(
            tr(
                "Technical API reference (English)",
                "Referencia técnica de la API (inglés)",
                "Referência técnica da API (inglês)",
            )
        )
        technical_toggle.setCheckable(True)
        layout.addWidget(technical_toggle)
        self.contract = QPlainTextEdit()
        self.contract.setReadOnly(True)
        self.contract.setPlainText(
            self.info["function"]
            + self.info["signature"]
            + "\n\n"
            + (self.info["documentation"] or "")
        )
        self.contract.setMaximumHeight(115)
        self.contract.hide()
        technical_toggle.toggled.connect(self.contract.setVisible)
        layout.addWidget(self.contract)
        self.controls = QWidget()
        body = QVBoxLayout(self.controls)
        body.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        self.input_path, self.output_path = QLineEdit(), QLineEdit()
        for label, field, callback in (
            (
                tr(
                    "Optional input NPZ (≤256 MiB uncompressed)",
                    "NPZ de entrada opcional (≤256 MiB sin comprimir)",
                    "NPZ de entrada opcional (≤256 MiB descompactados)",
                ),
                self.input_path,
                self.choose_input,
            ),
            (
                tr(
                    "Existing output folder · new job subfolder",
                    "Carpeta de salida existente · subcarpeta de trabajo nueva",
                    "Pasta de saída existente · nova subpasta de trabalho",
                ),
                self.output_path,
                self.choose_output,
            ),
        ):
            row = QHBoxLayout()
            row.addWidget(field, 1)
            button = QPushButton("…")
            button.clicked.connect(callback)
            row.addWidget(button)
            form.addRow(label, row)
        body.addLayout(form)
        syntax = QLabel(
            tr(
                'Parameters JSON: reference an attached array as {"$array": "array_name"}. No Python code or pickle. Outputs: typed manifest + NPZ, ≤128 MiB of arrays; complex values and masks preserved.',
                'Parámetros JSON: referencia una matriz adjunta como {"$array": "nombre_matriz"}. Sin código Python ni pickle. Salidas: manifiesto tipado + NPZ, ≤128 MiB de matrices; conserva complejos y máscaras.',
                'Parâmetros JSON: referencie uma matriz anexada como {"$array": "nome_matriz"}. Sem código Python nem pickle. Saídas: manifesto tipado + NPZ, ≤128 MiB de matrizes; preserva complexos e máscaras.',
            )
        )
        syntax.setWordWrap(True)
        body.addWidget(syntax)
        self.parameters = QPlainTextEdit("{}")
        module = importlib.import_module(
            "." + self.info["module"].rsplit(".", 1)[1],
            __package__.rsplit(".", 1)[0] + ".terraworkbench_core",
        )
        self.parameter_form = (
            DepthGridParameterForm(module)
            if operation_id == "depth.interpret_grid"
            else CoreParameterForm(
                presentation_signature(
                    getattr(module, self.info["function"]), operation_id
                ),
                operation_id=operation_id,
            )
        )
        self.parameter_tabs = QTabWidget()
        self.parameter_tabs.addTab(
            self.parameter_form,
            tr("Argument form", "Formulario de argumentos", "Formulário de argumentos"),
        )
        self.parameter_tabs.addTab(
            self.parameters, tr("Advanced JSON", "JSON avanzado", "JSON avançado")
        )
        body.addWidget(self.parameter_tabs, 1)
        actions = QHBoxLayout()
        for label, callback in (
            (
                tr(
                    "Required parameter names",
                    "Nombres de parámetros obligatorios",
                    "Nomes dos parâmetros obrigatórios",
                ),
                self.insert_required,
            ),
            (
                tr(
                    "Load parameters JSON…",
                    "Cargar parámetros JSON…",
                    "Carregar parâmetros JSON…",
                ),
                self.load_parameters,
            ),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        self.run_button = QPushButton(
            tr(
                "Queue / run explicitly",
                "Encolar / ejecutar explícitamente",
                "Enfileirar / executar explicitamente",
            )
        )
        self.run_button.clicked.connect(self.run)
        actions.addWidget(self.run_button)
        body.addLayout(actions)
        layout.addWidget(self.controls, 1)
        self.queue_list = QListWidget()
        self.queue_list.setMaximumHeight(90)
        self.queue_list.hide()
        self.queue_list.setAccessibleName(
            tr("Pending jobs", "Trabajos pendientes", "Trabalhos pendentes")
        )
        layout.addWidget(self.queue_list)
        queue_controls = QHBoxLayout()
        self.pause_queue = QPushButton(
            tr(
                "Pause following jobs",
                "Pausar tareas siguientes",
                "Pausar tarefas seguintes",
            )
        )
        self.pause_queue.setCheckable(True)
        self.pause_queue.setToolTip(
            tr(
                "Only following jobs are paused; an active kernel keeps running until completion or acknowledged cancellation.",
                "Solo se pausan las tareas siguientes; el kernel activo sigue hasta terminar o confirmar la cancelación.",
                "Apenas tarefas seguintes são pausadas; o kernel ativo continua até terminar ou confirmar o cancelamento.",
            )
        )
        self.pause_queue.toggled.connect(self.set_queue_paused)
        queue_controls.addWidget(self.pause_queue)
        for label, callback in (
            ("↑", lambda: self.move_queued(-1)),
            ("↓", lambda: self.move_queued(1)),
            (
                tr(
                    "Cancel selected queued job",
                    "Cancelar tarea pendiente seleccionada",
                    "Cancelar tarefa pendente selecionada",
                ),
                self.cancel_queued,
            ),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            queue_controls.addWidget(button)
        layout.addLayout(queue_controls)
        self.status = QLabel(
            tr(
                "Ready · no operation has been executed",
                "Listo · no se ha ejecutado ninguna operación",
                "Pronto · nenhuma operação foi executada",
            )
        )
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMaximumHeight(180)
        layout.addWidget(self.summary)
        self.tasks = TaskHistoryWidget(tr, self)
        self.tasks.cancelRequested.connect(
            lambda: self.worker.requestInterruption() if self.worker else None
        )
        layout.addWidget(self.tasks)
        self.input_path.editingFinished.connect(self.refresh_input_arrays)

    def choose_input(self):
        path, _ = QFileDialog.getOpenFileName(self, "NPZ", "", "NumPy (*.npz)")
        if path:
            self.input_path.setText(path)
            self.refresh_input_arrays()

    def show_error(self, error):
        self.status.setText(
            tr(
                "Review the input. Technical details: ",
                "Revisa la entrada. Detalles técnicos: ",
                "Revise a entrada. Detalhes técnicos: ",
            )
            + str(error)
        )

    def refresh_input_arrays(self):
        path = self.input_path.text().strip()
        try:
            arrays = describe_npz(path) if path else {}
            self.parameter_form.set_arrays(
                {
                    name: str(info["shape"]) + " · " + info["dtype"]
                    for name, info in arrays.items()
                }
            )
            self.input_path.setToolTip(
                "\n".join(
                    name + ": " + str(info["shape"]) + " · " + info["dtype"]
                    for name, info in arrays.items()
                )
            )
        except (OSError, ValueError, BadZipFile, EOFError) as error:
            self.parameter_form.set_arrays({})
            self.status.setText(
                tr(
                    "Cannot inspect input arrays: ",
                    "No se pueden inspeccionar las matrices: ",
                    "Não foi possível inspecionar as matrizes: ",
                )
                + str(error)
            )

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(
            self, tr("Output folder", "Carpeta de salida", "Pasta de saída")
        )
        if path:
            self.output_path.setText(path)

    def insert_required(self):
        if self.parameters.toPlainText().strip() not in ("", "{}"):
            self.status.setText(
                tr(
                    "Existing edits preserved. Clear the JSON first to insert required names.",
                    "Se conservan las ediciones. Vacía el JSON antes de insertar nombres obligatorios.",
                    "Edições preservadas. Limpe o JSON antes de inserir nomes obrigatórios.",
                )
            )
            return
        required = {
            name: None
            for name, (_, is_required) in self.parameter_form.fields.items()
            if is_required
        }
        self.parameters.setPlainText(json.dumps(required, indent=2))
        self.parameter_tabs.setCurrentIndex(1)

    def load_parameters(self):
        path, _ = QFileDialog.getOpenFileName(self, "JSON", "", "JSON (*.json)")
        if not path:
            return
        try:
            data, encoded = read_parameter_json(path, self.operation_id)
            self.parameter_form.set_parameters(data)
            self.parameters.setPlainText(encoded)
            self.parameter_tabs.setCurrentIndex(0)
            self.input_path.clear()
            self.input_path.setToolTip("")
            self.parameter_form.set_arrays({})
            self.status.setText(
                tr(
                    "Settings loaded. Reattach and review input arrays; loading settings is not identical-data replay.",
                    "Ajustes cargados. Vuelve a adjuntar y revisar las matrices; cargar ajustes no garantiza repetir los mismos datos.",
                    "Ajustes carregados. Anexe novamente e revise as matrizes; carregar ajustes não garante repetir os mesmos dados.",
                )
            )
        except ParameterJSONError as error:
            messages = {
                "file_budget": (
                    "JSON exceeds the 6 MiB import budget.",
                    "El JSON supera el límite de importación de 6 MiB.",
                    "O JSON excede o limite de importação de 6 MiB.",
                ),
                "parameter_budget": (
                    "Parameters exceed the 1 MiB JSON budget.",
                    "Los parámetros superan el límite JSON de 1 MiB.",
                    "Os parâmetros excedem o limite JSON de 1 MiB.",
                ),
                "duplicate_keys": (
                    "Duplicate JSON keys are not allowed.",
                    "No se permiten claves JSON duplicadas.",
                    "Chaves JSON duplicadas não são permitidas.",
                ),
                "nonfinite": (
                    "JSON values must be finite.",
                    "Los valores JSON deben ser finitos.",
                    "Os valores JSON devem ser finitos.",
                ),
                "invalid_json": (
                    "Invalid JSON or UTF-8 text.",
                    "JSON o texto UTF-8 inválido.",
                    "JSON ou texto UTF-8 inválido.",
                ),
                "wrong_operation": (
                    "Saved job belongs to a different operation or has invalid provenance.",
                    "El trabajo guardado pertenece a otra operación o tiene procedencia inválida.",
                    "O trabalho salvo pertence a outra operação ou tem proveniência inválida.",
                ),
                "object_required": (
                    "Parameters must be a JSON object.",
                    "Los parámetros deben ser un objeto JSON.",
                    "Os parâmetros devem ser um objeto JSON.",
                ),
            }
            self.show_error(tr(*messages[str(error)]))
        except Exception as error:
            self.show_error(error)

    def run(self):
        try:
            if self.parameter_tabs.currentIndex() == 0:
                self.parameters.setPlainText(
                    json.dumps(
                        self.parameter_form.parameters(), indent=2, allow_nan=False
                    )
                )
        except Exception as error:
            self.show_error(error)
            return
        text, source, output = (
            self.parameters.toPlainText(),
            self.input_path.text().strip(),
            self.output_path.text().strip(),
        )
        if not output:
            self.status.setText(
                tr(
                    "Choose an output folder first.",
                    "Primero elige una carpeta de salida.",
                    "Primeiro escolha uma pasta de saída.",
                )
            )
            return
        try:
            if len(self.pending) >= 20 or len(text.encode("utf-8")) > 1024**2:
                raise ValueError(
                    "Queue is limited to 20 jobs and 1 MiB of JSON per job"
                )
            if not Path(output).is_dir():
                raise ValueError("Choose an existing output folder")
            state = os.stat(source) if source else None
            fingerprint = (
                (state.st_dev, state.st_ino, state.st_size, state.st_mtime_ns)
                if state
                else None
            )
            self.sequence += 1
            self.pending.append(
                {
                    "id": self.sequence,
                    "text": text,
                    "source": source,
                    "output": output,
                    "fingerprint": fingerprint,
                }
            )
            self.refresh_queue()
            self.start_next()
        except Exception as error:
            self.show_error(error)

    def refresh_queue(self):
        self.queue_list.setVisible(bool(self.pending))
        selected = self.queue_list.currentRow()
        self.queue_list.clear()
        for job in self.pending:
            self.queue_list.addItem(
                f"#{job['id']} · {self.operation_id} · {Path(job['source']).name if job['source'] else 'JSON'}"
            )
            self.queue_list.item(self.queue_list.count() - 1).setToolTip(job["text"])
        if self.pending:
            self.queue_list.setCurrentRow(max(0, min(selected, len(self.pending) - 1)))

    def set_queue_paused(self, paused):
        self.queue_paused = paused
        if not paused:
            self.start_next()

    def move_queued(self, offset):
        index = self.queue_list.currentRow()
        target = index + offset
        if index >= 0 and 0 <= target < len(self.pending):
            self.pending[index], self.pending[target] = (
                self.pending[target],
                self.pending[index],
            )
            self.refresh_queue()
            self.queue_list.setCurrentRow(target)

    def cancel_queued(self):
        index = self.queue_list.currentRow()
        if 0 <= index < len(self.pending):
            job = self.pending.pop(index)
            self.refresh_queue()
            self.status.setText(
                tr(
                    "Queued job #{n} cancelled before execution",
                    "Tarea pendiente #{n} cancelada antes de ejecutarse",
                    "Tarefa pendente #{n} cancelada antes da execução",
                ).format(n=job["id"])
            )

    def start_next(self):
        if (
            self.worker is not None
            or self.queue_paused
            or not self.pending
            or self.close_requested
        ):
            return
        job = self.pending.pop(0)
        self.refresh_queue()
        text, source, output = job["text"], job["source"], job["output"]
        self.tasks.begin(self.operation_id + f" #{job['id']}")
        self.outcome = "failed"

        def work(cancel, progress):
            if source:
                state = os.stat(source)
                current = (state.st_dev, state.st_ino, state.st_size, state.st_mtime_ns)
                if current != job["fingerprint"]:
                    raise ValueError(
                        "Queued input archive changed; refusing to substitute different data"
                    )
            return run_core_job(
                self.operation_id,
                text,
                output,
                input_npz=source or None,
                cancel=cancel,
                progress=progress,
            )

        self.worker = StoreWorker(
            work,
            self,
        )
        self.worker.progress.connect(self.show_progress)
        self.worker.failed.connect(self.failed)
        self.worker.cancelled.connect(self.cancelled)
        self.worker.completed.connect(self.completed)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def show_progress(self, message):
        labels = {
            "Reading explicit inputs": tr(
                "Reading explicit inputs",
                "Leyendo entradas explícitas",
                "Lendo entradas explícitas",
            ),
            "Writing a new result bundle": tr(
                "Writing a new result bundle",
                "Guardando un nuevo paquete de resultados",
                "Salvando um novo pacote de resultados",
            ),
        }
        localized = labels.get(message, message)
        if message.startswith("Executing "):
            localized = tr(
                "Executing ", "Ejecutando ", "Executando "
            ) + operation_title(self.operation_id)
        self.status.setText(localized)
        self.tasks.progress(localized)

    def completed(self, result):
        self.result = result
        self.outcome = (
            "not_converged" if result["status"] == "not_converged" else "completed"
        )
        self.status.setText(
            (
                tr(
                    "Not converged; diagnostics saved: ",
                    "Sin converger; diagnósticos guardados: ",
                    "Sem convergir; diagnósticos salvos: ",
                )
                if self.outcome == "not_converged"
                else tr("Result saved: ", "Resultado guardado: ", "Resultado salvo: ")
            )
            + result["folder"]
        )
        displayed = {
            "status": result["status"],
            "result_preview": result.get("preview"),
            "arrays": result["arrays"],
            "provenance": result["provenance"],
            "folder": result["folder"],
            "manifest": result["manifest"],
        }
        self.summary.setPlainText(
            json.dumps(displayed, indent=2, ensure_ascii=False, allow_nan=False)
        )

    def failed(self, message):
        self.outcome = "failed"
        self.status.setText(
            tr(
                "Processing failed. Technical details: ",
                "El procesamiento falló. Detalles técnicos: ",
                "O processamento falhou. Detalhes técnicos: ",
            )
            + str(message)
        )

    def cancelled(self):
        self.outcome = "cancelled"
        self.status.setText(
            tr(
                "Cancelled · no completed job published",
                "Cancelado · no se publicó un trabajo completo",
                "Cancelado · nenhum trabalho completo foi publicado",
            )
        )

    def finished(self):
        self.tasks.finish(self.outcome, self.status.text())
        if self.outcome != "completed":
            self.pause_queue.setChecked(True)
        self.worker.deleteLater()
        self.worker = None
        if self.close_requested:
            self.close()
        elif self.pending and not self.queue_paused:
            QTimer.singleShot(0, self.start_next)

    def reject(self):
        if self.worker is not None:
            self.close_requested = True
            self.pending.clear()
            self.refresh_queue()
            self.worker.requestInterruption()
        else:
            self.pending.clear()
            super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            self.close_requested = True
            self.pending.clear()
            self.refresh_queue()
            self.worker.requestInterruption()
            event.ignore()
        else:
            event.accept()
