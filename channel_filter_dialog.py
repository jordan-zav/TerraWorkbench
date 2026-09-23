"""Channel-domain filtering UI; settings are explicit and provenance-ready."""

from qgis.PyQt.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QGroupBox, QLabel, QLineEdit, QMessageBox, QSpinBox, QToolButton, QVBoxLayout,
)

from .channel_filters import ChannelFilterOptions
from .qgis_compat import qt_enum
from .survey_workspace_dialog import tr


def suggested_name(channel, options, existing=()):
    suffix = options.method
    if options.method in ("mean", "median", "despike"):
        suffix += f"_w{options.window}"
        if options.method == "despike":
            suffix += f"_k{options.threshold:g}"
    elif options.method in ("lowpass", "highpass", "bandpass"):
        suffix += f"_n{options.order}_f{options.cutoff:g}"
        if options.method == "bandpass":
            suffix += f"-{options.upper_cutoff:g}"
    suffix += "_" + options.domain
    base = channel[:max(1, 197 - len(suffix))] + "__" + suffix
    name, index = base, 2
    while name in existing:
        ending = f"_{index}"
        name = base[:200 - len(ending)] + ending
        index += 1
    return name


class ChannelFilterDialog(QDialog):
    def __init__(self, store, database_id, selected="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Filter a database channel", "Filtrar un canal de la base", "Filtrar um canal do banco"))
        self.resize(710, 650)
        self.rows = store.channels(database_id)
        self.existing = {row["name"] for row in self.rows}
        self.options = None
        self._suggestion = ""
        layout = QVBoxLayout(self)
        title = QLabel(tr("Signal → process → new channel", "Señal → proceso → canal nuevo", "Sinal → processo → novo canal"))
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)
        form = QFormLayout()
        layout.addLayout(form)
        self.channel = QComboBox()
        self.channel.addItems([row["name"] for row in self.rows])
        if selected in self.existing:
            self.channel.setCurrentText(selected)
        form.addRow(tr("Signal channel", "Canal de señal", "Canal de sinal"), self.channel)
        self.method = QComboBox()
        for key, labels in (
            ("mean", ("Moving mean", "Media móvil", "Média móvel")),
            ("median", ("Moving median", "Mediana móvil", "Mediana móvel")),
            ("despike", ("Despike · Hampel", "Eliminar picos · Hampel", "Remover picos · Hampel")),
            ("detrend", ("Linear detrend", "Quitar tendencia lineal", "Remover tendência linear")),
            ("lowpass", ("Butterworth low-pass", "Butterworth pasa-bajos", "Butterworth passa-baixas")),
            ("highpass", ("Butterworth high-pass", "Butterworth pasa-altos", "Butterworth passa-altas")),
            ("bandpass", ("Butterworth band-pass", "Butterworth pasa-banda", "Butterworth passa-faixa")),
        ):
            self.method.addItem(tr(*labels), key)
        form.addRow(tr("Process", "Proceso", "Processo"), self.method)
        self.domain = QComboBox()
        for key, labels in (("samples", ("Samples · row order", "Muestras · orden de filas", "Amostras · ordem das linhas")),
                            ("time", ("Time · seconds", "Tiempo · segundos", "Tempo · segundos")),
                            ("distance", ("Distance · metres", "Distancia · metros", "Distância · metros"))):
            self.domain.addItem(tr(*labels), key)
        form.addRow(tr("Axis domain", "Dominio del eje", "Domínio do eixo"), self.domain)
        self.axis = QComboBox()
        self.axis.addItem(tr("Select numeric axis…", "Seleccionar eje numérico…", "Selecionar eixo numérico…"), "")
        for row in self.rows:
            self.axis.addItem(row["name"], row["name"])
        form.addRow(tr("Time / cumulative distance", "Tiempo / distancia acumulada", "Tempo / distância acumulada"), self.axis)
        self.group, self.sensor = QComboBox(), QComboBox()
        for widget in (self.group, self.sensor):
            widget.addItem(tr("Select grouping…", "Seleccionar agrupación…", "Selecionar agrupamento…"), None)
            widget.addItem(tr("Single series (explicit)", "Una sola serie (explícito)", "Uma série (explícito)"), "")
            for row in self.rows:
                widget.addItem(row["name"], row["name"])
        form.addRow(tr("Line / profile", "Línea / perfil", "Linha / perfil"), self.group)
        form.addRow(tr("Sensor", "Sensor", "Sensor"), self.sensor)
        self.gap = QDoubleSpinBox()
        self.gap.setDecimals(6)
        self.gap.setRange(0.000001, 1e12)
        self.gap.setValue(1.5)
        form.addRow(tr("Split at gap > (axis units)", "Separar si salto > (unidades del eje)", "Separar se intervalo > (unidades do eixo)"), self.gap)
        params = QGroupBox(tr("Filter settings", "Parámetros del filtro", "Parâmetros do filtro"))
        options_form = QFormLayout(params)
        self.window = QSpinBox()
        self.window.setRange(3, 1001)
        self.window.setSingleStep(2)
        self.window.setValue(5)
        options_form.addRow(tr("Window (odd samples)", "Ventana (muestras impares)", "Janela (amostras ímpares)"), self.window)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0.01, 1000)
        self.threshold.setValue(3)
        options_form.addRow(tr("Hampel threshold (× robust sigma)", "Umbral Hampel (× sigma robusta)", "Limiar Hampel (× sigma robusto)"), self.threshold)
        self.order = QSpinBox()
        self.order.setRange(1, 10)
        self.order.setValue(4)
        options_form.addRow(tr("Butterworth order", "Orden Butterworth", "Ordem Butterworth"), self.order)
        self.cutoff, self.upper = QDoubleSpinBox(), QDoubleSpinBox()
        for widget, value in ((self.cutoff, 0.1), (self.upper, 0.2)):
            widget.setDecimals(8)
            widget.setRange(0.00000001, 1e8)
            widget.setValue(value)
        self.frequency_label = QLabel()
        options_form.addRow(self.frequency_label, self.cutoff)
        options_form.addRow(tr("Upper cutoff (band-pass)", "Corte superior (pasa-banda)", "Corte superior (passa-faixa)"), self.upper)
        self.tolerance = QDoubleSpinBox()
        self.tolerance.setRange(0, 5)
        self.tolerance.setValue(1)
        self.tolerance.setSuffix(" %")
        options_form.addRow(tr("Sampling tolerance", "Tolerancia del muestreo", "Tolerância da amostragem"), self.tolerance)
        layout.addWidget(params)
        self.output = QLineEdit()
        out_form = QFormLayout()
        out_form.addRow(tr("New channel name", "Nombre del canal nuevo", "Nome do novo canal"), self.output)
        layout.addLayout(out_form)
        note = QLabel(tr(
            "Full database; no preview filters. Original order, separate contiguous line/sensor runs. No sorting or resampling. Nulls and gaps split the signal. Short segments and incomplete window edges become null. Time must be numeric seconds; distance must be cumulative metres, not X/Y. Maximum 3,000,000 rows per segment, not per database.",
            "Base completa; sin filtros de vista. Orden original, tramos contiguos separados por línea/sensor. Sin ordenar ni remuestrear. Nulos y huecos separan la señal. Tramos cortos y bordes sin ventana completa quedan nulos. Tiempo: segundos numéricos; distancia: metros acumulados, no X/Y. Máximo 3.000.000 de filas por tramo, no por base de datos.",
            "Banco completo; sem filtros de prévia. Ordem original, trechos contíguos separados por linha/sensor. Sem ordenar nem reamostrar. Nulos e lacunas separam o sinal. Trechos curtos e bordas sem janela completa ficam nulos. Tempo: segundos numéricos; distância: metros acumulados, não X/Y. Máximo de 3.000.000 de linhas por trecho, não por banco de dados."))
        note.setWordWrap(True)
        layout.addWidget(note)
        info = QToolButton()
        info.setText("i")
        info.setToolTip(tr("Method and libraries", "Método y librerías", "Método e bibliotecas"))
        info.clicked.connect(self.show_info)
        layout.addWidget(info)
        buttons = QDialogButtonBox(qt_enum(QDialogButtonBox, "StandardButton", "Ok") |
                                  qt_enum(QDialogButtonBox, "StandardButton", "Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        for widget in (self.channel, self.method, self.domain):
            widget.currentIndexChanged.connect(self.update_controls)
        for widget in (self.window, self.threshold, self.order, self.cutoff, self.upper):
            widget.valueChanged.connect(self.update_controls)
        self.update_controls()

    def settings(self):
        return ChannelFilterOptions(method=self.method.currentData(), domain=self.domain.currentData(),
            axis=self.axis.currentData() if self.domain.currentData() != "samples" else "",
            group=self.group.currentData() or "", sensor=self.sensor.currentData() or "",
            max_gap=self.gap.value(), window=self.window.value(), threshold=self.threshold.value(),
            order=self.order.value(), cutoff=self.cutoff.value(), upper_cutoff=self.upper.value(),
            spacing_tolerance=self.tolerance.value() / 100)

    def update_controls(self, *args):
        method, domain = self.method.currentData(), self.domain.currentData()
        butter = method in ("lowpass", "highpass", "bandpass")
        self.window.setEnabled(method in ("mean", "median", "despike"))
        self.threshold.setEnabled(method == "despike")
        for widget in (self.order, self.cutoff, self.tolerance):
            widget.setEnabled(butter)
        self.upper.setEnabled(method == "bandpass")
        self.axis.setEnabled(domain != "samples")
        self.gap.setEnabled(domain != "samples")
        unit = {"samples": tr("cycles/sample", "ciclos/muestra", "ciclos/amostra"), "time": "Hz", "distance": "cycles/m"}[domain]
        self.frequency_label.setText(tr("Cutoff", "Frecuencia de corte", "Frequência de corte") + f" ({unit})")
        if not self.output.text() or self.output.text() == self._suggestion:
            self._suggestion = suggested_name(self.channel.currentText(), self.settings(), self.existing)
            self.output.setText(self._suggestion)

    def show_info(self):
        QMessageBox.information(self, "TerraWorkbench", tr(
            "NumPy: centered complete windows, Hampel median/MAD (1.4826 factor), least-squares linear detrend on the actual axis. SciPy: Butterworth SOS, forward/backward zero phase with odd endpoint padding (squared amplitude response; effective order doubles). Cutoffs are single-pass design frequencies. No proprietary equivalence is claimed. Parameters, library versions, input versions and diagnostic counts are saved in the channel pipeline.",
            "NumPy: ventanas centradas completas, Hampel mediana/MAD (factor 1,4826), detrend lineal por mínimos cuadrados sobre el eje real. SciPy: Butterworth SOS, ida/vuelta de fase cero con extensión impar de bordes (respuesta de amplitud al cuadrado; orden efectivo doble). Los cortes son frecuencias de diseño de una pasada. No se afirma equivalencia propietaria. Parámetros, versiones de librerías/entradas y diagnósticos quedan guardados en la pipeline del canal.",
            "NumPy: janelas centradas completas, Hampel mediana/MAD (fator 1,4826), detrend linear por mínimos quadrados no eixo real. SciPy: Butterworth SOS, ida/volta de fase zero com extensão ímpar das bordas (resposta de amplitude ao quadrado; ordem efetiva dupla). Cortes são frequências de projeto de uma passagem. Sem equivalência proprietária. Parâmetros, versões de bibliotecas/entradas e diagnósticos ficam salvos no pipeline do canal."))

    def accept(self):
        try:
            if self.group.currentData() is None or self.sensor.currentData() is None:
                raise ValueError(tr("Choose line and sensor grouping explicitly.", "Elige explícitamente la agrupación por línea y sensor.", "Escolha explicitamente o agrupamento por linha e sensor."))
            self.options = self.settings()
            self.options.validate()
            output = self.output.text().strip()
            if not output or len(output) > 200 or "\x00" in output or output in self.existing:
                raise ValueError(tr("Use a new channel name (1–200 characters).", "Usa un nombre nuevo de canal (1–200 caracteres).", "Use um novo nome de canal (1–200 caracteres)."))
            self.output_name = output
            self.input_name = self.channel.currentText()
            super().accept()
        except ValueError as error:
            QMessageBox.warning(self, self.windowTitle(), str(error))
