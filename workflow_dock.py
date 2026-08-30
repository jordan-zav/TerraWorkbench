"""Dockable filter-stack workflow for TerraWorkbench."""

from __future__ import annotations

from dataclasses import dataclass, field
import html
import importlib.util
import json
from pathlib import Path
import re

import numpy as np

from qgis.PyQt.QtCore import (
    QPoint,
    QPointF,
    QProcess,
    QProcessEnvironment,
    QRectF,
    Qt,
    QUrl,
    QUrlQuery,
    pyqtSignal,
)
from qgis.PyQt.QtGui import (
    QColor,
    QDesktopServices,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
)
from qgis.PyQt.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QMenu,
    QPushButton,
    QProgressDialog,
    QSpinBox,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsProcessing,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingMultiStepFeedback,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsProcessingUtils,
    QgsProject,
    QgsRasterLayer,
    QgsSettings,
    QgsVectorLayer,
)

from .qgis_compat import (
    PROCESSING_NUMBER_INTEGER,
    processing_parameter_is_optional,
    qt_enum,
)
from .raster_io import (
    read_raster,
    restore_raster_order,
    to_regular_data_array,
    write_geotiff,
)
from .spectral import (
    apply_spectrum,
    apply_transfer,
    finish_fft_grid,
    frequency_grid,
    prepare_fft_grid,
    radial_power_spectrum,
)
from .data_import import (
    import_survey_grid,
    list_raster_subdatasets,
    list_vector_layers,
)
from .embedded_qpip import activate_dependency_path, dependency_directory
from .embedded_qpip.manager import python_command
from .geosoft_runtime import (
    GeosoftRuntime,
    find_geosoft_runtime,
    validate_geosoft_location,
)
from .i18n import language, text, translate
from .settings_dialog import (
    KEY_ADD_RESULT,
    KEY_BAND,
    KEY_CONFIRM_CLEAR,
    KEY_INSPECTOR,
    KEY_KEEP,
    KEY_LOCAL_DATA,
    KEY_OUTPUT,
    KEY_TOOLTIPS,
    SettingsDialog,
)


PLUGIN_PREFIX = "terraworkbench:"
PIPELINE_FORMAT_VERSION = 1
_FIXED_PARAMETERS = {"INPUT", "BAND", "OUTPUT"}
_SEARCH_TEXT_ROLE = int(qt_enum(Qt, "ItemDataRole", "UserRole")) + 1

_KNOWLEDGE_REPOSITORIES = (
    (
        "Campos potenciales y filtros",
        (
            ("Harmonica", "https://github.com/fatiando/harmonica", "Procesamiento, modelado, fuentes equivalentes, Euler y lectura GRD."),
            ("Verde", "https://github.com/fatiando/verde", "Gridding, tendencias y validación espacial."),
            ("Boule", "https://github.com/fatiando/boule", "Elipsoides y gravedad normal."),
            ("Choclo", "https://github.com/fatiando/choclo", "Kernels rápidos de gravedad y magnetismo."),
            ("GMT", "https://github.com/GenericMappingTools/gmt", "Procesamiento maduro de grillas y filtros FFT."),
            ("xrft", "https://github.com/xgcm/xrft", "FFT con dimensiones y coordenadas xarray."),
        ),
    ),
    (
        "Suites geofísicas y QGIS",
        (
            ("PyGMI", "https://github.com/Patrick-Cole/pygmi", "Suite abierta de magnetismo, gravedad, raster y modelado."),
            ("SGTool", "https://github.com/swaxi/SGTool", "Plugin QGIS/ArcGIS para cálculos de campos potenciales."),
            ("QGIS", "https://github.com/qgis/QGIS", "Código del host, Processing, tareas y raster providers."),
        ),
    ),
    (
        "Inversión y modelos 3D",
        (
            ("SimPEG", "https://github.com/simpeg/simpeg", "GRAV, MAG, MVI, regularización e inversión conjunta."),
            ("discretize", "https://github.com/simpeg/discretize", "TensorMesh, TreeMesh y operadores."),
            ("geoana", "https://github.com/simpeg/geoana", "Soluciones analíticas para pruebas sintéticas."),
            ("pyGIMLi", "https://github.com/gimli-org/pyGIMLi", "Modelado e inversión restringida y conjunta."),
            ("Euler inversion", "https://github.com/compgeolab/euler-inversion", "Investigación reproducible de localización de fuentes."),
            ("GemPy", "https://github.com/gempy-project/gempy", "Modelado geológico implícito y estocástico."),
            ("LoopStructural", "https://github.com/Loop3D/LoopStructural", "Modelado estructural implícito."),
        ),
    ),
    (
        "Campo principal y formatos",
        (
            ("ppigrf", "https://github.com/IAGA-VMOD/ppigrf", "IGRF-14 puro en Python."),
            ("GDAL", "https://github.com/OSGeo/gdal", "Formatos raster/vector y metadatos."),
            ("Rasterio", "https://github.com/rasterio/rasterio", "Lectura, escritura y validación raster sobre GDAL."),
            ("awesome-open-geoscience", "https://github.com/softwareunderground/awesome-open-geoscience", "Catálogo comunitario para descubrir proyectos abiertos."),
        ),
    ),
    (
        "Radiometría gamma",
        (
            ("IAEA radioelement guidelines", "https://www-pub.iaea.org/MTCD/publications/PDF/te_1363_web/PDF/Contents.pdf", "Normas de adquisición, calibración, procesamiento, incertidumbre y cartografía radiométrica."),
            ("Geoscience Australia Radiometrics", "https://www.ga.gov.au/scientific-topics/disciplines/geophysics/radiometrics", "Productos oficiales K, eU, eTh, dosis y composiciones ternarias."),
        ),
    ),
)

_REPOSITORY_DESCRIPTIONS_EN = {
    "Harmonica": "Processing, modelling, equivalent sources, Euler and GRD reading.",
    "Verde": "Gridding, trends and spatial validation.",
    "Boule": "Reference ellipsoids and normal gravity.",
    "Choclo": "Fast gravity and magnetic kernels.",
    "GMT": "Mature grid processing and FFT filters.",
    "xrft": "FFT with labelled xarray dimensions and coordinates.",
    "PyGMI": "Open magnetic, gravity, raster and modelling suite.",
    "SGTool": "QGIS/ArcGIS plugin for potential-field calculations.",
    "QGIS": "Host application, Processing framework, tasks and raster providers.",
    "SimPEG": "Gravity, magnetic, MVI, regularization and joint inversion.",
    "discretize": "TensorMesh, TreeMesh and numerical operators.",
    "geoana": "Analytical solutions for synthetic validation.",
    "pyGIMLi": "Constrained and joint modelling and inversion.",
    "Euler inversion": "Reproducible source-location research.",
    "GemPy": "Implicit and stochastic geological modelling.",
    "LoopStructural": "Implicit structural modelling.",
    "ppigrf": "Pure-Python IGRF-14 implementation.",
    "GDAL": "Raster/vector formats and metadata.",
    "Rasterio": "Raster reading, writing and validation on GDAL.",
    "awesome-open-geoscience": "Community catalogue of open geoscience projects.",
    "IAEA radioelement guidelines": "Acquisition, calibration, processing, uncertainty and radiometric-mapping guidance.",
    "Geoscience Australia Radiometrics": "Official K, eU, eTh, dose and ternary radiometric products.",
}


@dataclass
class PipelineStep:
    """A serializable Processing algorithm invocation."""

    algorithm_id: str
    parameters: dict[str, int | float | None] = field(default_factory=dict)

    def to_dict(self):
        return {
            "algorithm": self.algorithm_id,
            "parameters": dict(self.parameters),
        }

    @classmethod
    def from_dict(cls, value):
        algorithm_id = str(value.get("algorithm", ""))
        parameters = value.get("parameters", {})
        if not algorithm_id.startswith(PLUGIN_PREFIX) or not isinstance(
            parameters, dict
        ):
            raise ValueError("Invalid TerraWorkbench pipeline step")
        if _FIXED_PARAMETERS.intersection(parameters):
            raise ValueError("Pipeline steps cannot override input, band or output")
        return cls(algorithm_id, dict(parameters))


def available_algorithms():
    """Return registered TerraWorkbench algorithms in display order."""
    algorithms = [
        algorithm
        for algorithm in QgsApplication.processingRegistry().algorithms()
        if algorithm.id().startswith(PLUGIN_PREFIX)
        and isinstance(
            algorithm.parameterDefinition("INPUT"), QgsProcessingParameterRasterLayer
        )
        and all(
            parameter.name() in _FIXED_PARAMETERS
            or isinstance(parameter, QgsProcessingParameterNumber)
            for parameter in algorithm.parameterDefinitions()
        )
    ]
    return sorted(
        algorithms, key=lambda algorithm: (algorithm.group(), algorithm.displayName())
    )


def algorithm_defaults(algorithm):
    """Return editable numeric defaults for an algorithm."""
    defaults = {}
    for parameter in algorithm.parameterDefinitions():
        if parameter.name() in _FIXED_PARAMETERS:
            continue
        if not isinstance(parameter, QgsProcessingParameterNumber):
            raise ValueError(
                f"Unsupported pipeline parameter {parameter.name()} in {algorithm.id()}"
            )
        defaults[parameter.name()] = parameter.defaultValue()
    return defaults


def algorithm_domain(algorithm):
    """Return the declared numerical domain shown to geophysical users."""
    return getattr(algorithm, "processing_domain", "GRID / UNSPECIFIED")


def _safe_output_stem(index, algorithm):
    stem = re.sub(r"[^0-9A-Za-z_-]+", "_", algorithm.name()).strip("_")
    return f"{index:02d}_{stem or 'result'}"


def run_filter_stack(
    input_raster,
    band,
    steps,
    *,
    context=None,
    feedback=None,
    output_directory=None,
    keep_intermediate=False,
):
    """Run a stack, combining compatible FFT operators into one forward FFT."""
    if not steps:
        raise QgsProcessingException("Add at least one filter to the stack.")

    import processing

    context = context or QgsProcessingContext()
    if context.project() is None:
        context.setProject(QgsProject.instance())
    base_feedback = feedback or QgsProcessingFeedback()
    multi_feedback = QgsProcessingMultiStepFeedback(len(steps), base_feedback)
    output_path = Path(output_directory) if output_directory else None
    if output_path is not None:
        output_path.mkdir(parents=True, exist_ok=True)

    from .algorithms.spectral_filters import SpectralFilterBase

    spectral_algorithms = [
        QgsApplication.processingRegistry().algorithmById(step.algorithm_id)
        for step in steps
    ]
    if all(isinstance(algorithm, SpectralFilterBase) for algorithm in spectral_algorithms):
        preprocessing = [
            algorithm.preprocessing_values(step.parameters, context)
            for algorithm, step in zip(spectral_algorithms, steps)
        ]
        if all(values[:3] == preprocessing[0][:3] for values in preprocessing[1:]):
            return _run_combined_spectral_stack(
                input_raster,
                band,
                steps,
                spectral_algorithms,
                preprocessing,
                context,
                base_feedback,
                output_path,
                keep_intermediate,
            )

    current_input = input_raster
    outputs = []
    last_index = len(steps)
    for index, step in enumerate(steps, start=1):
        if multi_feedback.isCanceled():
            raise QgsProcessingException("Filter stack was canceled.")
        algorithm = QgsApplication.processingRegistry().algorithmById(step.algorithm_id)
        if algorithm is None or not step.algorithm_id.startswith(PLUGIN_PREFIX):
            raise QgsProcessingException(
                f"Algorithm is not available: {step.algorithm_id}"
            )

        multi_feedback.setCurrentStep(index - 1)
        parameters = {
            **step.parameters,
            "INPUT": current_input,
            "BAND": int(band),
        }
        persist = output_path is not None and (keep_intermediate or index == last_index)
        if persist:
            parameters["OUTPUT"] = str(
                output_path / f"{_safe_output_stem(index, algorithm)}.tif"
            )
        else:
            parameters["OUTPUT"] = QgsProcessing.TEMPORARY_OUTPUT

        result = processing.run(
            step.algorithm_id,
            parameters,
            context=context,
            feedback=multi_feedback,
            is_child_algorithm=True,
        )
        current_input = result["OUTPUT"]
        outputs.append(current_input)

    return current_input, outputs


def _run_combined_spectral_stack(
    input_raster,
    band,
    steps,
    algorithms,
    preprocessing,
    context,
    feedback,
    output_path,
    keep_intermediate,
):
    """Apply compatible Fourier operators to one prepared forward transform."""
    source_layer = (
        input_raster
        if isinstance(input_raster, QgsRasterLayer)
        else QgsRasterLayer(str(input_raster), "FFT stack input")
    )
    if not source_layer.isValid():
        raise QgsProcessingException("The FFT stack input raster is not valid.")
    grid = read_raster(source_layer, int(band))
    orientation = to_regular_data_array(grid)
    data = orientation.data
    northing = np.asarray(data.coords["northing"])
    easting = np.asarray(data.coords["easting"])
    spacing_northing = abs(float(northing[1] - northing[0]))
    spacing_easting = abs(float(easting[1] - easting[0]))
    detrend, padding, taper, _restore = preprocessing[0]
    prepared, fft_state = prepare_fft_grid(data.values, detrend, padding, taper)
    k_east, k_north, radial = frequency_grid(
        prepared.shape, spacing_northing, spacing_easting
    )
    transformed = np.fft.fft2(prepared)
    combined = np.ones(prepared.shape, dtype=np.complex128)
    outputs = []
    last_index = len(steps)
    feedback.pushInfo(
        "Combined FFT stack: one detrend/padding stage and one forward transform; "
        f"{last_index} transfer operators."
    )
    for index, (step, algorithm, settings) in enumerate(
        zip(steps, algorithms, preprocessing), start=1
    ):
        if feedback.isCanceled():
            raise QgsProcessingException("Filter stack was canceled.")
        algorithm.prepare(grid, step.parameters, context, feedback)
        response = algorithm.transfer(
            k_east, k_north, radial, step.parameters, context
        )
        if not np.isfinite(response).all():
            raise QgsProcessingException(
                f"Non-finite FFT response: {algorithm.displayName()}"
            )
        combined *= response
        filtered = finish_fft_grid(
            apply_spectrum(transformed, combined),
            fft_state,
            restore_trend=settings[3],
        )
        values = restore_raster_order(filtered, orientation)
        persist = output_path is not None and (
            keep_intermediate or index == last_index
        )
        if persist:
            destination = output_path / f"{_safe_output_stem(index, algorithm)}.tif"
        else:
            destination = Path(
                QgsProcessingUtils.generateTempFilename(
                    f"{_safe_output_stem(index, algorithm)}.tif"
                )
            )
        write_geotiff(
            str(destination),
            values,
            grid,
            f"Combined FFT stack through {algorithm.displayName()}",
        )
        outputs.append(str(destination))
        feedback.setProgress(100.0 * index / last_index)
    return outputs[-1], outputs


class SpectrumPlot(QWidget):
    """Small dependency-free Qt plot for radial power spectra."""

    def __init__(self, frequencies, original, filtered=None, parent=None):
        super().__init__(parent)
        self.frequencies = np.asarray(frequencies, dtype=float)
        self.original = np.asarray(original, dtype=float)
        self.filtered = None if filtered is None else np.asarray(filtered, dtype=float)
        self.setMinimumSize(560, 300)

    def _curve(self, painter, rectangle, values, color, lower, upper):
        logged = np.log10(np.maximum(values, np.finfo(float).tiny))
        span = max(upper - lower, np.finfo(float).eps)
        points = []
        for index, value in enumerate(logged):
            x = rectangle.left() + rectangle.width() * index / max(len(logged) - 1, 1)
            y = rectangle.bottom() - rectangle.height() * (value - lower) / span
            points.append(QPointF(x, y))
        if not points:
            return
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        painter.setPen(QPen(color, 2.0))
        painter.drawPath(path)

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(qt_enum(QPainter, "RenderHint", "Antialiasing"))
        painter.fillRect(self.rect(), self.palette().base())
        plot = QRectF(
            58.0, 18.0, max(self.width() - 82.0, 10.0), max(self.height() - 68.0, 10.0)
        )
        curves = [self.original]
        if self.filtered is not None:
            curves.append(self.filtered)
        logs = [np.log10(np.maximum(curve, np.finfo(float).tiny)) for curve in curves]
        lower = min(float(np.nanmin(curve)) for curve in logs)
        upper = max(float(np.nanmax(curve)) for curve in logs)
        painter.setPen(QPen(self.palette().mid().color(), 1.0))
        painter.drawRect(plot)
        self._curve(painter, plot, self.original, QColor("#202020"), lower, upper)
        if self.filtered is not None:
            self._curve(painter, plot, self.filtered, QColor("#d32f2f"), lower, upper)
        painter.setPen(self.palette().text().color())
        painter.drawText(8, 20, text("log power", "log potencia"))
        painter.drawText(int(plot.left()), self.height() - 16, "0")
        maximum = float(self.frequencies[-1]) if self.frequencies.size else 0.0
        painter.drawText(
            int(plot.right()) - 125,
            self.height() - 16,
            f"{maximum:.4g} {text('rad/unit', 'rad/unidad')}",
        )
        painter.drawText(int(plot.center().x()) - 45, self.height() - 16, text("wavenumber", "número de onda"))
        painter.setPen(QPen(QColor("#202020"), 2.0))
        painter.drawLine(65, 34, 92, 34)
        painter.setPen(self.palette().text().color())
        painter.drawText(98, 39, text("Input", "Entrada"))
        if self.filtered is not None:
            painter.setPen(QPen(QColor("#d32f2f"), 2.0))
            painter.drawLine(155, 34, 182, 34)
            painter.setPen(self.palette().text().color())
            painter.drawText(188, 39, text("Predicted output", "Salida prevista"))
        painter.end()


class SpectrumDialog(QDialog):
    def __init__(self, frequencies, original, filtered, note, parent=None):
        super().__init__(parent)
        self.setWindowTitle(
            text(
                "TerraWorkbench — Radial spectrum preview",
                "TerraWorkbench — Vista previa del espectro radial",
            )
        )
        layout = QVBoxLayout(self)
        description = QLabel(note)
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addWidget(SpectrumPlot(frequencies, original, filtered, self), 1)
        buttons = QDialogButtonBox(
            qt_enum(QDialogButtonBox, "StandardButton", "Close"), parent=self
        )
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class KnowledgeBaseDialog(QDialog):
    """User-facing scientific library with trusted, clickable references."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TerraWorkbenchKnowledgeBase")
        self.setWindowFlags(
            self.windowFlags() | qt_enum(Qt, "WindowType", "Tool")
        )
        self.setMinimumSize(620, 480)
        self.setMaximumSize(900, 760)
        self.resize(760, 680)

        layout = QVBoxLayout(self)
        self.intro = QLabel()
        self.intro.setWordWrap(True)
        layout.addWidget(self.intro)

        self.tabs = QTabWidget()
        self.repository_browser = QTextBrowser()
        self.repository_browser.setOpenExternalLinks(True)
        self.tabs.addTab(self.repository_browser, "")

        self.reference_browser = QTextBrowser()
        self.reference_browser.setOpenExternalLinks(True)
        self.tabs.addTab(self.reference_browser, "")
        layout.addWidget(self.tabs, 1)

        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.close_button = QPushButton()
        self.close_button.clicked.connect(self.hide)
        layout.addWidget(self.close_button)
        self.retranslate()

    def retranslate(self):
        self.setWindowTitle(
            text("TerraWorkbench — Knowledge Base", "TerraWorkbench — Base de conocimiento")
        )
        self.intro.setText(
            text(
                "Geophysical scientific library. Links open trusted official documentation, repositories and tests.",
                "Biblioteca científica geofísica. Los enlaces abren documentación oficial confiable, repositorios y pruebas.",
            )
        )
        self.repository_browser.setHtml(self._repository_html())
        self.tabs.setTabText(0, text("Trusted repositories", "Repositorios confiables"))
        self.tabs.setTabText(1, text("MAG / GRAV / RAD reference", "Referencia MAG / GRAV / RAD"))
        reference_name = {
            "en": "potential_fields_reference_en.md",
            "es": "geofisica_potencial_referencia.md",
            "pt": "potential_fields_reference_pt.md",
        }[language()]
        reference_path = Path(__file__).parent / "docs" / "knowledge_base" / reference_name
        if reference_path.is_file():
            self.reference_browser.setMarkdown(reference_path.read_text(encoding="utf-8"))
        else:
            self.reference_browser.setPlainText(
                text(
                    "The packaged scientific reference could not be found.",
                    "No se encontró la referencia científica empaquetada.",
                )
            )
        self.note.setText(
            text(
                "References support study and comparison. They do not imply a dependency, commercial-software equivalence or automatic permission to copy code.",
                "Una referencia sirve para estudiar y comparar. No implica dependencia, equivalencia con software comercial ni permiso automático para copiar código.",
            )
        )
        self.close_button.setText(text("Close", "Cerrar"))

    @staticmethod
    def _repository_html():
        sections = [
            f"<h2>{text('Open geophysical reference library', 'Biblioteca abierta de referencia geofísica')}</h2>",
            f"<p>{text('Click a project name to open its canonical repository.', 'Haz clic en el nombre de un proyecto para abrir su repositorio canónico.')}</p>",
        ]
        for title, repositories in _KNOWLEDGE_REPOSITORIES:
            english_title = {
                "Campos potenciales y filtros": "Potential fields and filters",
                "Suites geofísicas y QGIS": "Geophysical suites and QGIS",
                "Inversión y modelos 3D": "Inversion and 3D models",
                "Campo principal y formatos": "Main field and formats",
                "Radiometría gamma": "Gamma-ray spectrometry",
            }[title]
            sections.append(f"<h3>{text(english_title, title)}</h3><ul>")
            for name, url, description in repositories:
                localized_description = text(
                    _REPOSITORY_DESCRIPTIONS_EN.get(name, description), description
                )
                sections.append(
                    f'<li><a href="{url}"><b>{name}</b></a> — {localized_description}</li>'
                )
            sections.append("</ul>")
        return "".join(sections)


class FilterInfoDialog(QDialog):
    """Compact per-filter scientific and numerical explanation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TerraWorkbenchFilterInfo")
        self.algorithm = None
        self.setWindowFlags(
            self.windowFlags() | qt_enum(Qt, "WindowType", "Tool")
        )
        self.setMinimumSize(480, 400)
        self.setMaximumSize(620, 720)
        self.resize(540, 580)
        layout = QVBoxLayout(self)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        layout.addWidget(self.browser, 1)
        self.close_button = QPushButton()
        self.close_button.clicked.connect(self.hide)
        layout.addWidget(self.close_button)
        self.retranslate()

    def retranslate(self):
        self.close_button.setText(text("Close", "Cerrar"))
        if self.algorithm is None:
            self.setWindowTitle(
                text(
                    "TerraWorkbench — Filter information",
                    "TerraWorkbench — Información del filtro",
                )
            )
        else:
            self.set_algorithm(self.algorithm)

    def set_algorithm(self, algorithm):
        """Render QGIS help, parameters and trusted reference links."""
        self.algorithm = algorithm
        domain = translate(algorithm_domain(algorithm))
        try:
            help_text = algorithm.shortHelpString().strip()
        except (AttributeError, RuntimeError):
            help_text = ""
        if not help_text:
            help_text = text(
                "No extended description has been written for this algorithm yet. Review its parameters and the TerraWorkbench scientific reference before interpretation.",
                "Aún no se ha escrito una descripción ampliada para este algoritmo. Revise sus parámetros y la referencia científica de TerraWorkbench antes de interpretarlo.",
            )

        parameter_rows = []
        for parameter in algorithm.parameterDefinitions():
            default = parameter.defaultValue()
            default_text = "—" if default is None else str(default)
            parameter_rows.append(
                "<tr>"
                f"<td><code>{html.escape(parameter.name())}</code></td>"
                f"<td>{html.escape(parameter.description())}</td>"
                f"<td>{html.escape(default_text)}</td>"
                "</tr>"
            )

        links = _algorithm_reference_links(algorithm)
        link_items = "".join(
            f'<li><a href="{url}">{html.escape(name)}</a></li>'
            for name, url in links
        )
        self.setWindowTitle(
            f"TerraWorkbench — {algorithm.displayName()}"
        )
        self.browser.setHtml(
            f"<h2>{html.escape(algorithm.displayName())}</h2>"
            f"<p><b>{text('Group', 'Grupo')}:</b> {html.escape(algorithm.group())}<br>"
            f"<b>{text('Numerical domain', 'Dominio numérico')}:</b> {html.escape(domain)}<br>"
            f"<b>ID Processing:</b> <code>{html.escape(algorithm.id())}</code></p>"
            f"<h3>{text('What it does', 'Qué hace')}</h3><p>{html.escape(translate(help_text))}</p>"
            f"<h3>{text('Parameters', 'Parámetros')}</h3>"
            f"<table cellspacing='4'><tr><th>{text('Name', 'Nombre')}</th><th>{text('Description', 'Descripción')}</th>"
            f"<th>{text('Default', 'Predeterminado')}</th></tr>{''.join(parameter_rows)}</table>"
            f"<h3>{text('Trusted reading', 'Lecturas confiables')}</h3>"
            f"<ul>{link_items}</ul>"
            f"<p><i>{text('Check units, CRS, edge effects, noise and geological assumptions before interpreting the output.', 'Compruebe unidades, SRC, efectos de borde, ruido y supuestos geológicos antes de interpretar la salida.')}</i></p>"
        )


def _algorithm_reference_links(algorithm):
    """Return conservative user-reading links for an algorithm family."""
    searchable = " ".join(
        (algorithm.group(), algorithm.displayName(), algorithm_domain(algorithm))
    ).casefold()
    links = []
    if any(term in searchable for term in ("gravity", "magnetic", "harmonica")):
        links.append(("Harmonica", "https://github.com/fatiando/harmonica"))
    if any(term in searchable for term in ("fft", "spectral", "magmap")):
        links.append(("GMT grid FFT reference", "https://github.com/GenericMappingTools/gmt"))
    if any(term in searchable for term in ("igrf", "field-direction", "pole", "equator")):
        links.append(("ppigrf / IGRF-14", "https://github.com/IAGA-VMOD/ppigrf"))
    if any(term in searchable for term in ("bouguer", "normal gravity", "latitude")):
        links.append(("Boule geodetic reference", "https://github.com/fatiando/boule"))
    if any(term in searchable for term in ("gamma", "radiometr", "dose", "euth")):
        links.extend(
            (
                ("IAEA radioelement-mapping guidelines", "https://www-pub.iaea.org/MTCD/publications/PDF/te_1363_web/PDF/Contents.pdf"),
                ("Geoscience Australia radiometrics", "https://www.ga.gov.au/scientific-topics/disciplines/geophysics/radiometrics"),
            )
        )
    if not links:
        links.append(("TerraWorkbench reference ecosystem", "https://github.com/fatiando/harmonica"))
    return links


class FilterStackDock(QDockWidget):
    """Right-side QGIS panel for composing sequential raster filters."""

    languageChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("TerraWorkbench — Filter Stack", parent)
        self.setObjectName("TerraWorkbenchFilterStackDock")
        self.setMinimumWidth(300)
        self.setMaximumWidth(380)
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("icon.svg"))))
        self._parameter_editors = {}
        self._algorithm_labels = {}
        self._build_ui()
        self.apply_preferences()
        self.retranslate()
        self._connect_project()
        self.refresh_layers()
        self.refresh_algorithms()

    def _build_ui(self):
        body = QWidget(self)
        layout = QVBoxLayout(body)

        self.source_group = QGroupBox("Input raster")
        source_layout = QFormLayout(self.source_group)
        self.layer_combo = QComboBox()
        self.layer_combo.setSizeAdjustPolicy(
            qt_enum(
                QComboBox,
                "SizeAdjustPolicy",
                "AdjustToMinimumContentsLengthWithIcon",
            )
        )
        self.band_spin = QSpinBox()
        self.band_spin.setRange(1, 9999)
        self.band_spin.setValue(1)
        source_layout.addRow("Layer", self.layer_combo)
        source_layout.addRow("Band", self.band_spin)
        layout.addWidget(self.source_group)

        add_row = QHBoxLayout()
        self.algorithm_combo = QComboBox()
        self.algorithm_combo.hide()
        self.algorithm_button = QPushButton("Choose filter…")
        self.algorithm_button.setToolTip(
            "Open the compact filter chooser to the left of TerraWorkbench"
        )
        self.add_button = QPushButton("Add filter")
        add_row.addWidget(self.algorithm_button, 1)
        add_row.addWidget(self.add_button)
        layout.addLayout(add_row)

        self.step_list = QListWidget()
        self.step_list.setAlternatingRowColors(True)
        self.step_list.setDragDropMode(
            qt_enum(QAbstractItemView, "DragDropMode", "InternalMove")
        )
        self.step_list.setDefaultDropAction(
            qt_enum(Qt, "DropAction", "MoveAction")
        )
        self.step_list.setDragEnabled(True)
        self.step_list.setAcceptDrops(True)
        self.step_list.setDropIndicatorShown(True)
        layout.addWidget(self.step_list, 1)

        self.stack_actions_layout = QGridLayout()
        self.duplicate_button = QPushButton("Duplicate")
        self.remove_button = QPushButton("Remove")
        self.clear_button = QPushButton("Clear")
        self.stack_actions_layout.addWidget(self.duplicate_button, 0, 0)
        self.stack_actions_layout.addWidget(self.remove_button, 0, 1)
        self.stack_actions_layout.addWidget(self.clear_button, 0, 2)
        layout.addLayout(self.stack_actions_layout)

        self.inspector = QDialog(self.parentWidget() or self)
        self.inspector.setObjectName("TerraWorkbenchFilterInspector")
        self.inspector.setWindowTitle("TerraWorkbench — Filter inspector")
        self.inspector.setWindowFlags(
            self.inspector.windowFlags() | qt_enum(Qt, "WindowType", "Tool")
        )
        self.inspector.setMinimumWidth(400)
        self.inspector.setMaximumWidth(460)
        self.inspector.resize(440, 620)
        inspector_layout = QVBoxLayout(self.inspector)
        self.inspector_tabs = QTabWidget()
        parameter_tab = QWidget()
        parameter_tab_layout = QVBoxLayout(parameter_tab)
        self.parameter_group = QGroupBox("Selected filter parameters")
        self.parameter_form = QFormLayout(self.parameter_group)
        self.empty_parameters = QLabel("Select a filter to edit its parameters.")
        self.parameter_form.addRow(self.empty_parameters)
        parameter_tab_layout.addWidget(self.parameter_group)
        parameter_tab_layout.addStretch(1)
        spectrum_tab = QWidget()
        spectrum_layout = QVBoxLayout(spectrum_tab)
        self.spectrum_note = QLabel(
            "Compare the radial power spectrum of the input with the predicted FFT stack."
        )
        self.spectrum_note.setWordWrap(True)
        spectrum_layout.addWidget(self.spectrum_note)
        self.preview_button = QPushButton("Open spectrum preview…")
        spectrum_layout.addWidget(self.preview_button)
        spectrum_layout.addStretch(1)
        igrf_tab = QWidget()
        igrf_layout = QVBoxLayout(igrf_tab)
        self.igrf_note = QLabel(
            "IGRF mode 1 evaluates IGRF-14 at the raster center, survey date and altitude. "
            "Use mode 0 to enter inclination and declination manually. Positive inclination "
            "is downward; declination is clockwise from geographic North."
        )
        self.igrf_note.setWordWrap(True)
        igrf_layout.addWidget(self.igrf_note)
        igrf_layout.addStretch(1)
        self.inspector_tabs.addTab(parameter_tab, "Parameters")
        self.inspector_tabs.addTab(spectrum_tab, "Spectrum")
        self.inspector_tabs.addTab(igrf_tab, "IGRF")
        inspector_layout.addWidget(self.inspector_tabs)
        self.close_inspector = QPushButton("Close")
        self.close_inspector.clicked.connect(self.inspector.hide)
        inspector_layout.addWidget(self.close_inspector)
        self.algorithm_picker = QDialog(self.parentWidget() or self)
        self.algorithm_picker.setObjectName("TerraWorkbenchAlgorithmPicker")
        self.algorithm_picker.setWindowTitle("Choose a TerraWorkbench filter")
        self.algorithm_picker.setWindowFlags(
            self.algorithm_picker.windowFlags()
            | qt_enum(Qt, "WindowType", "Tool")
        )
        self.algorithm_picker.setMinimumWidth(360)
        self.algorithm_picker.setMaximumWidth(440)
        self.algorithm_picker.resize(410, 520)
        picker_layout = QVBoxLayout(self.algorithm_picker)
        self.domain_note = QLabel(
            "SPATIAL = cell-neighbour operation; FFT/HARMONICA = library FFT; "
            "FFT/MAGMAP-LIKE = detrend + reflected padding + taper + combined "
            "wavenumber operators; MIXED = components from more than one domain."
        )
        self.domain_note.setWordWrap(True)
        picker_layout.addWidget(self.domain_note)
        self.search_label = QLabel("Search by method, group or abbreviation")
        picker_layout.addWidget(self.search_label)
        self.algorithm_search = QLineEdit()
        self.algorithm_search.setPlaceholderText("RTP, upward, THDR, Butterworth…")
        picker_layout.addWidget(self.algorithm_search)
        self.algorithm_list = QListWidget()
        self.algorithm_list.setAlternatingRowColors(True)
        picker_layout.addWidget(self.algorithm_list, 1)
        picker_buttons = QHBoxLayout()
        picker_buttons.addStretch(1)
        self.close_picker = QPushButton("Close")
        self.close_picker.clicked.connect(self.algorithm_picker.hide)
        picker_buttons.addWidget(self.close_picker)
        picker_layout.addLayout(picker_buttons)

        self.knowledge_base = KnowledgeBaseDialog(self.parentWidget() or self)
        self.filter_info = FilterInfoDialog(self.parentWidget() or self)
        self.settings_dialog = SettingsDialog(self.parentWidget() or self)
        self.settings_dialog.preferencesChanged.connect(self.preferences_changed)

        self.output_group = QGroupBox("Outputs")
        output_layout = QGridLayout(self.output_group)
        self.output_directory = QLineEdit()
        self.output_directory.setPlaceholderText(
            "Temporary output (or choose a folder)"
        )
        self.output_browse = QPushButton("Browse…")
        self.keep_intermediate = QCheckBox("Save every intermediate raster")
        self.keep_intermediate.setEnabled(False)
        output_layout.addWidget(self.output_directory, 0, 0)
        output_layout.addWidget(self.output_browse, 0, 1)
        output_layout.addWidget(self.keep_intermediate, 1, 0, 1, 2)
        layout.addWidget(self.output_group)

        self.file_grid = QGridLayout()
        self.import_button = QPushButton("Import…")
        self.knowledge_button = QPushButton("Knowledge…")
        self.knowledge_button.setToolTip(
            "Open formulas, limitations and trusted open-source repositories"
        )
        self.import_menu = QMenu(self.import_button)
        self.import_grid_action = self.import_menu.addAction("Survey grid file…", self.import_grid)
        self.import_gdb_action = self.import_menu.addAction("Esri FileGDB folder…", self.import_filegdb)
        self.import_geosoft_action = self.import_menu.addAction(
            "GeoDatabase (Oasis montaj) inventory/export…", self.import_geosoft_gdb
        )
        self.example_menu = self.import_menu.addMenu("Bundled sample datasets")
        self.sample_mag_action = self.example_menu.addAction(
            "Synthetic magnetic anomaly (nT)",
            lambda: self.load_sample_raster("synthetic_magnetic_anomaly.tif"),
        )
        self.sample_grav_action = self.example_menu.addAction(
            "Synthetic gravity anomaly (mGal)",
            lambda: self.load_sample_raster("synthetic_gravity_anomaly.tif"),
        )
        self.sample_dem_action = self.example_menu.addAction(
            "Synthetic DEM (m)",
            lambda: self.load_sample_raster("synthetic_dem.tif"),
        )
        self.sample_k_action = self.example_menu.addAction(
            "Synthetic potassium (% K)",
            lambda: self.load_sample_raster("synthetic_potassium.tif"),
        )
        self.sample_u_action = self.example_menu.addAction(
            "Synthetic equivalent uranium (ppm eU)",
            lambda: self.load_sample_raster("synthetic_equivalent_uranium.tif"),
        )
        self.sample_th_action = self.example_menu.addAction(
            "Synthetic equivalent thorium (ppm eTh)",
            lambda: self.load_sample_raster("synthetic_equivalent_thorium.tif"),
        )
        self.sample_points_action = self.example_menu.addAction(
            "Synthetic survey points (CSV)",
            self.load_sample_points,
        )
        self.nrcan_menu = self.example_menu.addMenu("NRCan field reference grids")
        self.nrcan_hydraulic_dem_action = self.nrcan_menu.addAction(
            "Hydraulic — DEM",
            lambda: self.load_bundled_reference_grid(
                "Hydraulic/BC_2004_G_Hydraulic_dem.GRD"
            ),
        )
        self.nrcan_hydraulic_mag_action = self.nrcan_menu.addAction(
            "Hydraulic — residual magnetics",
            lambda: self.load_bundled_reference_grid(
                "Hydraulic/BC_2004_G_Hydraulic_mag_res.GRD"
            ),
        )
        self.local_data_menu = self.import_menu.addMenu("Local test datasets")
        self.local_data_menu.aboutToShow.connect(self.refresh_local_data_menu)
        self.refresh_local_data_menu()
        self.import_button.setMenu(self.import_menu)
        self.load_button = QPushButton("Load stack…")
        self.save_button = QPushButton("Save stack…")
        self.run_button = QPushButton("Run stack")
        self.settings_button = QPushButton("Settings…")
        self.file_grid.addWidget(self.import_button, 0, 0)
        self.file_grid.addWidget(self.knowledge_button, 0, 1)
        self.file_grid.addWidget(self.settings_button, 0, 2)
        self.file_grid.addWidget(self.load_button, 1, 0)
        self.file_grid.addWidget(self.save_button, 1, 1)
        self.file_grid.addWidget(self.run_button, 1, 2)
        for column in range(3):
            self.file_grid.setColumnStretch(column, 1)
        layout.addLayout(self.file_grid)

        self.setWidget(body)
        self.algorithm_button.clicked.connect(self.show_algorithm_picker)
        self.algorithm_search.textChanged.connect(self.filter_algorithm_picker)
        self.algorithm_list.itemClicked.connect(self.choose_algorithm_item)
        self.add_button.clicked.connect(self.add_step)
        self.step_list.currentRowChanged.connect(self.show_step_parameters)
        self.duplicate_button.clicked.connect(self.duplicate_step)
        self.remove_button.clicked.connect(self.remove_step)
        self.clear_button.clicked.connect(self.clear_stack)
        self.output_browse.clicked.connect(self.choose_output_directory)
        self.output_directory.textChanged.connect(
            lambda text: self.keep_intermediate.setEnabled(bool(text.strip()))
        )
        self.load_button.clicked.connect(self.load_stack)
        self.save_button.clicked.connect(self.save_stack)
        self.preview_button.clicked.connect(self.preview_spectrum)
        self.knowledge_button.clicked.connect(self.show_knowledge_base)
        self.settings_button.clicked.connect(self.show_settings)
        self.run_button.clicked.connect(self.run_stack)

    def apply_preferences(self):
        settings = QgsSettings()
        self.band_spin.setValue(settings.value(KEY_BAND, 1, type=int))
        self.output_directory.setText(settings.value(KEY_OUTPUT, "", type=str))
        self.keep_intermediate.setChecked(
            settings.value(KEY_KEEP, False, type=bool)
        )
        tooltips = settings.value(KEY_TOOLTIPS, True, type=bool)
        self.algorithm_button.setToolTip(
            text(
                "Open the compact filter chooser to the left of TerraWorkbench",
                "Abrir el selector compacto a la izquierda de TerraWorkbench",
            )
            if tooltips
            else ""
        )
        self.knowledge_button.setToolTip(
            text(
                "Open formulas, limitations and trusted open-source repositories",
                "Abrir fórmulas, limitaciones y repositorios abiertos confiables",
            )
            if tooltips
            else ""
        )

    def preferences_changed(self):
        self.apply_preferences()
        provider = QgsApplication.processingRegistry().providerById("terraworkbench")
        if provider is not None:
            provider.refreshAlgorithms()
        self.refresh_algorithms()
        self.retranslate()
        self.languageChanged.emit()

    def retranslate(self):
        self.setWindowTitle(
            text("TerraWorkbench — Filter Stack", "TerraWorkbench — Pila de filtros")
        )
        self.source_group.setTitle(text("Input raster", "Ráster de entrada"))
        source_form = self.source_group.layout()
        source_form.labelForField(self.layer_combo).setText(text("Layer", "Capa"))
        source_form.labelForField(self.band_spin).setText(text("Band", "Banda"))
        self.algorithm_button.setText(text("Choose filter…", "Elegir filtro…"))
        self.add_button.setText(text("Add filter", "Añadir filtro"))
        self.duplicate_button.setText(text("Duplicate", "Duplicar"))
        self.remove_button.setText(text("Remove", "Eliminar"))
        self.clear_button.setText(text("Clear", "Limpiar"))
        self.step_list.setToolTip(
            text(
                "Drag filters to change their execution order.",
                "Arrastre los filtros para cambiar su orden de ejecución.",
            )
        )
        self.inspector.setWindowTitle(
            text("TerraWorkbench — Filter inspector", "TerraWorkbench — Inspector de filtros")
        )
        self.parameter_group.setTitle(
            text("Selected filter parameters", "Parámetros del filtro seleccionado")
        )
        self.empty_parameters.setText(
            text("Select a filter to edit its parameters.", "Seleccione un filtro para editar sus parámetros.")
        )
        self.spectrum_note.setText(
            text(
                "Compare the radial power spectrum of the input with the predicted FFT stack.",
                "Compare el espectro de potencia radial de la entrada con la pila FFT prevista.",
            )
        )
        self.preview_button.setText(
            text("Open spectrum preview…", "Abrir vista previa del espectro…")
        )
        self.igrf_note.setText(
            text(
                "IGRF mode 1 evaluates IGRF-14 at the raster center, survey date and altitude. Use mode 0 to enter inclination and declination manually. Positive inclination is downward; declination is clockwise from geographic North.",
                "El modo IGRF 1 evalúa IGRF-14 en el centro del ráster, fecha y altitud del levantamiento. Use el modo 0 para ingresar inclinación y declinación manualmente. La inclinación positiva apunta hacia abajo; la declinación es horaria desde el Norte geográfico.",
            )
        )
        self.inspector_tabs.setTabText(0, text("Parameters", "Parámetros"))
        self.inspector_tabs.setTabText(1, text("Spectrum", "Espectro"))
        self.inspector_tabs.setTabText(2, "IGRF")
        self.close_inspector.setText(text("Close", "Cerrar"))
        self.algorithm_picker.setWindowTitle(
            text("Choose a TerraWorkbench filter", "Elegir un filtro de TerraWorkbench")
        )
        self.domain_note.setText(
            text(
                "SPATIAL = cell-neighbour operation; FFT/HARMONICA = library FFT; FFT/MAGMAP-LIKE = detrend + reflected padding + taper + combined wavenumber operators; MIXED = components from more than one domain.",
                "ESPACIAL = operación entre celdas vecinas; FFT/HARMONICA = FFT de biblioteca; FFT/TIPO MAGMAP = tendencia + relleno reflejado + suavizado + operadores combinados de número de onda; MIXTO = componentes de más de un dominio.",
            )
        )
        self.search_label.setText(
            text("Search by method, group or abbreviation", "Buscar por método, grupo o abreviatura")
        )
        self.algorithm_search.setPlaceholderText(
            "RTP, upward, THDR, Butterworth…"
            if language() == "en"
            else "RTP, ascendente, THDR, Butterworth…"
            if language() == "es"
            else "RTP, ascendente, THDR, Butterworth…"
        )
        self.close_picker.setText(text("Close", "Cerrar"))
        self.output_group.setTitle(text("Outputs", "Salidas"))
        self.output_directory.setPlaceholderText(
            text("Temporary output (or choose a folder)", "Salida temporal (o elija una carpeta)")
        )
        self.output_browse.setText(text("Browse…", "Examinar…"))
        self.keep_intermediate.setText(
            text("Save every intermediate raster", "Guardar cada ráster intermedio")
        )
        self.import_button.setText(text("Import…", "Importar…"))
        self.knowledge_button.setText(text("Knowledge…", "Conocimiento…"))
        self.load_button.setText(text("Load stack…", "Cargar pila…"))
        self.save_button.setText(text("Save stack…", "Guardar pila…"))
        self.run_button.setText(text("Run stack", "Ejecutar pila"))
        self.settings_button.setText(text("Settings…", "Configuración…"))
        self.import_grid_action.setText(text("Survey grid file…", "Archivo de grilla de levantamiento…"))
        self.import_gdb_action.setText(text("Esri FileGDB folder…", "Carpeta Esri FileGDB…"))
        self.import_geosoft_action.setText(text("GeoDatabase (Oasis montaj) inventory/export…", "Inventario/exportación GeoDatabase (Oasis montaj)…"))
        self.example_menu.setTitle(text("Bundled sample datasets", "Datos de ejemplo incluidos"))
        self.sample_mag_action.setText(text("Synthetic magnetic anomaly (nT)", "Anomalía magnética sintética (nT)"))
        self.sample_grav_action.setText(text("Synthetic gravity anomaly (mGal)", "Anomalía gravimétrica sintética (mGal)"))
        self.sample_dem_action.setText(text("Synthetic DEM (m)", "DEM sintético (m)"))
        self.sample_k_action.setText(text("Synthetic potassium (% K)", "Potasio sintético (% K)"))
        self.sample_u_action.setText(text("Synthetic equivalent uranium (ppm eU)", "Uranio equivalente sintético (ppm eU)"))
        self.sample_th_action.setText(text("Synthetic equivalent thorium (ppm eTh)", "Torio equivalente sintético (ppm eTh)"))
        self.sample_points_action.setText(text("Synthetic survey points (CSV)", "Puntos sintéticos de levantamiento (CSV)"))
        self.nrcan_menu.setTitle(
            text("NRCan field reference grids", "Grillas reales de referencia NRCan")
        )
        self.nrcan_hydraulic_dem_action.setText("Hydraulic — DEM")
        self.nrcan_hydraulic_mag_action.setText(
            text("Hydraulic — residual magnetics", "Hydraulic — magnetometría residual")
        )
        self.local_data_menu.setTitle(text("Local test datasets", "Datos locales de prueba"))
        self.refresh_local_data_menu()
        self.knowledge_base.retranslate()
        self.filter_info.retranslate()
        self.settings_dialog.retranslate()
        for index in range(self.step_list.count()):
            item = self.step_list.item(index)
            self._set_item_step(item, self._item_step(item))

    def show_settings(self):
        self.settings_dialog.load()
        self.settings_dialog.retranslate()
        self._show_window_left(self.settings_dialog)

    def clear_stack(self):
        if self.step_list.count() == 0:
            return
        if QgsSettings().value(KEY_CONFIRM_CLEAR, True, type=bool):
            answer = QMessageBox.question(
                self,
                "TerraWorkbench",
                text(
                    "Clear every filter from the current stack?",
                    "¿Eliminar todos los filtros de la pila actual?",
                ),
            )
            if answer != qt_enum(QMessageBox, "StandardButton", "Yes"):
                return
        self.step_list.clear()

    def _connect_project(self):
        project = QgsProject.instance()
        project.layersAdded.connect(self.refresh_layers)
        project.layersRemoved.connect(self.refresh_layers)

    def disconnect_project(self):
        project = QgsProject.instance()
        for signal in (project.layersAdded, project.layersRemoved):
            try:
                signal.disconnect(self.refresh_layers)
            except (TypeError, RuntimeError):
                pass
        self.algorithm_picker.close()
        self.inspector.close()
        self.knowledge_base.close()
        self.filter_info.close()
        self.settings_dialog.close()

    def showEvent(self, event):
        self.refresh_layers()
        self.refresh_algorithms()
        super().showEvent(event)

    def refresh_layers(self, *_args):
        selected_id = self.layer_combo.currentData()
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        layers = [
            layer
            for layer in QgsProject.instance().mapLayers().values()
            if isinstance(layer, QgsRasterLayer) and layer.isValid()
        ]
        for layer in sorted(layers, key=lambda item: item.name().casefold()):
            self.layer_combo.addItem(layer.name(), layer.id())
        selected_index = self.layer_combo.findData(selected_id)
        if selected_index >= 0:
            self.layer_combo.setCurrentIndex(selected_index)
        self.layer_combo.blockSignals(False)

    def refresh_algorithms(self):
        selected_id = self.algorithm_combo.currentData()
        self.algorithm_combo.clear()
        self.algorithm_list.clear()
        self._algorithm_labels.clear()
        for algorithm in available_algorithms():
            label = (
                f"[{algorithm_domain(algorithm)}] "
                f"{algorithm.group()} — {algorithm.displayName()}"
            )
            self._algorithm_labels[algorithm.id()] = label
            self.algorithm_combo.addItem(label, algorithm.id())
            self.algorithm_combo.setItemData(
                self.algorithm_combo.count() - 1,
                label,
                qt_enum(Qt, "ItemDataRole", "ToolTipRole"),
            )
            # The item itself must remain textless because its child row renders
            # the label and information button. Painting both causes duplicated,
            # overlapping text on Windows/QGIS dark themes.
            item = QListWidgetItem()
            item.setData(
                qt_enum(Qt, "ItemDataRole", "UserRole"), algorithm.id()
            )
            item.setData(_SEARCH_TEXT_ROLE, label)
            item.setToolTip(label)
            self.algorithm_list.addItem(item)
            row = QWidget(self.algorithm_list)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(2, 1, 2, 1)
            choose_button = QPushButton(label)
            choose_button.setFlat(True)
            choose_button.setStyleSheet("text-align: left; padding: 4px;")
            choose_button.setToolTip("Select this filter")
            choose_button.clicked.connect(
                lambda _checked=False, algorithm_id=algorithm.id():
                self.choose_algorithm_id(algorithm_id)
            )
            info_button = QToolButton()
            info_button.setText("ⓘ")
            info_button.setToolTip(
                f"Read scientific and numerical information about {algorithm.displayName()}"
            )
            info_button.setFixedWidth(30)
            info_button.clicked.connect(
                lambda _checked=False, algorithm_id=algorithm.id():
                self.show_algorithm_info(algorithm_id)
            )
            row_layout.addWidget(choose_button, 1)
            row_layout.addWidget(info_button)
            item.setSizeHint(row.sizeHint())
            self.algorithm_list.setItemWidget(item, row)
        selected_index = self.algorithm_combo.findData(selected_id)
        if selected_index >= 0:
            self.algorithm_combo.setCurrentIndex(selected_index)
        elif self.algorithm_combo.count():
            self.algorithm_combo.setCurrentIndex(0)
        self._update_algorithm_button()

    def _update_algorithm_button(self):
        algorithm_id = self.algorithm_combo.currentData()
        label = self._algorithm_labels.get(algorithm_id, "Choose filter…")
        self.algorithm_button.setText(label)
        self.algorithm_button.setToolTip(label)

    def filter_algorithm_picker(self, text):
        words = text.casefold().split()
        for index in range(self.algorithm_list.count()):
            item = self.algorithm_list.item(index)
            label = str(item.data(_SEARCH_TEXT_ROLE) or "").casefold()
            item.setHidden(not all(word in label for word in words))

    def choose_algorithm_item(self, item):
        algorithm_id = item.data(qt_enum(Qt, "ItemDataRole", "UserRole"))
        self.choose_algorithm_id(algorithm_id)

    def choose_algorithm_id(self, algorithm_id):
        """Select an algorithm without confusing the adjacent information button."""
        index = self.algorithm_combo.findData(algorithm_id)
        if index >= 0:
            self.algorithm_combo.setCurrentIndex(index)
            self._update_algorithm_button()
        self.algorithm_picker.hide()

    def show_algorithm_info(self, algorithm_id):
        """Open the per-filter information panel without selecting the filter."""
        algorithm = self._algorithm(algorithm_id)
        if algorithm is None:
            return
        self.filter_info.set_algorithm(algorithm)
        self._show_window_left_of(self.filter_info, self.algorithm_picker)

    def show_algorithm_picker(self):
        self.algorithm_search.clear()
        selected_id = self.algorithm_combo.currentData()
        selected_item = None
        for index in range(self.algorithm_list.count()):
            item = self.algorithm_list.item(index)
            if item.data(qt_enum(Qt, "ItemDataRole", "UserRole")) == selected_id:
                selected_item = item
                break
        if selected_item is not None:
            self.algorithm_list.setCurrentItem(selected_item)
            self.algorithm_list.scrollToItem(selected_item)
        self._show_window_left(self.algorithm_picker, vertical_offset=95)
        self.algorithm_search.setFocus()

    def _algorithm(self, algorithm_id):
        return QgsApplication.processingRegistry().algorithmById(algorithm_id)

    def _item_step(self, item):
        return PipelineStep.from_dict(
            item.data(qt_enum(Qt, "ItemDataRole", "UserRole"))
        )

    def _set_item_step(self, item, step):
        algorithm = self._algorithm(step.algorithm_id)
        label = algorithm.displayName() if algorithm else step.algorithm_id
        if algorithm:
            domain = translate(algorithm_domain(algorithm))
            item.setText(f"[{domain}] {label}")
            item.setToolTip(f"{domain} | {algorithm.group()} — {label}")
        else:
            item.setText(label)
            item.setToolTip(label)
        item.setData(qt_enum(Qt, "ItemDataRole", "UserRole"), step.to_dict())

    def steps(self):
        return [
            self._item_step(self.step_list.item(index))
            for index in range(self.step_list.count())
        ]

    def add_step(self):
        algorithm_id = self.algorithm_combo.currentData()
        algorithm = self._algorithm(algorithm_id)
        if algorithm is None:
            QMessageBox.warning(self, "TerraWorkbench", text("No filter is selected.", "No hay ningún filtro seleccionado."))
            return
        try:
            step = PipelineStep(algorithm_id, algorithm_defaults(algorithm))
        except ValueError as error:
            QMessageBox.warning(self, "TerraWorkbench", str(error))
            return
        item = QListWidgetItem()
        self._set_item_step(item, step)
        self.step_list.addItem(item)
        self.step_list.setCurrentItem(item)
        if QgsSettings().value(KEY_INSPECTOR, True, type=bool):
            self._show_inspector_left()

    def duplicate_step(self):
        item = self.step_list.currentItem()
        if item is None:
            return
        row = self.step_list.currentRow() + 1
        copy_item = QListWidgetItem()
        step = self._item_step(item)
        self._set_item_step(
            copy_item, PipelineStep(step.algorithm_id, dict(step.parameters))
        )
        self.step_list.insertItem(row, copy_item)
        self.step_list.setCurrentItem(copy_item)

    def remove_step(self):
        row = self.step_list.currentRow()
        if row >= 0:
            self.step_list.takeItem(row)

    def _clear_parameter_form(self):
        while self.parameter_form.count():
            item = self.parameter_form.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._parameter_editors.clear()

    def show_step_parameters(self, row):
        self._clear_parameter_form()
        if row < 0:
            self.parameter_form.addRow(
                QLabel(text("Select a filter to edit its parameters.", "Seleccione un filtro para editar sus parámetros."))
            )
            return
        item = self.step_list.item(row)
        step = self._item_step(item)
        algorithm = self._algorithm(step.algorithm_id)
        if algorithm is None:
            self.parameter_form.addRow(
                QLabel(text("This filter is not currently available.", "Este filtro no está disponible actualmente."))
            )
            return

        editable = 0
        for parameter in algorithm.parameterDefinitions():
            if parameter.name() in _FIXED_PARAMETERS:
                continue
            editor = QLineEdit()
            value = step.parameters.get(parameter.name())
            editor.setText("" if value is None else str(value))
            optional = processing_parameter_is_optional(parameter)
            editor.setPlaceholderText(
                text("Optional", "Opcional") if optional else text("Required", "Obligatorio")
            )
            editor.editingFinished.connect(self.update_current_parameters)
            self._parameter_editors[parameter.name()] = (editor, parameter)
            self.parameter_form.addRow(parameter.description(), editor)
            editable += 1
        if not editable:
            self.parameter_form.addRow(
                QLabel(text("This filter has no additional parameters.", "Este filtro no tiene parámetros adicionales."))
            )
        self._show_inspector_left()

    def _show_inspector_left(self):
        self._show_window_left(self.inspector)

    def show_knowledge_base(self):
        """Show the user-facing scientific library beside the compact dock."""
        self._show_window_left(self.knowledge_base)

    def _show_window_left(self, window, vertical_offset=0):
        self._show_window_left_of(window, self, vertical_offset)

    def _show_window_left_of(self, window, anchor, vertical_offset=0):
        anchor_top_left = anchor.mapToGlobal(QPoint(0, 0))
        screen = QApplication.screenAt(anchor_top_left)
        primary = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else primary.availableGeometry()
        maximum_height = max(320, available.height() - 32)
        window.resize(window.width(), min(window.height(), maximum_height))
        x = max(available.left(), anchor_top_left.x() - window.width() - 8)
        desired_y = anchor_top_left.y() + vertical_offset
        y = min(
            max(available.top(), desired_y),
            available.bottom() - window.height() + 1,
        )
        window.move(x, y)
        window.show()
        window.raise_()

    def import_grid(self):
        source, _selected_filter = QFileDialog.getOpenFileName(
            self,
            text("Import survey grid", "Importar grilla de levantamiento"),
            "",
            text("Survey grids (*.grd *.GRD *.gxf *.GXF *.tif *.tiff *.asc *.xyz *.csv *.txt *.gdb);;All files (*)", "Grillas de levantamiento (*.grd *.GRD *.gxf *.GXF *.tif *.tiff *.asc *.xyz *.csv *.txt *.gdb);;Todos los archivos (*)"),
        )
        if not source:
            return
        if Path(source).suffix.lower() == ".gdb":
            self.import_geosoft_gdb(source)
            return
        self._finish_import(source)

    @staticmethod
    def _sample_path(filename):
        return Path(__file__).parent / "sample_data" / "synthetic" / filename

    def load_sample_raster(self, filename):
        """Load a bundled redistributable raster and select it as stack input."""
        source = self._sample_path(filename)
        layer = QgsRasterLayer(str(source), source.stem.replace("_", " ").title())
        if not layer.isValid():
            QMessageBox.critical(
                self,
                text("TerraWorkbench sample data", "Datos de ejemplo de TerraWorkbench"),
                text(f"The bundled sample raster could not be opened:\n{source}", f"No se pudo abrir el ráster de ejemplo incluido:\n{source}"),
            )
            return None
        QgsProject.instance().addMapLayer(layer)
        self.refresh_layers()
        index = self.layer_combo.findData(layer.id())
        if index >= 0:
            self.layer_combo.setCurrentIndex(index)
        return layer

    def load_sample_points(self):
        """Load bundled survey-like CSV points with their declared projected CRS."""
        source = self._sample_path("synthetic_survey_points.csv")
        uri = (
            f"file:///{source.as_posix()}?delimiter=,&xField=easting&yField=northing"
            "&crs=EPSG:32718&detectTypes=yes"
        )
        layer = QgsVectorLayer(
            uri,
            text("Synthetic Survey Points", "Puntos sintéticos de levantamiento"),
            "delimitedtext",
        )
        if not layer.isValid():
            QMessageBox.critical(
                self,
                text("TerraWorkbench sample data", "Datos de ejemplo de TerraWorkbench"),
                text(f"The bundled survey points could not be opened:\n{source}", f"No se pudieron abrir los puntos de levantamiento incluidos:\n{source}"),
            )
            return None
        QgsProject.instance().addMapLayer(layer)
        return layer

    @staticmethod
    def _nrcan_sample_path(relative_path):
        return Path(__file__).parent / "sample_data" / "nrcan" / relative_path

    def load_bundled_reference_grid(self, relative_path):
        """Convert a redistributable NRCan GRD without modifying its source."""
        source = self._nrcan_sample_path(relative_path)
        if not source.is_file():
            QMessageBox.critical(
                self,
                "TerraWorkbench",
                text(
                    f"The bundled NRCan grid could not be found:\n{source}",
                    f"No se encontró la grilla NRCan incluida:\n{source}",
                ),
            )
            return None
        self._finish_import(str(source))
        return source

    @staticmethod
    def _default_local_data_directory():
        candidate = Path(__file__).parent / "sample_data" / "local_private"
        return candidate if candidate.is_dir() else None

    def local_data_directory(self):
        """Return the configured external test-data directory, if available."""
        configured = QgsSettings().value(KEY_LOCAL_DATA, "", type=str).strip()
        if configured:
            candidate = Path(configured)
            if candidate.is_dir():
                return candidate
        return self._default_local_data_directory()

    def choose_local_data_directory(self):
        current = self.local_data_directory()
        selected = QFileDialog.getExistingDirectory(
            self,
            text(
                "Choose local test-data folder",
                "Elegir carpeta local de datos de prueba",
            ),
            str(current or ""),
        )
        if selected:
            QgsSettings().setValue(KEY_LOCAL_DATA, selected)
            self.settings_dialog.load()
            self.refresh_local_data_menu()

    def refresh_local_data_menu(self):
        """Rebuild the external-data menu without embedding machine paths."""
        self.local_data_menu.clear()
        choose_action = self.local_data_menu.addAction(
            text("Choose test-data folder…", "Elegir carpeta de datos de prueba…")
        )
        choose_action.triggered.connect(self.choose_local_data_directory)
        directory = self.local_data_directory()
        if directory is None:
            unavailable = self.local_data_menu.addAction(
                text("No local folder configured", "No hay carpeta local configurada")
            )
            unavailable.setEnabled(False)
            return

        open_action = self.local_data_menu.addAction(
            text("Open test-data folder", "Abrir carpeta de datos de prueba")
        )
        open_action.triggered.connect(
            lambda _checked=False, path=directory: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(path))
            )
        )
        self.local_data_menu.addSeparator()
        supported = {".tif", ".tiff", ".grd", ".gxf", ".asc", ".xyz", ".csv", ".txt", ".gdb"}
        candidates = [
            path
            for path in directory.rglob("*")
            if (path.is_file() and path.suffix.casefold() in supported)
            or (path.is_dir() and path.suffix.casefold() == ".gdb")
        ]
        # Do not list the internal files of an Esri FileGDB separately.
        filegdb_directories = {
            path for path in candidates if path.is_dir() and path.suffix.casefold() == ".gdb"
        }
        candidates = [
            path
            for path in candidates
            if path in filegdb_directories
            or not any(parent in filegdb_directories for parent in path.parents)
        ]
        for path in sorted(candidates, key=lambda item: str(item).casefold()):
            label = str(path.relative_to(directory))
            action = self.local_data_menu.addAction(label)
            action.setToolTip(str(path))
            action.triggered.connect(
                lambda _checked=False, source=path: self.open_local_test_data(source)
            )
        if not candidates:
            empty = self.local_data_menu.addAction(
                text("No supported datasets found", "No se encontraron datasets compatibles")
            )
            empty.setEnabled(False)

    def open_local_test_data(self, source):
        """Open a real local reference dataset while preserving its source file."""
        source = Path(source)
        if source.is_dir() and source.suffix.casefold() == ".gdb":
            self.import_filegdb(str(source))
            return
        suffix = source.suffix.casefold()
        if suffix == ".gdb":
            self.import_geosoft_gdb(str(source))
            return
        if suffix in {".tif", ".tiff"}:
            layer = QgsRasterLayer(str(source), source.stem)
            if layer.isValid():
                QgsProject.instance().addMapLayer(layer)
                self.refresh_layers()
                index = self.layer_combo.findData(layer.id())
                if index >= 0:
                    self.layer_combo.setCurrentIndex(index)
                return layer
            QMessageBox.critical(
                self,
                "TerraWorkbench",
                text(
                    f"The raster could not be opened:\n{source}",
                    f"No se pudo abrir el ráster:\n{source}",
                ),
            )
            return None
        self._finish_import(str(source))
        return None

    def _geosoft_runtime(self):
        activate_dependency_path()
        if importlib.util.find_spec("geosoft") is not None:
            return GeosoftRuntime(
                dependency_directory(),
                None,
                Path(python_command()),
                standalone=True,
            )
        settings = QgsSettings()
        runtime = find_geosoft_runtime(
            settings.value("TerraWorkbench/geosoftLocation", "")
        )
        if runtime:
            settings.setValue("TerraWorkbench/geosoftLocation", str(runtime.root))
            return runtime
        selected = QFileDialog.getExistingDirectory(
            self,
            text("Locate the Geosoft or Oasis montaj installation folder", "Ubicar la carpeta de instalación de Geosoft u Oasis montaj"),
            "",
        )
        if not selected:
            return None
        runtime = validate_geosoft_location(selected)
        if runtime is None:
            QMessageBox.critical(
                self,
                "TerraWorkbench",
                text(
                    "That folder does not contain both bin\\omscore.exe and the bundled python\\python.exe. Choose the Geosoft Desktop Applications folder.",
                    "Esa carpeta no contiene bin\\omscore.exe y python\\python.exe. Elija la carpeta de Geosoft Desktop Applications.",
                ),
            )
            return None
        settings.setValue("TerraWorkbench/geosoftLocation", str(runtime.root))
        return runtime

    def import_geosoft_gdb(self, source=None):
        if not source:
            source, _selected_filter = QFileDialog.getOpenFileName(
                self,
                text("Choose GeoDatabase (Oasis montaj)", "Elegir GeoDatabase (Oasis montaj)"),
                "",
                "GeoDatabase (Oasis montaj) (*.gdb)",
            )
        if not source:
            return
        runtime = self._geosoft_runtime()
        if runtime is None:
            return
        choice_dialog = QMessageBox(self)
        choice_dialog.setWindowTitle(text("GeoDatabase (Oasis montaj) export", "Exportación GeoDatabase (Oasis montaj)"))
        choice_dialog.setText(
            text("Choose what to recover from the Oasis montaj GeoDatabase.", "Elija qué recuperar de la GeoDatabase de Oasis montaj.")
        )
        choice_dialog.setInformativeText(
            text(
                "Full extraction writes every numeric channel to open CSV, loads the points and inventories into QGIS, and may require substantially more disk space than the compressed GDB.",
                "La extracción completa escribe cada canal numérico en CSV abierto, carga los puntos e inventarios en QGIS y puede requerir bastante más espacio que la GDB comprimida.",
            )
        )
        inventory_button = choice_dialog.addButton(
            text("Inventory only", "Solo inventario"), qt_enum(QMessageBox, "ButtonRole", "ActionRole")
        )
        extract_button = choice_dialog.addButton(
            text("Extract all and load into QGIS", "Extraer todo y cargar en QGIS"),
            qt_enum(QMessageBox, "ButtonRole", "AcceptRole"),
        )
        cancel_button = choice_dialog.addButton(
            qt_enum(QMessageBox, "StandardButton", "Cancel")
        )
        execute = getattr(choice_dialog, "exec", None) or choice_dialog.exec_
        execute()
        if choice_dialog.clickedButton() == cancel_button:
            return
        extract_all = choice_dialog.clickedButton() == extract_button
        if choice_dialog.clickedButton() not in (inventory_button, extract_button):
            return
        output = QFileDialog.getExistingDirectory(self, text("Choose GDB export folder", "Elegir carpeta de exportación GDB"))
        if not output:
            return
        bridge = Path(__file__).with_name("geosoft_bridge.py")
        arguments = [str(bridge), "--input", str(source), "--output", str(output)]
        if extract_all:
            arguments.append("--extract-all")
        process = QProcess(self)
        process_environment = QProcessEnvironment.systemEnvironment()
        if runtime.standalone:
            process_environment.insert(
                "TERRAWORKBENCH_GEOSOFT_SITE", str(runtime.root)
            )
            process_environment.insert(
                "TERRAWORKBENCH_GEOSOFT_ENGINE",
                "Geosoft GX Developer public runtime (BSD-2-Clause)",
            )
        else:
            process_environment.insert(
                "TERRAWORKBENCH_GEOSOFT_ENGINE",
                "Geosoft gxpy runtime from installed Oasis montaj",
            )
        process.setProcessEnvironment(process_environment)
        starting_message = (
            text(
                "Starting the public Geosoft GX Developer reader…",
                "Iniciando el lector público Geosoft GX Developer…",
            )
            if runtime.standalone
            else text(
                "Starting the installed Oasis montaj runtime…",
                "Iniciando el runtime instalado de Oasis montaj…",
            )
        )
        progress = QProgressDialog(
            starting_message, text("Cancel", "Cancelar"), 0, 0, self
        )
        progress.setWindowTitle("TerraWorkbench — GeoDatabase (Oasis montaj)")
        progress.setWindowModality(qt_enum(Qt, "WindowModality", "WindowModal"))
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        self._geosoft_process = process
        self._geosoft_progress = progress
        cancelled = {"value": False}

        def update_progress():
            output_text = (
                bytes(process.readAllStandardOutput()).decode(errors="replace").strip()
            )
            if output_text:
                progress.setLabelText(output_text.splitlines()[-1])

        def finished(exit_code, _exit_status):
            update_progress()
            error_text = (
                bytes(process.readAllStandardError()).decode(errors="replace").strip()
            )
            progress.close()
            process.deleteLater()
            self._geosoft_process = None
            self._geosoft_progress = None
            if cancelled["value"]:
                return
            if exit_code == 0:
                loaded = self._load_geosoft_outputs(source, output)
                QMessageBox.information(
                    self,
                    "TerraWorkbench",
                    text(
                        f"GeoDatabase (Oasis montaj) {'export' if extract_all else 'inventory'} completed.\nAdded {loaded} open-data layer(s)/table(s) to QGIS.\n{output}\n\nThese exported files no longer require Oasis montaj.",
                        f"Se completó {'la exportación' if extract_all else 'el inventario'} de GeoDatabase (Oasis montaj).\nSe añadieron {loaded} capa(s)/tabla(s) de datos abiertos a QGIS.\n{output}\n\nEstos archivos exportados ya no requieren Oasis montaj.",
                    ),
                )
                if extract_all and self._last_geosoft_point_layer is not None:
                    self._offer_survey_gridding(self._last_geosoft_point_layer)
            else:
                failure_text = (
                    text(
                        "The public Geosoft GX Developer reader failed.",
                        "Falló el lector público Geosoft GX Developer.",
                    )
                    if runtime.standalone
                    else text(
                        "The installed Oasis montaj runtime failed. Confirm that it is licensed for this user.",
                        "Falló el runtime instalado de Oasis montaj. Confirme que tenga licencia para este usuario.",
                    )
                )
                diagnostic = error_text or text(
                    "No diagnostic was returned.", "No se devolvió diagnóstico."
                )
                QMessageBox.critical(
                    self,
                    "TerraWorkbench",
                    f"{failure_text}\n\n{diagnostic}",
                )

        def cancel_process():
            cancelled["value"] = True
            process.kill()

        process.readyReadStandardOutput.connect(update_progress)
        process.finished.connect(finished)
        progress.canceled.connect(cancel_process)
        progress.show()
        process.start(str(runtime.python), arguments)

    def _load_geosoft_outputs(self, source, output):
        self._last_geosoft_point_layer = None
        manifest_path = Path(output) / f"{Path(source).stem}_inventory.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return 0
        loaded = 0
        for key, suffix in (("channels_csv", "channels"), ("lines_csv", "lines")):
            path = manifest.get(key)
            if not path or not Path(path).is_file():
                continue
            url = QUrl.fromLocalFile(path)
            query = QUrlQuery()
            query.addQueryItem("type", "csv")
            query.addQueryItem("detectTypes", "yes")
            query.addQueryItem("geomType", "none")
            url.setQuery(query)
            layer = QgsVectorLayer(
                url.toString(),
                f"{Path(source).stem} — {suffix} — GeoDatabase (Oasis montaj)",
                "delimitedtext",
            )
            if layer.isValid():
                self._mark_oasis_source(layer, source, manifest)
                QgsProject.instance().addMapLayer(layer)
                loaded += 1
        csv_path = manifest.get("csv")
        x_field, y_field = manifest.get("x_field"), manifest.get("y_field")
        if csv_path and x_field and y_field and Path(csv_path).is_file():
            url = QUrl.fromLocalFile(csv_path)
            query = QUrlQuery()
            for key, value in (
                ("type", "csv"),
                ("detectTypes", "yes"),
                ("xField", x_field),
                ("yField", y_field),
                ("geomType", "point"),
                ("subsetIndex", "no"),
                ("watchFile", "no"),
            ):
                query.addQueryItem(key, value)
            url.setQuery(query)
            layer = QgsVectorLayer(
                url.toString(),
                f"{Path(source).stem} — all channels — GeoDatabase (Oasis montaj)",
                "delimitedtext",
            )
            wkt = manifest.get("coordinate_system", {}).get("wkt", "")
            if wkt:
                layer.setCrs(QgsCoordinateReferenceSystem.fromWkt(wkt))
            if layer.isValid():
                self._mark_oasis_source(layer, source, manifest)
                QgsProject.instance().addMapLayer(layer)
                self._last_geosoft_point_layer = layer
                loaded += 1
        return loaded

    def _offer_survey_gridding(self, point_layer):
        answer = QMessageBox.question(
            self,
            text("Create analysis grid", "Crear grilla de análisis"),
            text("The GeoDatabase points are now independent from Oasis montaj. Open the gridding tool to select a channel and create a GeoTIFF for RTP/RTE and the Filter Stack?", "Los puntos de GeoDatabase ya son independientes de Oasis montaj. ¿Abrir la herramienta de interpolación para elegir un canal y crear un GeoTIFF para RTP/RTE y la pila de filtros?"),
            qt_enum(QMessageBox, "StandardButton", "Yes")
            | qt_enum(QMessageBox, "StandardButton", "No"),
            qt_enum(QMessageBox, "StandardButton", "Yes"),
        )
        if answer != qt_enum(QMessageBox, "StandardButton", "Yes"):
            return
        fields = {name.casefold(): name for name in point_layer.fields().names()}
        preferred = ("magcom", "magdiur", "magraw", "maguncom", "srvmglev", "f_nadr")
        value_field = next((fields[name] for name in preferred if name in fields), "")
        import processing

        processing.execAlgorithmDialog(
            "terraworkbench:grid_survey_points",
            {
                "INPUT": point_layer,
                "VALUE_FIELD": value_field,
                "CELL_SIZE": 0.0,
                "METHOD": 0,
                "POWER": 2.0,
                "NEIGHBORS": 12,
                "SEARCH_RADIUS": 0.0,
            },
        )

    @staticmethod
    def _mark_oasis_source(layer, source, manifest):
        layer.setCustomProperty(
            "TerraWorkbench/sourceFormat",
            manifest.get("source_format", "GeoDatabase (Oasis montaj)"),
        )
        layer.setCustomProperty("TerraWorkbench/sourceFile", str(source))
        layer.setCustomProperty(
            "TerraWorkbench/conversionEngine",
            manifest.get("conversion_engine", "Geosoft runtime"),
        )
        metadata = layer.metadata()
        metadata.setTitle(layer.name())
        metadata.setAbstract(
            "Imported from GeoDatabase (Oasis montaj) and converted to open CSV by "
            "TerraWorkbench. The exported layer is usable without Oasis montaj."
        )
        metadata.addHistoryItem(
            f"Source: GeoDatabase (Oasis montaj): {Path(source).name}"
        )
        layer.setMetadata(metadata)

    def import_filegdb(self, source=None):
        if not source:
            source = QFileDialog.getExistingDirectory(self, text("Choose Esri FileGDB folder", "Elegir carpeta Esri FileGDB"))
        if not source:
            return
        if Path(source).suffix.lower() != ".gdb":
            QMessageBox.warning(
                self, "TerraWorkbench", text("Choose a folder ending in .gdb.", "Elija una carpeta que termine en .gdb.")
            )
            return
        subdatasets = list_raster_subdatasets(source)
        vector_layers = list_vector_layers(source)
        choices = []
        targets = {}
        if vector_layers:
            all_label = text(
                "[Vector] Load every feature class and table",
                "[Vector] Cargar todas las clases de entidad y tablas",
            )
            choices.append(all_label)
            targets[all_label] = ("all_vectors", None)
            for name in vector_layers:
                label = f"{text('[Vector]', '[Vector]')} {name}"
                choices.append(label)
                targets[label] = ("vector", name)
        for name, description in subdatasets:
            label = f"[Raster] {description or name}"
            choices.append(label)
            targets[label] = ("raster", name)
        if not choices:
            QMessageBox.warning(
                self,
                "TerraWorkbench",
                text(
                    "No readable raster, feature class or table was found in this FileGDB.",
                    "No se encontró ningún ráster, clase de entidad o tabla legible en esta FileGDB.",
                ),
            )
            return
        selected, accepted = QInputDialog.getItem(
            self,
            text("Open Esri FileGDB content", "Abrir contenido de Esri FileGDB"),
            text("Dataset", "Dataset"),
            choices,
            0,
            False,
        )
        if not accepted:
            return
        kind, value = targets[selected]
        if kind == "raster":
            self._finish_import(source, value)
            return
        names = vector_layers if kind == "all_vectors" else [value]
        loaded = 0
        for name in names:
            layer = QgsVectorLayer(f"{source}|layername={name}", name, "ogr")
            if layer.isValid():
                QgsProject.instance().addMapLayer(layer)
                loaded += 1
        if loaded != len(names):
            message = text(
                "Loaded {loaded} of {total} FileGDB vector/table layers.",
                "Se cargaron {loaded} de {total} capas vectoriales/tablas de FileGDB.",
            ).format(loaded=loaded, total=len(names))
            QMessageBox.warning(
                self,
                "TerraWorkbench",
                message,
            )

    def _finish_import(self, source, subdataset=None):
        suggested = str(Path(source).with_suffix(".tif"))
        output, _selected_filter = QFileDialog.getSaveFileName(
            self, text("Save imported GeoTIFF", "Guardar GeoTIFF importado"), suggested, "GeoTIFF (*.tif *.tiff)"
        )
        if not output:
            return
        QApplication.setOverrideCursor(qt_enum(Qt, "CursorShape", "WaitCursor"))
        try:
            imported, metadata = import_survey_grid(
                source, output, subdataset=subdataset
            )
            layer = QgsRasterLayer(imported, Path(imported).stem)
            if not layer.isValid():
                raise QgsProcessingException(
                    "The imported GeoTIFF is not a valid QGIS raster."
                )
            QgsProject.instance().addMapLayer(layer)
            details = "\n".join(
                f"{key}: {value}"
                for key, value in metadata.items()
                if key
                in {
                    "TITLE",
                    "EPSG",
                    "SURVEY_START",
                    "SURVEY_END",
                    "LINE_DIRECTION",
                    "LINE_SPACING",
                }
            )
            QMessageBox.information(
                self,
                "TerraWorkbench",
                text("Grid imported and added to the map.", "La grilla se importó y añadió al mapa.")
                + (f"\n\n{details}" if details else ""),
            )
        except (OSError, ValueError, QgsProcessingException) as error:
            QMessageBox.critical(self, "TerraWorkbench", text(f"Import failed:\n{error}", f"Falló la importación:\n{error}"))
        finally:
            QApplication.restoreOverrideCursor()

    def update_current_parameters(self):
        item = self.step_list.currentItem()
        if item is None:
            return True
        step = self._item_step(item)
        valid = True
        for name, (editor, parameter) in self._parameter_editors.items():
            text = editor.text().strip()
            try:
                if not text and processing_parameter_is_optional(parameter):
                    value = None
                elif parameter.dataType() == PROCESSING_NUMBER_INTEGER:
                    value = int(text) if text else parameter.defaultValue()
                else:
                    value = float(text) if text else parameter.defaultValue()
                if value is not None and not parameter.checkValueIsAcceptable(value):
                    raise ValueError
                step.parameters[name] = value
                editor.setStyleSheet("")
            except (TypeError, ValueError):
                valid = False
                editor.setStyleSheet("border: 1px solid #d32f2f;")
        self._set_item_step(item, step)
        return valid

    def choose_output_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self, text("Choose output folder", "Elegir carpeta de salida"), self.output_directory.text()
        )
        if directory:
            self.output_directory.setText(directory)

    def save_stack(self):
        if not self.update_current_parameters():
            QMessageBox.warning(
                self, "TerraWorkbench", text("Correct the highlighted parameter values.", "Corrija los valores de parámetros resaltados.")
            )
            return
        if not self.steps():
            QMessageBox.warning(self, "TerraWorkbench", text("The filter stack is empty.", "La pila de filtros está vacía."))
            return
        path, _selected_filter = QFileDialog.getSaveFileName(
            self, text("Save filter stack", "Guardar pila de filtros"), "terraworkbench-stack.json", "JSON (*.json)"
        )
        if not path:
            return
        payload = {
            "format": PIPELINE_FORMAT_VERSION,
            "steps": [step.to_dict() for step in self.steps()],
        }
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_stack(self):
        path, _selected_filter = QFileDialog.getOpenFileName(
            self, text("Load filter stack", "Cargar pila de filtros"), "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            if payload.get("format") != PIPELINE_FORMAT_VERSION:
                raise ValueError("Unsupported filter-stack format")
            steps = [
                PipelineStep.from_dict(value) for value in payload.get("steps", [])
            ]
            if not steps:
                raise ValueError("The saved filter stack is empty")
            missing = [
                step.algorithm_id
                for step in steps
                if self._algorithm(step.algorithm_id) is None
            ]
            if missing:
                raise ValueError(f"Unavailable filters: {', '.join(missing)}")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            QMessageBox.critical(
                self, "TerraWorkbench", text(f"Could not load stack:\n{error}", f"No se pudo cargar la pila:\n{error}")
            )
            return

        self.step_list.clear()
        for step in steps:
            item = QListWidgetItem()
            self._set_item_step(item, step)
            self.step_list.addItem(item)
        self.step_list.setCurrentRow(0)

    def _selected_raster(self):
        layer_id = self.layer_combo.currentData()
        layer = QgsProject.instance().mapLayer(layer_id) if layer_id else None
        return layer if isinstance(layer, QgsRasterLayer) and layer.isValid() else None

    def preview_spectrum(self):
        if not self.update_current_parameters():
            QMessageBox.warning(
                self, "TerraWorkbench", text("Correct the highlighted parameter values.", "Corrija los valores de parámetros resaltados.")
            )
            return
        layer = self._selected_raster()
        if layer is None:
            QMessageBox.warning(
                self, "TerraWorkbench", text("Choose a valid input raster layer.", "Elija una capa ráster de entrada válida.")
            )
            return

        QApplication.setOverrideCursor(qt_enum(Qt, "CursorShape", "WaitCursor"))
        try:
            grid = read_raster(layer, self.band_spin.value())
            orientation = to_regular_data_array(grid)
            data = orientation.data
            northing = np.asarray(data.coords["northing"])
            easting = np.asarray(data.coords["easting"])
            spacing_northing = abs(float(northing[1] - northing[0]))
            spacing_easting = abs(float(easting[1] - easting[0]))
            frequencies, original_power = radial_power_spectrum(
                data.values, spacing_northing, spacing_easting
            )

            from .algorithms.spectral_filters import SpectralFilterBase

            context = QgsProcessingContext()
            context.setProject(QgsProject.instance())
            preprocessing = None
            prepared = None
            fft_state = None
            combined = None
            spectral_steps = True
            preview_feedback = QgsProcessingFeedback()
            for step in self.steps():
                algorithm = self._algorithm(step.algorithm_id)
                if not isinstance(algorithm, SpectralFilterBase):
                    spectral_steps = False
                    break
                current_preprocessing = algorithm.preprocessing_values(
                    step.parameters, context
                )
                if preprocessing is None:
                    preprocessing = current_preprocessing
                    detrend, padding, taper, _restore = preprocessing
                    prepared, fft_state = prepare_fft_grid(
                        data.values, detrend, padding, taper
                    )
                    k_east, k_north, radial = frequency_grid(
                        prepared.shape, spacing_northing, spacing_easting
                    )
                    combined = np.ones(prepared.shape, dtype=np.complex128)
                elif current_preprocessing[:3] != preprocessing[:3]:
                    spectral_steps = False
                    break
                algorithm.prepare(grid, step.parameters, context, preview_feedback)
                combined *= algorithm.transfer(
                    k_east, k_north, radial, step.parameters, context
                )

            if spectral_steps and self.steps():
                restore_trend = preprocessing[3]
                predicted = finish_fft_grid(
                    apply_transfer(prepared, combined), fft_state, restore_trend
                )
                _frequencies, filtered_power = radial_power_spectrum(
                    predicted, spacing_northing, spacing_easting
                )
                note = text(
                    "Black: input radial power spectrum. Red: predicted result from the combined FFT spectral filters in this stack.",
                    "Negro: espectro de potencia radial de entrada. Rojo: resultado previsto por los filtros espectrales FFT combinados de esta pila.",
                )
            else:
                filtered_power = None
                note = text(
                    "Input radial power spectrum. A predicted output is shown only when every stack step belongs to the FFT spectral filters group.",
                    "Espectro de potencia radial de entrada. Solo se muestra una salida prevista cuando cada paso pertenece al grupo de filtros espectrales FFT.",
                )
        except (OSError, ValueError, QgsProcessingException) as error:
            QMessageBox.critical(
                self, "TerraWorkbench", text(f"Spectrum preview failed:\n{error}", f"Falló la vista previa del espectro:\n{error}")
            )
            return
        finally:
            QApplication.restoreOverrideCursor()

        dialog = SpectrumDialog(frequencies, original_power, filtered_power, note, self)
        execute = getattr(dialog, "exec", None) or dialog.exec_
        execute()

    def run_stack(self):
        if not self.update_current_parameters():
            QMessageBox.warning(
                self, "TerraWorkbench", text("Correct the highlighted parameter values.", "Corrija los valores de parámetros resaltados.")
            )
            return
        layer = self._selected_raster()
        if layer is None:
            QMessageBox.warning(
                self, "TerraWorkbench", text("Choose a valid input raster layer.", "Elija una capa ráster de entrada válida.")
            )
            return
        steps = self.steps()
        if not steps:
            QMessageBox.warning(self, "TerraWorkbench", text("Add at least one filter.", "Añada al menos un filtro."))
            return

        output_directory = self.output_directory.text().strip() or None
        progress = QProgressDialog(text("Running filter stack…", "Ejecutando pila de filtros…"), text("Cancel", "Cancelar"), 0, 100, self)
        progress.setWindowModality(qt_enum(Qt, "WindowModality", "WindowModal"))
        progress.setMinimumDuration(0)
        feedback = QgsProcessingFeedback()
        feedback.progressChanged.connect(lambda value: progress.setValue(int(value)))
        progress.canceled.connect(feedback.cancel)
        progress.show()
        QApplication.setOverrideCursor(qt_enum(Qt, "CursorShape", "WaitCursor"))
        try:
            final_output, outputs = run_filter_stack(
                layer,
                self.band_spin.value(),
                steps,
                feedback=feedback,
                output_directory=output_directory,
                keep_intermediate=self.keep_intermediate.isChecked(),
            )
            if feedback.isCanceled():
                return
            result_layer = QgsRasterLayer(
                str(final_output),
                f"TerraWorkbench — {steps[-1].algorithm_id.split(':', 1)[1]}",
            )
            if not result_layer.isValid():
                raise QgsProcessingException(
                    f"The final output is invalid: {final_output}"
                )
            if QgsSettings().value(KEY_ADD_RESULT, True, type=bool):
                QgsProject.instance().addMapLayer(result_layer)
            QMessageBox.information(
                self,
                "TerraWorkbench",
                text(
                    f"Completed {len(outputs)} filter(s). The final result was added to the map."
                    if QgsSettings().value(KEY_ADD_RESULT, True, type=bool)
                    else f"Completed {len(outputs)} filter(s). The final result was written to disk.",
                    f"Se completaron {len(outputs)} filtro(s). El resultado final se añadió al mapa."
                    if QgsSettings().value(KEY_ADD_RESULT, True, type=bool)
                    else f"Se completaron {len(outputs)} filtro(s). El resultado final se escribió en disco.",
                ),
            )
        except (OSError, ValueError, QgsProcessingException) as error:
            QMessageBox.critical(
                self, "TerraWorkbench", text(f"Filter stack failed:\n{error}", f"Falló la pila de filtros:\n{error}")
            )
        finally:
            QApplication.restoreOverrideCursor()
            progress.close()
