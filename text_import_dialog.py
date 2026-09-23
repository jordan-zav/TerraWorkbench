"""Explicit text import review: format, physical lines, typed channels, preview."""

import json
from pathlib import Path

from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from .i18n import language
from .qgis_compat import qt_enum
from .text_import import ColumnSpec, TextImportOptions, inspect_text, preview, suggest_columns


def tr(en, es, pt):
    return {"en": en, "es": es, "pt": pt}.get(language(), en)


class TextImportDialog(QDialog):
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = Path(path)
        self.options = None
        self.setWindowTitle(tr("Review text import", "Revisar importación de texto", "Revisar importação de texto") + " — " + self.path.name)
        self.resize(1000, 760)
        try:
            detected, warnings, lines = inspect_text(path)
        except Exception as error:
            detected, warnings, lines = TextImportOptions(), [str(error)], []
        self.warnings = warnings
        layout = QVBoxLayout(self)
        self.notice = QLabel(tr(
            "Suggestions only. Review the numbered source, first data line and types. CRS is never guessed.",
            "Son sugerencias. Revisa el texto numerado, la primera fila de datos y los tipos. No se adivina el CRS.",
            "São sugestões. Revise o texto numerado, a primeira linha de dados e os tipos. O SRC não é inferido."))
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        form = QGridLayout()
        layout.addLayout(form)
        self.encoding = QComboBox()
        self.encoding.setEditable(True)
        for codec in ("utf-8-sig", "utf-8", "cp1252", "latin-1", "cp850", "utf-16", "utf-16-le", "utf-16-be", "utf-32"):
            self.encoding.addItem(codec, codec)
        self.mode = QComboBox()
        for labels, value in (
            (("Delimited", "Delimitado", "Delimitado"), "delimited"),
            (("Whitespace", "Espacios", "Espaços"), "whitespace"),
            (("Fixed width", "Ancho fijo", "Largura fixa"), "fixed"),
        ):
            self.mode.addItem(tr(*labels), value)
        self.delimiter = QComboBox()
        for labels, value in (
            (("Comma (,)", "Coma (,)", "Vírgula (,)"), ","),
            (("Semicolon (;)", "Punto y coma (;)", "Ponto e vírgula (;)"), ";"),
            (("Tab", "Tabulador", "Tabulação"), "\t"),
            (("Pipe (|)", "Barra (|)", "Barra (|)"), "|"),
        ):
            self.delimiter.addItem(tr(*labels), value)
        self.header = QSpinBox()
        self.header.setRange(0, 1000000)
        self.data = QSpinBox()
        self.data.setRange(1, 1000001)
        self.decimal = QComboBox()
        self.decimal.addItems([".", ","])
        self.widths = QLineEdit()
        self.widths.setPlaceholderText("10,12,8")
        self.comments = QLineEdit()
        self.nulls = QLineEdit()
        self.trim = QCheckBox(tr("Trim outer whitespace", "Quitar espacios exteriores", "Remover espaços externos"))
        self.trim.setChecked(detected.trim)
        fields = [
            (("Encoding", "Codificación", "Codificação"), self.encoding),
            (("Layout", "Formato", "Formato"), self.mode),
            (("Separator", "Separador", "Separador"), self.delimiter),
            (("Header line (0 = none)", "Fila de encabezado (0 = ninguna)", "Linha de cabeçalho (0 = nenhuma)"), self.header),
            (("First data line (1-based)", "Primera fila de datos (desde 1)", "Primeira linha de dados (a partir de 1)"), self.data),
            (("Decimal separator", "Separador decimal", "Separador decimal"), self.decimal),
            (("Fixed widths (characters)", "Anchos fijos (caracteres)", "Larguras fixas (caracteres)"), self.widths),
            (("Comment prefixes (| separated)", "Prefijos de comentario (separados por |)", "Prefixos de comentário (separados por |)"), self.comments),
            (("Null markers (; separated; empty is always null)", "Valores nulos (separados por ;, vacío siempre es nulo)", "Valores nulos (separados por ;, vazio sempre é nulo)"), self.nulls),
        ]
        for i, (labels, widget) in enumerate(fields):
            row, col = i // 3, (i % 3) * 2
            label = QLabel(tr(*labels))
            label.setWordWrap(True)
            form.addWidget(label, row, col)
            form.addWidget(widget, row, col + 1)
        form.addWidget(self.trim, 3, 0, 1, 3)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.raw = QPlainTextEdit()
        self.raw.setReadOnly(True)
        self.raw.setPlainText("\n".join(f"{i+1:5d}  {line}" for i, line in enumerate(lines[:80])))
        self.tabs.addTab(self.raw, tr("Numbered source", "Texto numerado", "Texto numerado"))
        channel_tab = QWidget()
        channel_layout = QVBoxLayout(channel_tab)
        channel_layout.addWidget(QLabel(tr("Names, types, roles and units are editable. Re-suggesting replaces these edits.",
            "Puedes editar nombres, tipos, roles y unidades. Volver a sugerir reemplaza estas ediciones.",
            "Nomes, tipos, funções e unidades são editáveis. Sugerir novamente substitui estas edições.")))
        self.channels = QTableWidget(0, 4)
        self.channels.setHorizontalHeaderLabels([tr("Name", "Nombre", "Nome"), tr("Type", "Tipo", "Tipo"), tr("Role", "Rol", "Função"), tr("Unit", "Unidad", "Unidade")])
        channel_layout.addWidget(self.channels)
        self.tabs.addTab(channel_tab, tr("Channels", "Canales", "Canais"))
        self.sample = QTableWidget()
        self.sample.setEditTriggers(qt_enum(QAbstractItemView, "EditTrigger", "NoEditTriggers"))
        self.tabs.addTab(self.sample, tr("Parsed preview", "Vista interpretada", "Prévia interpretada"))
        buttons = QHBoxLayout()
        for labels, callback in (
            (("Suggest channels", "Sugerir canales", "Sugerir canais"), self.suggest),
            (("Refresh preview", "Actualizar vista previa", "Atualizar prévia"), self.refresh_preview),
        ):
            button = QPushButton(tr(*labels))
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.status = QLabel("\n".join(warnings))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        box = QDialogButtonBox(qt_enum(QDialogButtonBox, "StandardButton", "Ok") | qt_enum(QDialogButtonBox, "StandardButton", "Cancel"))
        box.button(qt_enum(QDialogButtonBox, "StandardButton", "Ok")).setText(tr("Import with these settings", "Importar con esta configuración", "Importar com esta configuração"))
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)
        self.encoding.setCurrentIndex(self.encoding.findData(detected.encoding))
        self.mode.setCurrentIndex(self.mode.findData(detected.mode))
        self.delimiter.setCurrentIndex(max(0, self.delimiter.findData(detected.delimiter)))
        self.header.setValue(detected.header_row)
        self.data.setValue(detected.data_row)
        self.decimal.setCurrentText(detected.decimal)
        self.comments.setText("|".join(detected.comments))
        self.nulls.setText(";".join(v for v in detected.null_values if v))
        self.set_columns(detected.columns)
        self._preview_signature = None
        self._preview_source = None
        self.mode.currentIndexChanged.connect(self.update_mode)
        self.update_mode()

    def update_mode(self):
        self.delimiter.setEnabled(self.mode.currentData() == "delimited")
        self.widths.setEnabled(self.mode.currentData() == "fixed")

    def configuration(self, include_columns=True):
        widths = tuple(int(v.strip()) for v in self.widths.text().split(",") if v.strip()) if self.mode.currentData() == "fixed" else ()
        result = TextImportOptions(
            encoding=self.encoding.currentText().strip(), mode=self.mode.currentData(),
            delimiter=self.delimiter.currentData(), header_row=self.header.value(), data_row=self.data.value(),
            widths=widths, decimal=self.decimal.currentText(), comments=tuple(p.strip() for p in self.comments.text().split("|") if p.strip()),
            null_values=tuple(dict.fromkeys(["", *(v.strip() for v in self.nulls.text().split(";") if v.strip())])), trim=self.trim.isChecked())
        if include_columns:
            for i in range(self.channels.rowCount()):
                result.columns.append(ColumnSpec(self.channels.item(i, 0).text().strip(),
                    self.channels.cellWidget(i, 1).currentData(), self.channels.cellWidget(i, 2).currentData(),
                    self.channels.item(i, 3).text().strip()))
        result.validate()
        return result

    def set_columns(self, columns):
        self.channels.setRowCount(len(columns))
        for i, column in enumerate(columns):
            self.channels.setItem(i, 0, QTableWidgetItem(column.name))
            self.channels.setItem(i, 3, QTableWidgetItem(column.unit))
            kind = QComboBox()
            for labels, value in [(("Text", "Texto", "Texto"), "text"), (("Integer", "Entero", "Inteiro"), "integer"), (("Decimal", "Decimal", "Decimal"), "float")]:
                kind.addItem(tr(*labels), value)
            kind.setCurrentIndex(kind.findData(column.data_type))
            self.channels.setCellWidget(i, 1, kind)
            role = QComboBox()
            for labels, value in [(("None", "Ninguno", "Nenhuma"), ""), (("X", "X", "X"), "x"), (("Y", "Y", "Y"), "y"),
                (("Time", "Tiempo", "Tempo"), "time"), (("Line", "Línea", "Linha"), "line"), (("Sensor", "Sensor", "Sensor"), "sensor")]:
                role.addItem(tr(*labels), value)
            role.setCurrentIndex(role.findData(column.role))
            self.channels.setCellWidget(i, 2, role)
        self.channels.resizeColumnsToContents()

    def reload_source(self, options):
        import codecs
        from .text_import import SAMPLE_BYTES
        with self.path.open("rb") as handle:
            raw = handle.read(SAMPLE_BYTES)
        value = codecs.getincrementaldecoder(options.encoding)(errors="strict").decode(raw, final=False)
        self.raw.setPlainText("\n".join(f"{i+1:5d}  {line}" for i, line in enumerate(value.splitlines()[:80])))

    def suggest(self):
        try:
            options = self.configuration(False)
            self.reload_source(options)
            columns = suggest_columns(self.path, options)
            self.set_columns(columns)
            self._preview_signature = None
            self.tabs.setCurrentIndex(1)
            self.status.setText(tr("Suggestions updated. Review channels and refresh the preview.", "Sugerencias actualizadas. Revisa los canales y actualiza la vista previa.", "Sugestões atualizadas. Revise os canais e atualize a prévia."))
        except Exception as error:
            self.status.setText(str(error))

    def refresh_preview(self):
        try:
            before = self.path.stat()
            options = self.configuration()
            self.reload_source(options)
            rows = preview(self.path, options)
            if not rows:
                raise ValueError("No records at the chosen first data line.")
            after = self.path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError("The source changed during preview; retry from a stable file.")
            self.sample.clear()
            self.sample.setColumnCount(len(options.columns))
            self.sample.setRowCount(len(rows))
            self.sample.setHorizontalHeaderLabels([c.name for c in options.columns])
            self.sample.setVerticalHeaderLabels([str(number) for number, _ in rows])
            for i, (_, values) in enumerate(rows):
                for j, value in enumerate(values):
                    self.sample.setItem(i, j, QTableWidgetItem("∅" if value is None else str(value)))
            self.sample.resizeColumnsToContents()
            self._preview_signature = json.dumps(options.to_dict(), sort_keys=True)
            self._preview_source = (after.st_size, after.st_mtime_ns)
            self.tabs.setCurrentIndex(2)
            self.status.setText(tr("Preview OK. Full import validates every row; an error aborts this database.", "Vista previa correcta. La importación valida todas las filas; un error cancela esta base.", "Prévia correta. A importação valida todas as linhas; um erro cancela este banco."))
            return True
        except Exception as error:
            self._preview_signature = None
            self.status.setText(str(error))
            return False

    def accept(self):
        try:
            current = self.configuration()
            signature = json.dumps(current.to_dict(), sort_keys=True)
            stat = self.path.stat()
            if signature != self._preview_signature or (stat.st_size, stat.st_mtime_ns) != self._preview_source:
                self.refresh_preview()
                # Deliberately require a second explicit click after viewing the
                # parsed result, rather than importing immediately on a guess.
                return
            current.source_size, current.source_mtime_ns = self._preview_source
            self.options = current
            super().accept()
        except Exception as error:
            QMessageBox.warning(self, "TerraWorkbench", str(error))
