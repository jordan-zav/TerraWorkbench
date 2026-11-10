"""Session-local task audit; actual worker states, not simulated percentages."""

from datetime import datetime, timezone
import time

from qgis.PyQt.QtCore import QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QTextEdit,
)


class TaskHistoryWidget(QWidget):
    cancelRequested = pyqtSignal()

    def __init__(self, translate, parent=None):
        super().__init__(parent)
        self.tr = translate
        self.records = []
        self.active = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        self.toggle = QPushButton(
            self.tr(
                "Tasks · session history",
                "Tareas · historial de sesión",
                "Tarefas · histórico da sessão",
            )
        )
        self.toggle.setCheckable(True)
        self.cancel = QPushButton(
            self.tr(
                "Cancel active task", "Cancelar tarea activa", "Cancelar tarefa ativa"
            )
        )
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.request_cancel)
        bar.addWidget(self.toggle, 1)
        bar.addWidget(self.cancel)
        layout.addLayout(bar)
        self.details = QWidget()
        detail_layout = QVBoxLayout(self.details)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(
            [
                self.tr("Task", "Tarea", "Tarefa"),
                self.tr("State", "Estado", "Estado"),
                self.tr(
                    "Reported progress", "Progreso reportado", "Progresso informado"
                ),
                self.tr("Elapsed (s)", "Tiempo (s)", "Tempo (s)"),
            ]
        )
        self.tree.setMaximumHeight(145)
        self.tree.setColumnWidth(0, 300)
        self.message = QTextEdit()
        self.message.setReadOnly(True)
        self.message.setMaximumHeight(75)
        detail_layout.addWidget(self.tree)
        detail_layout.addWidget(self.message)
        layout.addWidget(self.details)
        self.details.hide()
        self.toggle.toggled.connect(self.details.setVisible)
        self.tree.currentItemChanged.connect(self.selected)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.tick)

    def begin(self, title):
        if self.active is not None:
            raise RuntimeError("A task is already running")
        item = QTreeWidgetItem(
            [title, self.tr("Running", "En ejecución", "Em execução"), "—", "0"]
        )
        record = {
            "title": title,
            "started": datetime.now(timezone.utc).isoformat(),
            "clock": time.monotonic(),
            "state": "running",
            "message": "",
            "item": item,
            "rows": None,
        }
        self.records.append(record)
        self.tree.addTopLevelItem(item)
        if len(self.records) > 100:
            self.records.pop(0)
            self.tree.takeTopLevelItem(0)
        self.active = record
        self.tree.setCurrentItem(item)
        self.cancel.setEnabled(True)
        self.timer.start()
        self.tick()

    def progress(self, rows):
        if self.active is not None:
            self.active["rows"] = str(rows)
            self.active["item"].setText(2, str(rows))

    def request_cancel(self):
        if self.active is not None:
            self.active["item"].setText(
                1,
                self.tr(
                    "Cancel requested",
                    "Cancelación solicitada",
                    "Cancelamento solicitado",
                ),
            )
            self.cancel.setEnabled(False)
            self.cancelRequested.emit()

    def finish(self, state, message=""):
        if self.active is None:
            return
        self.tick()
        self.timer.stop()
        record = self.active
        record["state"], record["message"] = state, str(message)
        record["finished"] = datetime.now(timezone.utc).isoformat()
        labels = {
            "not_converged": self.tr("Not converged", "Sin converger", "Sem convergir"),
            "completed": self.tr("Completed", "Completada", "Concluída"),
            "failed": self.tr("Failed", "Fallida", "Falhou"),
            "cancelled": self.tr("Cancelled", "Cancelada", "Cancelada"),
        }
        record["item"].setText(1, labels[state])
        record["item"].setToolTip(0, record["message"])
        self.active = None
        self.cancel.setEnabled(False)
        self.toggle.setText(
            self.tr(
                "Tasks · {n} in this session",
                "Tareas · {n} en esta sesión",
                "Tarefas · {n} nesta sessão",
            ).format(n=len(self.records))
        )
        if state in ("failed", "not_converged"):
            self.toggle.setChecked(True)
        self.selected(self.tree.currentItem())

    def tick(self):
        if self.active is not None:
            elapsed = time.monotonic() - self.active["clock"]
            self.active["item"].setText(3, f"{elapsed:.1f}")
            self.toggle.setText(
                self.tr(
                    "Task active · {seconds:.0f} s",
                    "Tarea activa · {seconds:.0f} s",
                    "Tarefa ativa · {seconds:.0f} s",
                ).format(seconds=elapsed)
            )

    def selected(self, item, previous=None):
        record = next((r for r in self.records if r["item"] is item), None)
        self.message.setPlainText(
            (record["started"] + "\n" + record["message"]) if record else ""
        )
