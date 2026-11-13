"""Dockable filter-stack workflow for TerraWorkbench."""

from __future__ import annotations

from dataclasses import dataclass, field
import html
import json
import hashlib
import inspect
import uuid
from datetime import datetime, timezone
from pathlib import Path
import re

import numpy as np

from qgis.PyQt.QtCore import (
    QPoint,
    QPointF,
    QProcess,
    QProcessEnvironment,
    QRectF,
    QSize,
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
    QFrame,
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
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    QgsApplication,
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

from ._paths import PLUGIN_ROOT
from .hillshade import HillshadeActions
from ..qgis_plugin.qgis_compat import (
    PROCESSING_NUMBER_INTEGER,
    processing_parameter_is_optional,
    qt_enum,
)
from ..qgis_plugin.raster_io import (
    read_raster,
    restore_raster_order,
    to_regular_data_array,
    write_geotiff,
)
from .knowledge_content import CHAPTERS, LANGUAGES, chapter_text
from ..compat.spectral import (
    apply_spectrum,
    apply_transfer,
    finish_fft_grid,
    frequency_grid,
    prepare_fft_grid,
    radial_power_spectrum,
)
from ..qgis_plugin.data_import import (
    copy_imported_raster,
    import_layer_path,
    import_working_directory,
    is_temporary_import,
    mark_temporary_import,
    new_import_directory,
    project_work_directory,
    recent_work_directories,
    remember_work_directory,
    save_temporary_imports,
    temporary_import_root,
    write_project_work_directory,
    import_survey_grid,
    list_raster_subdatasets,
    list_vector_layers,
)
from ..qgis_plugin.hillshade import EFFECT
from ..embedded_qpip import dependency_directory
from ..embedded_qpip.manager import python_command
from ..qgis_plugin.geosoft_runtime import (
    GeosoftRuntime,
    find_geosoft_runtime,
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
BRAND_ICON_PATH = PLUGIN_ROOT / "assets" / "branding" / "terraworkbench-icon.png"

_KNOWLEDGE_REPOSITORIES = (
    (
        "Campos potenciales y filtros",
        (
            (
                "Harmonica",
                "https://github.com/fatiando/harmonica",
                "Procesamiento, modelado, fuentes equivalentes, Euler y lectura GRD.",
            ),
            (
                "Verde",
                "https://github.com/fatiando/verde",
                "Gridding, tendencias y validación espacial.",
            ),
            (
                "Boule",
                "https://github.com/fatiando/boule",
                "Elipsoides y gravedad normal.",
            ),
            (
                "Choclo",
                "https://github.com/fatiando/choclo",
                "Kernels rápidos de gravedad y magnetismo.",
            ),
            (
                "GMT",
                "https://github.com/GenericMappingTools/gmt",
                "Procesamiento maduro de grillas y filtros FFT.",
            ),
            (
                "xrft",
                "https://github.com/xgcm/xrft",
                "FFT con dimensiones y coordenadas xarray.",
            ),
        ),
    ),
    (
        "Suites geofísicas y QGIS",
        (
            (
                "PyGMI",
                "https://github.com/Patrick-Cole/pygmi",
                "Suite abierta de magnetismo, gravedad, raster y modelado.",
            ),
            (
                "SGTool",
                "https://github.com/swaxi/SGTool",
                "Plugin QGIS/ArcGIS para cálculos de campos potenciales.",
            ),
            (
                "QGIS",
                "https://github.com/qgis/QGIS",
                "Código del host, Processing, tareas y raster providers.",
            ),
        ),
    ),
    (
        "Inversión y modelos 3D",
        (
            (
                "SimPEG",
                "https://github.com/simpeg/simpeg",
                "GRAV, MAG, MVI, regularización e inversión conjunta.",
            ),
            (
                "discretize",
                "https://github.com/simpeg/discretize",
                "TensorMesh, TreeMesh y operadores.",
            ),
            (
                "geoana",
                "https://github.com/simpeg/geoana",
                "Soluciones analíticas para pruebas sintéticas.",
            ),
            (
                "pyGIMLi",
                "https://github.com/gimli-org/pyGIMLi",
                "Modelado e inversión restringida y conjunta.",
            ),
            (
                "Euler inversion",
                "https://github.com/compgeolab/euler-inversion",
                "Investigación reproducible de localización de fuentes.",
            ),
            (
                "GemPy",
                "https://github.com/gempy-project/gempy",
                "Modelado geológico implícito y estocástico.",
            ),
            (
                "LoopStructural",
                "https://github.com/Loop3D/LoopStructural",
                "Modelado estructural implícito.",
            ),
        ),
    ),
    (
        "Campo principal y formatos",
        (
            (
                "ppigrf",
                "https://github.com/IAGA-VMOD/ppigrf",
                "IGRF-14 puro en Python.",
            ),
            (
                "GDAL",
                "https://github.com/OSGeo/gdal",
                "Formatos raster/vector y metadatos.",
            ),
            (
                "Rasterio",
                "https://github.com/rasterio/rasterio",
                "Lectura, escritura y validación raster sobre GDAL.",
            ),
            (
                "awesome-open-geoscience",
                "https://github.com/softwareunderground/awesome-open-geoscience",
                "Catálogo comunitario para descubrir proyectos abiertos.",
            ),
        ),
    ),
    (
        "Radiometría gamma",
        (
            (
                "IAEA radioelement guidelines",
                "https://www-pub.iaea.org/MTCD/publications/PDF/te_1363_web/PDF/Contents.pdf",
                "Normas de adquisición, calibración, procesamiento, incertidumbre y cartografía radiométrica.",
            ),
            (
                "Geoscience Australia Radiometrics",
                "https://www.ga.gov.au/scientific-topics/disciplines/geophysics/radiometrics",
                "Productos oficiales K, eU, eTh, dosis y composiciones ternarias.",
            ),
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

    from ..algorithms.spectral_filters import SpectralFilterBase

    spectral_algorithms = [
        QgsApplication.processingRegistry().algorithmById(step.algorithm_id)
        for step in steps
    ]
    if all(
        isinstance(algorithm, SpectralFilterBase) for algorithm in spectral_algorithms
    ):
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
    orientation = to_regular_data_array(grid, fill_missing=True)
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
        response = algorithm.transfer(k_east, k_north, radial, step.parameters, context)
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
        persist = output_path is not None and (keep_intermediate or index == last_index)
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
            output_nodata=float("nan"),
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
        painter.drawText(
            int(plot.center().x()) - 45,
            self.height() - 16,
            text("wavenumber", "número de onda"),
        )
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
        self.setWindowFlags(self.windowFlags() | qt_enum(Qt, "WindowType", "Tool"))
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
        handbook = QWidget()
        handbook_layout = QVBoxLayout(handbook)
        self.chapter_search = QLineEdit()
        self.chapter_picker = QComboBox()
        self.handbook_browser = QTextBrowser()
        self.handbook_browser.setOpenExternalLinks(True)
        handbook_layout.addWidget(self.chapter_search)
        handbook_layout.addWidget(self.chapter_picker)
        handbook_layout.addWidget(self.handbook_browser, 1)
        self.tabs.addTab(handbook, "")
        self.chapter_search.textChanged.connect(self.filter_chapters)
        self.chapter_picker.currentIndexChanged.connect(self.show_chapter)
        from .full_manual import FullManualWidget

        self.full_manual = FullManualWidget()
        self.tabs.addTab(self.full_manual, "")
        layout.addWidget(self.tabs, 1)

        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.close_button = QPushButton()
        self.close_button.clicked.connect(self.hide)
        layout.addWidget(self.close_button)
        self.retranslate()
        self.tabs.setCurrentIndex(2)

    def retranslate(self):
        self.setWindowTitle(
            text(
                "TerraWorkbench — Knowledge Base",
                "TerraWorkbench — Base de conocimiento",
            )
        )
        self.intro.setText(
            text(
                "Geophysical scientific library. Links open trusted official documentation, repositories and tests.",
                "Biblioteca científica geofísica. Los enlaces abren documentación oficial confiable, repositorios y pruebas.",
            )
        )
        self.repository_browser.setHtml(self._repository_html())
        self.tabs.setTabText(0, text("Trusted repositories", "Repositorios confiables"))
        self.tabs.setTabText(
            1, text("MAG / GRAV / RAD reference", "Referencia MAG / GRAV / RAD")
        )
        self.tabs.setTabText(2, text("Practical handbook", "Manual práctico"))
        self.tabs.setTabText(
            3,
            {"en": "Complete manual", "es": "Manual completo", "pt": "Manual completo"}[
                language()
            ],
        )
        self.full_manual.retranslate(language())
        self.chapter_search.setPlaceholderText(
            text("Search handbook…", "Buscar en el manual…")
        )
        self.filter_chapters()
        reference_name = {
            "en": "potential_fields_reference_en.md",
            "es": "geofisica_potencial_referencia.md",
            "pt": "potential_fields_reference_pt.md",
        }[language()]
        reference_path = PLUGIN_ROOT / "docs" / "handbook" / reference_name
        if reference_path.is_file():
            self.reference_browser.setMarkdown(
                reference_path.read_text(encoding="utf-8")
            )
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

    def filter_chapters(self, *_args):
        selected = self.chapter_picker.currentData()
        locale = language()
        query = self.chapter_search.text().casefold().strip()
        index = LANGUAGES.index(locale)
        self.chapter_picker.blockSignals(True)
        self.chapter_picker.clear()
        for chapter in CHAPTERS:
            if not query or query in chapter_text(chapter[0], locale).casefold():
                self.chapter_picker.addItem(chapter[1][index], chapter[0])
        row = self.chapter_picker.findData(selected)
        if row >= 0:
            self.chapter_picker.setCurrentIndex(row)
        self.chapter_picker.blockSignals(False)
        self.show_chapter()

    def show_chapter(self, *_args):
        chapter_id = self.chapter_picker.currentData()
        if chapter_id is None:
            self.handbook_browser.setPlainText(
                text("No matching chapters.", "No hay capítulos coincidentes.")
            )
        else:
            self.handbook_browser.setMarkdown(chapter_text(chapter_id, language()))

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
        self.algorithm_id = None
        self.setWindowFlags(self.windowFlags() | qt_enum(Qt, "WindowType", "Tool"))
        self.setMinimumSize(480, 400)
        self.resize(720, 680)
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
            current = QgsApplication.processingRegistry().algorithmById(
                self.algorithm_id
            )
            if current is not None:
                self.set_algorithm(current)

    def set_algorithm(self, algorithm):
        """Render QGIS help, parameters and trusted reference links."""
        self.algorithm = algorithm
        self.algorithm_id = algorithm.id()
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

        implementation_rows = []
        for label, value in getattr(algorithm, "implementation_details", ()):
            implementation_rows.append(
                "<tr>"
                f"<td><b>{html.escape(translate(label))}</b></td>"
                f"<td>{html.escape(translate(value))}</td>"
                "</tr>"
            )

        links = _algorithm_reference_links(algorithm)
        link_items = "".join(
            f'<li><a href="{url}">{html.escape(name)}</a></li>' for name, url in links
        )
        self.setWindowTitle(f"TerraWorkbench — {algorithm.displayName()}")
        self.browser.setHtml(
            f"<h2>{html.escape(algorithm.displayName())}</h2>"
            f"<p><b>{text('Group', 'Grupo')}:</b> {html.escape(algorithm.group())}<br>"
            f"<b>{text('Numerical domain', 'Dominio numérico')}:</b> {html.escape(domain)}<br>"
            f"<b>ID Processing:</b> <code>{html.escape(algorithm.id())}</code></p>"
            f"<h3>{text('Implementation and libraries', 'Implementación y librerías')}</h3>"
            f"<table cellspacing='5'>{''.join(implementation_rows)}</table>"
            f"<p><small>{text('Libraries are shown here for transparency; the domain label describes where the calculation operates, not which package implements it.', 'Las librerías se muestran aquí por transparencia; la etiqueta de dominio indica dónde opera el cálculo, no qué paquete lo implementa.')}</small></p>"
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
    if any(term in searchable for term in ("fft", "spectral", "frequency", "fourier")):
        links.append(
            ("GMT grid FFT reference", "https://github.com/GenericMappingTools/gmt")
        )
    if any(
        term in searchable for term in ("igrf", "field-direction", "pole", "equator")
    ):
        links.append(("ppigrf / IGRF-14", "https://github.com/IAGA-VMOD/ppigrf"))
    if any(term in searchable for term in ("bouguer", "normal gravity", "latitude")):
        links.append(("Boule geodetic reference", "https://github.com/fatiando/boule"))
    if any(term in searchable for term in ("gamma", "radiometr", "dose", "euth")):
        links.extend(
            (
                (
                    "IAEA radioelement-mapping guidelines",
                    "https://www-pub.iaea.org/MTCD/publications/PDF/te_1363_web/PDF/Contents.pdf",
                ),
                (
                    "Geoscience Australia radiometrics",
                    "https://www.ga.gov.au/scientific-topics/disciplines/geophysics/radiometrics",
                ),
            )
        )
    if not links:
        links.append(
            (
                "TerraWorkbench reference ecosystem",
                "https://github.com/fatiando/harmonica",
            )
        )
    return links


class ElidedButton(QPushButton):
    """Keep full scientific labels in the tooltip while rendering explicit ellipsis."""

    def __init__(self, value="", parent=None):
        self.full_text = str(value)
        super().__init__(value, parent)

    def setText(self, value):
        self.full_text = str(value)
        self.setToolTip(self.full_text)
        self.update_elision()

    def update_elision(self):
        width = max(1, self.width() - 24)
        value = "\n".join(
            self.fontMetrics().elidedText(
                line, qt_enum(Qt, "TextElideMode", "ElideRight"), width
            )
            for line in self.full_text.splitlines()
        )
        super().setText(value)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_elision()


class FilterStackDock(QDockWidget):
    """Right-side QGIS panel for composing sequential raster filters."""

    languageChanged = pyqtSignal()
    workspaceRequested = pyqtSignal(str, str)

    def __init__(self, parent=None, *, iface=None):
        super().__init__("TerraWorkbench — Filter Stack", parent)
        self.setObjectName("TerraWorkbenchFilterStackDock")
        self.setMinimumWidth(320)
        self.resize(460, 820)
        self.setWindowIcon(QIcon(str(BRAND_ICON_PATH)))
        self._parameter_editors = {}
        self.last_stages = []
        self._algorithm_labels = {}
        self._warned_work_directories = set()
        self._ignored_temporary_imports = set()
        self.iface = iface
        self.hillshade = HillshadeActions(self, iface)
        self._build_ui()
        self.apply_preferences()
        self.retranslate()
        self._connect_project()
        self.refresh_layers()
        self.refresh_algorithms()

    def _build_ui(self):
        body = QWidget(self)
        body.setObjectName("TerraWorkbenchBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self.header = QFrame()
        self.header.setObjectName("TerraWorkbenchHeader")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(12, 10, 12, 10)
        self.brand_icon = QLabel()
        self.brand_icon.setObjectName("TerraWorkbenchBrandIcon")
        self.brand_icon.setPixmap(QIcon(str(BRAND_ICON_PATH)).pixmap(QSize(36, 36)))
        self.brand_icon.setFixedSize(40, 40)
        brand_copy = QVBoxLayout()
        brand_copy.setSpacing(1)
        self.brand_title = QLabel("TerraWorkbench")
        self.brand_title.setObjectName("TerraWorkbenchBrandTitle")
        self.brand_subtitle = QLabel("Geophysical workflow builder")
        self.brand_subtitle.setObjectName("TerraWorkbenchBrandSubtitle")
        brand_copy.addWidget(self.brand_title)
        brand_copy.addWidget(self.brand_subtitle)
        header_layout.addWidget(self.brand_icon)
        header_layout.addLayout(brand_copy, 1)
        layout.addWidget(self.header)

        self.work_directory_button = QToolButton()
        self.work_directory_menu = QMenu(self.work_directory_button)
        self.work_directory_menu.setToolTipsVisible(True)
        self.work_directory_menu.aboutToShow.connect(self._populate_work_directory_menu)
        self.work_directory_button.setMenu(self.work_directory_menu)
        self.work_directory_button.setPopupMode(
            qt_enum(QToolButton, "ToolButtonPopupMode", "InstantPopup")
        )
        self.quick_tools = QGridLayout()
        self.quick_tools.setColumnStretch(3, 1)
        self._quick_tools_wrapped = None
        self.workspace_button = QToolButton()
        self.workspace_button.clicked.connect(lambda: self.workspaceRequested.emit("", ""))
        layout.addLayout(self.quick_tools)

        self.source_group = QGroupBox("Input raster")
        self.source_group.setObjectName("TerraWorkbenchSection")
        source_layout = QFormLayout(self.source_group)
        self.layer_combo = QComboBox()
        self.layer_combo.currentIndexChanged.connect(self.hillshade.refresh)
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

        workflow_heading = QHBoxLayout()
        self.workflow_title = QLabel("FILTER WORKFLOW")
        self.workflow_title.setObjectName("TerraWorkbenchSectionTitle")
        self.step_count = QLabel("0 filters")
        self.step_count.setObjectName("TerraWorkbenchCountBadge")
        workflow_heading.addWidget(self.workflow_title)
        workflow_heading.addStretch(1)
        workflow_heading.addWidget(self.step_count)
        layout.addLayout(workflow_heading)

        add_row = QHBoxLayout()
        self.algorithm_combo = QComboBox()
        self.algorithm_combo.hide()
        self.algorithm_button = ElidedButton("Choose filter…")
        self.algorithm_button.setObjectName("TerraWorkbenchAlgorithmButton")
        self.algorithm_button.setSizePolicy(
            qt_enum(QSizePolicy, "Policy", "Ignored"),
            qt_enum(QSizePolicy, "Policy", "Fixed"),
        )
        self.algorithm_button.setToolTip("Open the filter catalogue")
        self.add_button = QPushButton("Add filter")
        self.add_button.setObjectName("TerraWorkbenchAccentButton")
        add_row.addWidget(self.algorithm_button, 1)
        add_row.addWidget(self.add_button)
        layout.addLayout(add_row)

        self.empty_stack_note = QLabel(
            "No filters yet. Choose a method above, then add it to the workflow."
        )
        self.empty_stack_note.setObjectName("TerraWorkbenchEmptyState")
        self.empty_stack_note.setWordWrap(True)
        self.empty_stack_note.setAlignment(qt_enum(Qt, "AlignmentFlag", "AlignCenter"))
        layout.addWidget(self.empty_stack_note)

        self.step_list = QListWidget()
        self.step_list.setObjectName("TerraWorkbenchStepList")
        self.step_list.setAlternatingRowColors(True)
        self.step_list.setDragDropMode(
            qt_enum(QAbstractItemView, "DragDropMode", "InternalMove")
        )
        self.step_list.setDefaultDropAction(qt_enum(Qt, "DropAction", "MoveAction"))
        self.step_list.setDragEnabled(True)
        self.step_list.setAcceptDrops(True)
        self.step_list.setDropIndicatorShown(True)
        layout.addWidget(self.step_list, 1)

        self.stack_actions_layout = QGridLayout()
        self.move_up_button = QToolButton()
        self.move_up_button.setIcon(
            self.style().standardIcon(qt_enum(QStyle, "StandardPixmap", "SP_ArrowUp"))
        )
        self.move_down_button = QToolButton()
        self.move_down_button.setIcon(
            self.style().standardIcon(qt_enum(QStyle, "StandardPixmap", "SP_ArrowDown"))
        )
        for button in (self.move_up_button, self.move_down_button):
            button.setIconSize(QSize(16, 16))
            button.setToolButtonStyle(
                qt_enum(Qt, "ToolButtonStyle", "ToolButtonTextBesideIcon")
            )
        self.duplicate_button = QPushButton("Duplicate")
        self.remove_button = QPushButton("Remove")
        self.clear_button = QPushButton("Clear")
        self.parameters_button = QPushButton("Parameters")
        self.stack_actions_layout.addWidget(self.move_up_button, 0, 0)
        self.stack_actions_layout.addWidget(self.move_down_button, 0, 1)
        self.stack_actions_layout.addWidget(self.parameters_button, 0, 2)
        self.stack_actions_layout.addWidget(self.duplicate_button, 1, 0)
        self.stack_actions_layout.addWidget(self.remove_button, 1, 1)
        self.stack_actions_layout.addWidget(self.clear_button, 1, 2)
        for column in range(3):
            self.stack_actions_layout.setColumnStretch(column, 1)
        layout.addLayout(self.stack_actions_layout)

        self.inspector = QDialog(self.parentWidget() or self)
        self.inspector.setObjectName("TerraWorkbenchFilterInspector")
        self.inspector.setWindowTitle("TerraWorkbench — Filter inspector")
        self.inspector.setWindowFlags(
            self.inspector.windowFlags() | qt_enum(Qt, "WindowType", "Tool")
        )
        self.inspector.setMinimumWidth(520)
        self.inspector.resize(720, 720)
        inspector_layout = QVBoxLayout(self.inspector)
        self.inspector_tabs = QTabWidget()
        parameter_tab = QWidget()
        parameter_tab_layout = QVBoxLayout(parameter_tab)
        self.parameter_group = QGroupBox("Selected filter parameters")
        self.parameter_form = QFormLayout(self.parameter_group)
        self.parameter_form.setRowWrapPolicy(
            qt_enum(QFormLayout, "RowWrapPolicy", "WrapLongRows")
        )
        self.parameter_form.setVerticalSpacing(12)
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
        parameter_scroll = QScrollArea()
        parameter_scroll.setWidgetResizable(True)
        parameter_scroll.setWidget(parameter_tab)
        self.inspector_tabs.addTab(parameter_scroll, "Parameters")
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
            self.algorithm_picker.windowFlags() | qt_enum(Qt, "WindowType", "Tool")
        )
        self.algorithm_picker.setMinimumWidth(560)
        self.algorithm_picker.resize(840, 700)
        picker_layout = QVBoxLayout(self.algorithm_picker)
        picker_layout.setSpacing(12)
        self.domain_filter = QComboBox()
        for key in ("", "SPACE", "FREQUENCY", "MIXED", "MODEL", "OTHER"):
            self.domain_filter.addItem(key, key)
        self.domain_filter.currentIndexChanged.connect(
            lambda: self.filter_algorithm_picker(self.algorithm_search.text())
        )
        picker_layout.addWidget(self.domain_filter)
        self.domain_note = QLabel(
            "SPATIAL = cells and neighbours; FREQUENCY = 2D Fourier/wavenumber; "
            "MIXED = spatial + frequency; PHYSICAL MODEL = equations constrained "
            "by geophysical parameters. Database describes the input, not a numerical domain."
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
        self.algorithm_list.setSpacing(4)
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
        self.output_group.setObjectName("TerraWorkbenchSection")
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
        self.review_stages_button = QPushButton()
        self.review_stages_button.setEnabled(False)
        self.review_stages_button.clicked.connect(self.review_stages)
        output_layout.addWidget(self.review_stages_button, 2, 0, 1, 2)
        layout.addWidget(self.output_group)

        self.file_grid = QGridLayout()
        self.import_button = QPushButton("Import…")
        self.knowledge_button = QPushButton("Knowledge…")
        self.knowledge_button.setToolTip(
            "Open formulas, limitations and trusted open-source repositories"
        )
        self.import_menu = QMenu(self.import_button)
        self.import_grid_action = self.import_menu.addAction(
            "Survey grid file…", self.import_grid
        )
        self.import_gdb_action = self.import_menu.addAction(
            "Esri FileGDB folder…", self.import_filegdb
        )
        self.import_geosoft_action = self.import_menu.addAction(
            "Geosoft GeoDatabase inventory/export…", self.import_geosoft_gdb
        )
        self.open_archive_action = self.import_menu.addAction(
            "Open converted survey archive…", self.import_open_archive
        )
        self.export_geosoft_action = self.import_menu.addAction(
            "Export Geosoft GeoDatabase to folder…",
            lambda: self.import_geosoft_gdb(choose_destination=True),
        )
        self.save_import_action = self.import_menu.addAction(
            "Save as GeoTIFF…", self.save_imported_grid
        )
        self.import_menu.aboutToShow.connect(self._update_import_actions)
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
        self.refresh_bundled_reference_actions()
        self.example_menu.aboutToShow.connect(self.refresh_bundled_reference_actions)
        self.local_data_menu = self.import_menu.addMenu("Local test datasets")
        self.local_data_menu.aboutToShow.connect(self.refresh_local_data_menu)
        self.refresh_local_data_menu()
        self.import_button.setMenu(self.import_menu)
        self.load_button = QPushButton("Load stack…")
        self.save_button = QPushButton("Save stack…")
        self.run_button = QPushButton("Run stack")
        self.run_button.setObjectName("TerraWorkbenchPrimaryButton")
        self.run_button.setMinimumHeight(34)
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
        self._apply_visual_style()
        self.algorithm_button.clicked.connect(self.show_algorithm_picker)
        self.algorithm_search.textChanged.connect(self.filter_algorithm_picker)
        self.algorithm_list.itemClicked.connect(self.choose_algorithm_item)
        self.add_button.clicked.connect(self.add_step)
        self.step_list.currentRowChanged.connect(self.show_step_parameters)
        self.parameters_button.clicked.connect(
            lambda: self.show_step_parameters(self.step_list.currentRow())
        )
        self.duplicate_button.clicked.connect(self.duplicate_step)
        self.remove_button.clicked.connect(self.remove_step)
        self.clear_button.clicked.connect(self.clear_stack)
        self.move_up_button.clicked.connect(lambda: self.move_step(-1))
        self.move_down_button.clicked.connect(lambda: self.move_step(1))
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
        self.step_list.model().rowsInserted.connect(self._update_stack_state)
        self.step_list.model().rowsRemoved.connect(self._update_stack_state)
        self.step_list.model().rowsMoved.connect(self._update_stack_state)
        self.step_list.currentRowChanged.connect(self._update_stack_state)
        self._update_stack_state()

    def _apply_visual_style(self):
        """Apply a restrained theme that stays legible in light and dark QGIS."""
        dark = self.palette().window().color().lightness() < 128
        if dark:
            panel = "#263238"
            border = "#455a64"
            muted = "#b0bec5"
            empty = "#1f292e"
            hover = "#37474f"
        else:
            panel = "#f4f8f7"
            border = "#cbd9d5"
            muted = "#526460"
            empty = "#f8faf9"
            hover = "#e6f0ed"
        self.widget().setStyleSheet(
            f"""
            #TerraWorkbenchHeader {{
                background: {panel}; border: 1px solid {border};
                border-radius: 8px;
            }}
            #TerraWorkbenchBrandTitle {{ font-size: 15px; font-weight: 700; }}
            #TerraWorkbenchBrandSubtitle {{ color: {muted}; font-size: 11px; }}
            #TerraWorkbenchSection {{
                border: 1px solid {border}; border-radius: 7px;
                margin-top: 7px; padding-top: 7px;
            }}
            #TerraWorkbenchSection::title {{
                subcontrol-origin: margin; left: 10px; padding: 0 5px;
                font-weight: 600;
            }}
            #TerraWorkbenchSectionTitle {{
                color: {muted}; font-size: 10px; font-weight: 700;
            }}
            #TerraWorkbenchCountBadge {{
                background: {panel}; border: 1px solid {border};
                border-radius: 8px; padding: 2px 7px; color: {muted};
            }}
            #TerraWorkbenchEmptyState {{
                background: {empty}; border: 1px dashed {border};
                border-radius: 7px; padding: 12px; color: {muted};
            }}
            #TerraWorkbenchStepList {{
                border: 1px solid {border}; border-radius: 6px;
                padding: 3px; alternate-background-color: {panel};
            }}
            #TerraWorkbenchStepList::item {{ padding: 7px 5px; border-radius: 4px; }}
            #TerraWorkbenchStepList::item:hover {{ background: {hover}; }}
            #TerraWorkbenchAlgorithmButton {{ text-align: left; padding: 5px 8px; }}
            #TerraWorkbenchAccentButton {{ font-weight: 600; padding: 5px 9px; }}
            #TerraWorkbenchPrimaryButton {{
                background: #147d64; color: white; border: 1px solid #0f6853;
                border-radius: 6px; font-weight: 700; padding: 7px 12px;
            }}
            #TerraWorkbenchPrimaryButton:hover {{ background: #198f73; }}
            #TerraWorkbenchPrimaryButton:pressed {{ background: #0f6853; }}
            #TerraWorkbenchPrimaryButton:disabled {{
                background: {panel}; color: {muted}; border-color: {border};
            }}
            """
        )

    def _update_stack_state(self, *_args):
        count = self.step_list.count()
        selected = self.step_list.currentRow()
        self.step_count.setText(
            text(
                "{count} filter" if count == 1 else "{count} filters",
                "{count} filtro" if count == 1 else "{count} filtros",
            ).format(count=count)
        )
        self.empty_stack_note.setVisible(count == 0)
        self.run_button.setEnabled(count > 0 and self.layer_combo.count() > 0)
        self.save_button.setEnabled(count > 0)
        self.clear_button.setEnabled(count > 0)
        self.duplicate_button.setEnabled(selected >= 0)
        self.parameters_button.setEnabled(selected >= 0)
        self.remove_button.setEnabled(selected >= 0)
        self.move_up_button.setEnabled(selected > 0)
        self.move_down_button.setEnabled(0 <= selected < count - 1)

    def move_step(self, offset):
        """Move the selected filter one position while preserving its data."""
        row = self.step_list.currentRow()
        target = row + int(offset)
        if row < 0 or target < 0 or target >= self.step_list.count():
            return
        item = self.step_list.takeItem(row)
        self.step_list.insertItem(target, item)
        self.step_list.setCurrentItem(item)

    def apply_preferences(self):
        settings = QgsSettings()
        self.band_spin.setValue(settings.value(KEY_BAND, 1, type=int))
        self.output_directory.setText(settings.value(KEY_OUTPUT, "", type=str))
        self.keep_intermediate.setChecked(settings.value(KEY_KEEP, False, type=bool))
        tooltips = settings.value(KEY_TOOLTIPS, True, type=bool)
        self.algorithm_button.setToolTip(
            text(
                "Open the filter catalogue",
                "Abrir el catálogo de filtros",
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
        if getattr(self, "_survey_notices", None):
            from .survey_workspace_dialog import translate_survey_notices

            translate_survey_notices(self)
        self.brand_subtitle.setText(
            text("Geophysical workflow builder", "Constructor de flujos geofísicos")
        )
        self.workflow_title.setText(text("FILTER WORKFLOW", "FLUJO DE FILTROS"))
        self.empty_stack_note.setText(
            text(
                "No filters yet. Choose a method above, then add it to the workflow.",
                "Aún no hay filtros. Elija un método arriba y añádalo al flujo.",
            )
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
        self.move_up_button.setText(text("Up", "Subir"))
        self.move_down_button.setText(text("Down", "Bajar"))
        self.move_up_button.setToolTip(
            text("Move the selected filter up", "Subir el filtro seleccionado")
        )
        self.move_down_button.setToolTip(
            text("Move the selected filter down", "Bajar el filtro seleccionado")
        )
        self.step_list.setToolTip(
            text(
                "Drag filters to change their execution order.",
                "Arrastre los filtros para cambiar su orden de ejecución.",
            )
        )
        self.inspector.setWindowTitle(
            text(
                "TerraWorkbench — Filter inspector",
                "TerraWorkbench — Inspector de filtros",
            )
        )
        self.parameter_group.setTitle(
            text("Selected filter parameters", "Parámetros del filtro seleccionado")
        )
        self.parameters_button.setText(text("Parameters", "Parámetros"))
        self.empty_parameters.setText(
            text(
                "Select a filter to edit its parameters.",
                "Seleccione un filtro para editar sus parámetros.",
            )
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
                "SPATIAL = cells and neighbours; FREQUENCY = 2D Fourier/wavenumber; MIXED = spatial + frequency; PHYSICAL MODEL = equations constrained by geophysical parameters. Database describes the input, not a numerical domain.",
                "ESPACIAL: celdas y sus vecinas. FRECUENCIA: Fourier 2D y número de onda. MIXTO: combina ambos dominios. MODELO FÍSICO: ecuaciones con parámetros geofísicos. Una base de datos es un tipo de entrada, no un dominio numérico.",
            )
        )
        for index, label in enumerate(
            (
                "All domains",
                "Spatial · 2D grids",
                "Frequency · 2D Fourier",
                "Mixed · space and frequency",
                "Physical models",
                "Other grid operations",
            )
        ):
            self.domain_filter.setItemText(index, translate(label))
        self.search_label.setText(
            text(
                "Search by method, group or abbreviation",
                "Buscar por método, grupo o abreviatura",
            )
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
            text(
                "Temporary output (or choose a folder)",
                "Salida temporal (o elija una carpeta)",
            )
        )
        self.output_browse.setText(text("Browse…", "Examinar…"))
        from .survey_workspace_dialog import tr

        self.review_stages_button.setText(
            tr(
                "Review last run stages…",
                "Revisar etapas de la última ejecución…",
                "Revisar etapas da última execução…",
            )
        )
        self.keep_intermediate.setText(
            text("Save every intermediate raster", "Guardar cada ráster intermedio")
        )
        self.import_button.setText(text("Import…", "Importar…"))
        self.knowledge_button.setText(text("Knowledge…", "Conocimiento…"))
        self.load_button.setText(text("Load stack…", "Cargar pila…"))
        self.save_button.setText(text("Save stack…", "Guardar pila…"))
        self.run_button.setText(text("Run stack", "Ejecutar pila"))
        self.settings_button.setText(text("Settings…", "Configuración…"))
        self.import_grid_action.setText(
            text("Survey grid file…", "Archivo de grilla de levantamiento…")
        )
        self.import_gdb_action.setText(
            text("Esri FileGDB folder…", "Carpeta Esri FileGDB…")
        )
        self.import_geosoft_action.setText(
            text(
                "Geosoft GeoDatabase inventory/export…",
                "Inventario y exportación de GeoDatabase Geosoft…",
            )
        )
        self.export_geosoft_action.setText(text(
            "Export Geosoft GeoDatabase to folder…",
            "Exportar GeoDatabase Geosoft a una carpeta…",
        ))
        self.open_archive_action.setText(text(
            "Open converted survey archive…", "Abrir copia abierta de levantamiento…"
        ))
        self.refresh_work_directory()
        self.hillshade.retranslate()
        self.workspace_button.setText(text("Databases…", "Bases de datos…"))
        self._layout_quick_tools()
        for layer in QgsProject.instance().mapLayers().values():
            if is_temporary_import(layer):
                self._mark_import(layer)
        self.example_menu.setTitle(
            text("Bundled sample datasets", "Datos de ejemplo incluidos")
        )
        self.sample_mag_action.setText(
            text("Synthetic magnetic anomaly (nT)", "Anomalía magnética sintética (nT)")
        )
        self.sample_grav_action.setText(
            text(
                "Synthetic gravity anomaly (mGal)",
                "Anomalía gravimétrica sintética (mGal)",
            )
        )
        self.sample_dem_action.setText(text("Synthetic DEM (m)", "DEM sintético (m)"))
        self.sample_k_action.setText(
            text("Synthetic potassium (% K)", "Potasio sintético (% K)")
        )
        self.sample_u_action.setText(
            text(
                "Synthetic equivalent uranium (ppm eU)",
                "Uranio equivalente sintético (ppm eU)",
            )
        )
        self.sample_th_action.setText(
            text(
                "Synthetic equivalent thorium (ppm eTh)",
                "Torio equivalente sintético (ppm eTh)",
            )
        )
        self.sample_points_action.setText(
            text(
                "Synthetic survey points (CSV)",
                "Puntos sintéticos de levantamiento (CSV)",
            )
        )
        self.nrcan_menu.setTitle(
            text("NRCan field reference grids", "Grillas reales de referencia NRCan")
        )
        self.nrcan_hydraulic_dem_action.setText("Hydraulic — DEM")
        self.nrcan_hydraulic_mag_action.setText(
            text("Hydraulic — residual magnetics", "Hydraulic — magnetometría residual")
        )
        self.local_data_menu.setTitle(
            text("Local test datasets", "Datos locales de prueba")
        )
        self.refresh_local_data_menu()
        self.knowledge_base.retranslate()
        self.filter_info.retranslate()
        self.settings_dialog.retranslate()
        for index in range(self.step_list.count()):
            item = self.step_list.item(index)
            self._set_item_step(item, self._item_step(item))
        if self.step_list.currentRow() >= 0:
            if self.update_current_parameters():
                self.show_step_parameters(self.step_list.currentRow(), reveal=False)
        self._update_stack_state()

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
        project.writeProject.connect(self.warn_temporary_imports)
        project.readProject.connect(self._work_project_changed)
        project.cleared.connect(self._work_project_changed)

    def disconnect_project(self):
        self.hillshade.close()
        if getattr(self, "_survey_notices", None):
            from .survey_workspace_dialog import close_survey_notices

            close_survey_notices(self)
        project = QgsProject.instance()
        for signal in (project.layersAdded, project.layersRemoved):
            try:
                signal.disconnect(self.refresh_layers)
            except (TypeError, RuntimeError):
                pass
        for signal, slot in (
            (project.writeProject, self.warn_temporary_imports),
            (project.readProject, self._work_project_changed),
            (project.cleared, self._work_project_changed),
        ):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self.algorithm_picker.close()
        self.inspector.close()
        self.knowledge_base.close()
        self.filter_info.close()
        self.settings_dialog.close()

    def showEvent(self, event):
        self.refresh_work_directory()
        self.refresh_layers()
        self.refresh_algorithms()
        super().showEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "workspace_button"):
            self._layout_quick_tools()

    def _layout_quick_tools(self):
        buttons = (self.work_directory_button, self.hillshade.button, self.workspace_button)
        width = sum(button.sizeHint().width() for button in buttons) + 2 * self.quick_tools.spacing()
        wrapped = width > self.width() - 24
        if wrapped == self._quick_tools_wrapped:
            return
        self._quick_tools_wrapped = wrapped
        for button in buttons:
            self.quick_tools.removeWidget(button)
        align = qt_enum(Qt, "AlignmentFlag", "AlignLeft")
        if wrapped:
            self.quick_tools.addWidget(buttons[0], 0, 0, 1, 3, align)
            self.quick_tools.addWidget(buttons[1], 1, 0, align)
            self.quick_tools.addWidget(buttons[2], 1, 1, align)
        else:
            for column, button in enumerate(buttons):
                self.quick_tools.addWidget(button, 0, column, align)

    def refresh_layers(self, *_args):
        selected_id = self.layer_combo.currentData()
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        layers = [
            layer
            for layer in QgsProject.instance().mapLayers().values()
            if isinstance(layer, QgsRasterLayer) and layer.isValid() and not layer.customProperty(EFFECT)
        ]
        for layer in sorted(layers, key=lambda item: item.name().casefold()):
            self.layer_combo.addItem(layer.name(), layer.id())
        selected_index = self.layer_combo.findData(selected_id)
        if selected_index >= 0:
            self.layer_combo.setCurrentIndex(selected_index)
        self.layer_combo.blockSignals(False)
        self.hillshade.refresh()
        self._update_stack_state()

    def refresh_algorithms(self):
        selected_id = self.algorithm_combo.currentData()
        self.algorithm_combo.clear()
        self.algorithm_list.clear()
        self._algorithm_labels.clear()
        for algorithm in available_algorithms():
            label = (
                f"[{translate(algorithm_domain(algorithm))}] "
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
            item.setData(qt_enum(Qt, "ItemDataRole", "UserRole"), algorithm.id())
            item.setData(_SEARCH_TEXT_ROLE, label)
            item.setToolTip(label)
            self.algorithm_list.addItem(item)
            row = QWidget(self.algorithm_list)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(2, 1, 2, 1)
            choose_button = ElidedButton(
                algorithm.displayName()
                + "\n"
                + translate(algorithm_domain(algorithm))
                + " · "
                + algorithm.group()
            )
            choose_button.setFlat(True)
            choose_button.setStyleSheet("text-align: left; padding: 10px;")
            choose_button.setMinimumHeight(64)
            choose_button.setSizePolicy(
                qt_enum(QSizePolicy, "Policy", "Ignored"),
                qt_enum(QSizePolicy, "Policy", "Fixed"),
            )
            choose_button.setToolTip(label)
            choose_button.clicked.connect(
                lambda _checked=False, algorithm_id=algorithm.id(): (
                    self.choose_algorithm_id(algorithm_id)
                )
            )
            info_button = QToolButton()
            info_button.setText("i")
            info_button.setToolTip(
                translate("Method, parameters and libraries")
                + ": "
                + algorithm.displayName()
            )
            info_button.setFixedWidth(30)
            info_button.clicked.connect(
                lambda _checked=False, algorithm_id=algorithm.id(): (
                    self.show_algorithm_info(algorithm_id)
                )
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
        self.filter_algorithm_picker(self.algorithm_search.text())

    def _update_algorithm_button(self):
        algorithm_id = self.algorithm_combo.currentData()
        label = self._algorithm_labels.get(algorithm_id, "Choose filter…")
        self.algorithm_button.setText(label)
        self.algorithm_button.setToolTip(label)

    def filter_algorithm_picker(self, text):
        words = text.casefold().split()
        selected_domain = self.domain_filter.currentData()
        for index in range(self.algorithm_list.count()):
            item = self.algorithm_list.item(index)
            label = str(item.data(_SEARCH_TEXT_ROLE) or "").casefold()
            algorithm = self._algorithm(
                item.data(qt_enum(Qt, "ItemDataRole", "UserRole"))
            )
            domain = algorithm_domain(algorithm).upper() if algorithm else ""
            category = (
                "MIXED"
                if "MIXED" in domain
                else "MODEL"
                if "MODEL" in domain
                else "FREQUENCY"
                if "FREQUENCY" in domain
                else "SPACE"
                if "SPACE" in domain or "SPATIAL" in domain
                else "OTHER"
            )
            item.setHidden(
                not all(word in label for word in words)
                or bool(selected_domain and selected_domain != category)
            )

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
            QMessageBox.warning(
                self,
                "TerraWorkbench",
                text("No filter is selected.", "No hay ningún filtro seleccionado."),
            )
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
                widget.hide()
                widget.deleteLater()
        self._parameter_editors.clear()

    def show_step_parameters(self, row, *, reveal=True):
        self._clear_parameter_form()
        if row < 0:
            self.parameter_form.addRow(
                QLabel(
                    text(
                        "Select a filter to edit its parameters.",
                        "Seleccione un filtro para editar sus parámetros.",
                    )
                )
            )
            return
        item = self.step_list.item(row)
        step = self._item_step(item)
        algorithm = self._algorithm(step.algorithm_id)
        if algorithm is None:
            self.parameter_form.addRow(
                QLabel(
                    text(
                        "This filter is not currently available.",
                        "Este filtro no está disponible actualmente.",
                    )
                )
            )
            return

        editable = 0
        for definition in algorithm.parameterDefinitions():
            if definition.name() in _FIXED_PARAMETERS:
                continue
            # Provider refresh deletes its C++ parameter objects. Editors must
            # own copies so switching language cannot invalidate unsaved values.
            parameter = definition.clone()
            editor = QLineEdit()
            value = step.parameters.get(parameter.name())
            editor.setText("" if value is None else str(value))
            optional = processing_parameter_is_optional(parameter)
            editor.setPlaceholderText(
                text("Optional", "Opcional")
                if optional
                else text("Required", "Obligatorio")
            )
            editor.editingFinished.connect(self.update_current_parameters)
            self._parameter_editors[parameter.name()] = (editor, parameter)
            self.parameter_form.addRow(parameter.description(), editor)
            editable += 1
        if not editable:
            self.parameter_form.addRow(
                QLabel(
                    text(
                        "This filter has no additional parameters.",
                        "Este filtro no tiene parámetros adicionales.",
                    )
                )
            )
        if reveal:
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
        available = (
            screen.availableGeometry() if screen else primary.availableGeometry()
        )
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
            text(
                "Survey grids (*.grd *.GRD *.gxf *.GXF *.tif *.tiff *.asc *.xyz *.csv *.txt *.gdb);;All files (*)",
                "Grillas de levantamiento (*.grd *.GRD *.gxf *.GXF *.tif *.tiff *.asc *.xyz *.csv *.txt *.gdb);;Todos los archivos (*)",
            ),
        )
        if not source:
            return
        if Path(source).suffix.lower() == ".gdb":
            self.import_geosoft_gdb(source)
            return
        self._finish_import(source)

    @staticmethod
    def _sample_path(filename):
        return PLUGIN_ROOT / "sample_data" / "synthetic" / filename

    def load_sample_raster(self, filename):
        """Load a bundled redistributable raster and select it as stack input."""
        source = self._sample_path(filename)
        layer = QgsRasterLayer(str(source), source.stem.replace("_", " ").title())
        if not layer.isValid():
            QMessageBox.critical(
                self,
                text(
                    "TerraWorkbench sample data", "Datos de ejemplo de TerraWorkbench"
                ),
                text(
                    "The bundled sample raster could not be opened:\n{source}",
                    "No se pudo abrir el ráster de ejemplo incluido:\n{source}",
                ).format(source=source),
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
                text(
                    "TerraWorkbench sample data", "Datos de ejemplo de TerraWorkbench"
                ),
                text(
                    "The bundled survey points could not be opened:\n{source}",
                    "No se pudieron abrir los puntos de levantamiento incluidos:\n{source}",
                ).format(source=source),
            )
            return None
        QgsProject.instance().addMapLayer(layer)
        return layer

    @staticmethod
    def _nrcan_sample_path(relative_path):
        return PLUGIN_ROOT / "sample_data" / "nrcan" / relative_path

    def refresh_bundled_reference_actions(self):
        """Hide optional example actions when their source is not distributed."""
        entries = (
            (self.nrcan_hydraulic_dem_action, "Hydraulic/BC_2004_G_Hydraulic_dem.GRD"),
            (
                self.nrcan_hydraulic_mag_action,
                "Hydraulic/BC_2004_G_Hydraulic_mag_res.GRD",
            ),
        )
        for action, filename in entries:
            available = self._nrcan_sample_path(filename).is_file()
            action.setEnabled(available)
            action.setVisible(available)
        self.nrcan_menu.menuAction().setVisible(any(a.isVisible() for a, _ in entries))

    def load_bundled_reference_grid(self, relative_path):
        """Convert a redistributable NRCan GRD without modifying its source."""
        source = self._nrcan_sample_path(relative_path)
        if not source.is_file():
            QMessageBox.critical(
                self,
                "TerraWorkbench",
                text(
                    "The bundled NRCan grid could not be found:\n{source}",
                    "No se encontró la grilla NRCan incluida:\n{source}",
                ).format(source=source),
            )
            return None
        self._finish_import(str(source))
        return source

    @staticmethod
    def _default_local_data_directory():
        candidate = PLUGIN_ROOT / "sample_data" / "local_private"
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
        supported = {
            ".tif",
            ".tiff",
            ".grd",
            ".gxf",
            ".asc",
            ".xyz",
            ".csv",
            ".txt",
            ".gdb",
        }
        candidates = [
            path
            for path in directory.rglob("*")
            if (path.is_file() and path.suffix.casefold() in supported)
            or (path.is_dir() and path.suffix.casefold() == ".gdb")
        ]
        # Do not list the internal files of an Esri FileGDB separately.
        filegdb_directories = {
            path
            for path in candidates
            if path.is_dir() and path.suffix.casefold() == ".gdb"
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
                text(
                    "No supported datasets found",
                    "No se encontraron datasets compatibles",
                )
            )
            empty.setEnabled(False)

    def open_local_test_data(self, source):
        """Open a real local reference dataset while preserving its source file."""
        source = Path(source)
        if (source.is_dir() and (source / "archive.json").is_file()) or source.name == "archive.json":
            return self.import_open_archive(str(source))
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
                    "The raster could not be opened:\n{source}",
                    "No se pudo abrir el ráster:\n{source}",
                ).format(source=source),
            )
            return None
        self._finish_import(str(source))
        return None

    def _geosoft_runtime(self):
        from .dependency_dialog import confirm_gx_conversion

        settings = QgsSettings()
        desktop = find_geosoft_runtime(settings.value("TerraWorkbench/geosoftLocation", ""))
        if desktop:
            if not confirm_gx_conversion(self):
                return None
            return desktop
        return self._managed_geosoft_runtime()

    def _managed_geosoft_runtime(self, *, confirm=True):
        """Return the managed GX runtime, which runs in QGIS' own Python."""
        from .dependency_dialog import check_gdb_connector, confirm_gx_conversion, gdb_dotnet_ready, gdb_support_state, prepare_gdb_support

        if not check_gdb_connector(self):
            return None

        package, redist = gdb_support_state()
        if package and redist and gdb_dotnet_ready():
            if confirm and not confirm_gx_conversion(self):
                return None
        else:
            if not prepare_gdb_support(self):
                return None
            package, redist = gdb_support_state()
        if package and redist and gdb_dotnet_ready():
            return GeosoftRuntime(dependency_directory(), None, Path(python_command()),
                                  standalone=True, redist=redist)
        return None

    def import_geosoft_gdb(self, source=None, *, choose_destination=False):
        """Ignore repeated import events while a prompt or conversion is active."""
        if getattr(self, "_gdb_import_active", False) or getattr(self, "_geosoft_process", None) is not None:
            return
        self._gdb_import_active = True
        try:
            return self._import_geosoft_gdb(source, choose_destination=choose_destination)
        finally:
            self._gdb_import_active = False

    def _import_geosoft_gdb(self, source=None, *, choose_destination=False):
        if not source:
            source, _selected_filter = QFileDialog.getOpenFileName(
                self,
                text("Choose Geosoft GeoDatabase", "Elegir GeoDatabase Geosoft"),
                "",
                "Geosoft GeoDatabase (*.gdb)",
            )
        if not source:
            return
        runtime = self._geosoft_runtime()
        if runtime is None:
            return
        choice_dialog = QMessageBox(self)
        choice_dialog.setWindowTitle(
            text("Geosoft GeoDatabase export", "Exportación de GeoDatabase Geosoft")
        )
        choice_dialog.setText(
            text(
                "Choose what to recover from the Geosoft GeoDatabase.",
                "Elija qué recuperar de la GeoDatabase Geosoft.",
            )
        )
        choice_dialog.setInformativeText(
            text(
                "The recommended archive preserves native types, text, arrays, dummies and per-channel fiducials, then verifies every channel against a second GX read.",
                "La copia recomendada conserva tipos nativos, texto, arrays, dummies y fiduciales por canal, y verifica cada canal con una segunda lectura GX.",
            )
        )
        inventory_button = choice_dialog.addButton(
            text("Inventory only", "Solo inventario"),
            qt_enum(QMessageBox, "ButtonRole", "ActionRole"),
        )
        extract_button = choice_dialog.addButton(
            text("Legacy numeric CSV (lossy)", "CSV numérico heredado (con pérdidas)"),
            qt_enum(QMessageBox, "ButtonRole", "AcceptRole"),
        )
        archive_button = choice_dialog.addButton(
            text("Convert to open archive (recommended)", "Convertir a archivo abierto (recomendado)"),
            qt_enum(QMessageBox, "ButtonRole", "AcceptRole"),
        )
        choice_dialog.setDefaultButton(archive_button)
        cancel_button = choice_dialog.addButton(
            qt_enum(QMessageBox, "StandardButton", "Cancel")
        )
        execute = getattr(choice_dialog, "exec", None) or choice_dialog.exec_
        execute()
        if choice_dialog.clickedButton() == cancel_button:
            return
        extract_all = choice_dialog.clickedButton() == extract_button
        open_archive = choice_dialog.clickedButton() == archive_button
        if choice_dialog.clickedButton() not in (inventory_button, extract_button, archive_button):
            return
        if open_archive and not runtime.standalone:
            # The verified open archive needs QGIS' Python and its managed
            # packages (pyarrow); a desktop install bundles another Python.
            runtime = self._managed_geosoft_runtime(confirm=False)
            if runtime is None:
                return
        destination = None
        if choose_destination:
            destination = QFileDialog.getExistingDirectory(
                self, text("Choose GDB export folder", "Elegir carpeta de exportación GDB")
            )
            if not destination:
                return
        try:
            output, temporary_root = self._import_destination(source, destination)
            output = str(output)
        except OSError as error:
            self._import_error(error)
            return
        bridge = PLUGIN_ROOT / "qgis_plugin/geosoft_bridge.py"
        arguments = [str(bridge), "--input", str(source), "--output", str(output)]
        if extract_all:
            arguments.append("--extract-all")
        if open_archive:
            arguments.append("--open-archive")
        process = QProcess(self)
        process_environment = QProcessEnvironment.systemEnvironment()
        # The child needs TerraWorkbench's managed packages (pyarrow, etc.)
        # with either GX engine, including the installed desktop runtime.
        process_environment.insert(
            "TERRAWORKBENCH_DEPENDENCY_PATH", str(dependency_directory())
        )
        if runtime.standalone:
            process_environment.remove("TERRAWORKBENCH_GX_DESKTOP")
            process_environment.insert("TERRAWORKBENCH_GEOSOFT_SITE", str(runtime.root))
            from ..qgis_plugin.gx_runtime_setup import dotnet_environment

            for key, value in dotnet_environment(dependency_directory() / "_gx_runtime").items():
                process_environment.insert(key, value)
            if runtime.redist:
                process_environment.insert("TERRAWORKBENCH_GX_REDIST", str(runtime.redist))
            process_environment.insert(
                "TERRAWORKBENCH_GEOSOFT_ENGINE",
                "Geosoft GX Developer public runtime (BSD-2-Clause)",
            )
        else:
            process_environment.insert("TERRAWORKBENCH_GX_DESKTOP", "1")
            process_environment.remove("TERRAWORKBENCH_GX_REDIST")
            process_environment.remove("TERRAWORKBENCH_GEOSOFT_SITE")
            process_environment.insert(
                "TERRAWORKBENCH_GEOSOFT_ENGINE",
                "Installed Geosoft Python runtime",
            )
        process.setProcessEnvironment(process_environment)
        starting_message = (
            text(
                "Starting the public Geosoft GX Developer reader…",
                "Iniciando el lector público Geosoft GX Developer…",
            )
            if runtime.standalone
            else text(
                "Starting the installed Geosoft runtime…",
                "Iniciando el runtime instalado de Geosoft…",
            )
        )
        progress = QProgressDialog(
            starting_message, text("Cancel", "Cancelar"), 0, 0, self
        )
        progress.setWindowTitle("TerraWorkbench — Geosoft GeoDatabase")
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
            progress.canceled.disconnect(cancel_process)
            progress.close()
            process.deleteLater()
            self._geosoft_process = None
            self._geosoft_progress = None
            if cancelled["value"]:
                return
            from .dependency_dialog import runtime_error_message, show_gx_error

            if exit_code == 0:
                if open_archive:
                    self.import_open_archive(Path(output) / (Path(source).stem + ".twarchive"))
                else:
                    self._load_geosoft_outputs(source, output, temporary_root)
            elif runtime.standalone and any(marker in error_text for marker in (
                "GX_DOTNET6:", "GX_REDIST_CONFIG:", "TW_GX_CHECK:", "geodist.dll", "hostfxr",
            )):
                show_gx_error(self, error_text)
            else:
                error_text = runtime_error_message(error_text)
                failure_text = (
                    text(
                        "The public Geosoft GX Developer reader failed.",
                        "Falló el lector público Geosoft GX Developer.",
                    )
                    if runtime.standalone
                    else text(
                        "The installed Geosoft runtime failed. Confirm that it is available to this user.",
                        "Falló el runtime instalado de Geosoft. Confirme que esté disponible para este usuario.",
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

    def import_open_archive(self, source=None):
        """Load a verified open copy with existing survey layers, without GX."""
        from ..terraworkbench_core.gdb_archive import open_archive, attach_archive
        if source is None:
            source, _ = QFileDialog.getOpenFileName(
                self, text("Open converted survey archive…", "Abrir copia abierta de levantamiento…"),
                "", "Open survey archive (archive.json catalog.sqlite *.parquet)",
            )
        if not source:
            return
        try:
            archived, _, manifest = open_archive(source)
            x, y = manifest.get("x_field"), manifest.get("y_field")
            pairs = {(row["line"], row["channel"]): (row["start"], row["increment"], row["length"])
                     for row in manifest["alignment"]}
            if x and y and any(pairs[(line["name"], x)] != pairs[(line["name"], y)] for line in manifest["lines"]):
                raise ValueError(text(
                    "X/Y fiducials differ. The archive is preserved; automatic map creation would require explicit alignment.",
                    "Los fiduciales X/Y difieren. El archivo se conserva; crear el mapa requiere una alineación explícita.",
                ))
        except (ValueError, OSError, KeyError) as error:
            self._import_error(error)
            return

        def import_data(store, canceled):
            return attach_archive(store, archived.root, canceled)

        name = Path(manifest["provenance"]["source_path"]).stem
        self._start_gdb_survey_maps(str(archived.root.parent), [(name, import_data)])

    def _start_gdb_survey_maps(self, folder, jobs, workspace=None):
        """Run the existing survey worker for point data from the GDB importers."""
        from qgis.PyQt.QtCore import QSettings
        from .survey_workspace_dialog import (
            KEY_WORKSPACE,
            StoreWorker,
            SurveyWorkspaceDialog,
            notify_survey_database,
        )
        from ..compat.survey_store import SurveyStore
        from ..qgis_plugin.survey_map_layers import add_survey_map

        saved = QSettings().value(KEY_WORKSPACE, "", type=str)
        fallback = Path(folder) / "TerraWorkbench surveys"
        workspace = workspace or (
            Path(saved)
            if saved and (Path(saved) / "catalog.sqlite").is_file()
            else fallback
        )

        def run(cancel, progress):
            store = SurveyStore(workspace, create=True)
            results = []
            for name, import_data in jobs:
                try:
                    database_id = import_data(store, canceled=cancel)
                    metadata = json.loads(next(row["metadata"] for row in store.databases() if row["id"] == database_id))
                    results.append(
                        SurveyWorkspaceDialog._try_survey_map(
                            store, database_id, cancel, progress, columns=metadata.get("gdb_map_columns")
                        )
                    )
                except InterruptedError:
                    raise
                except Exception as error:
                    results.append((None, name, None, str(error)))
            return store, results

        progress = QProgressDialog(
            text("Building survey map…", "Construyendo mapa del levantamiento…"),
            text("Cancel", "Cancelar"),
            0,
            0,
            self,
        )
        worker = StoreWorker(run, self)

        def complete(result):
            if getattr(self, "_tw_disposing", False):
                return
            store, results = result
            QSettings().setValue(KEY_WORKSPACE, str(store.root))
            messages, retry = [], []
            for database_id, name, package, error in results:
                if database_id:
                    notify_survey_database(self.iface, store.root, database_id, name, self)
                if package:
                    try:
                        add_survey_map(
                            QgsProject.instance(), store, database_id, name, package
                        )
                        if not package[2]["has_line_channel"]:
                            messages.append(
                                f"{name}: "
                                + text(
                                    "No line channel; samples and boundary only.",
                                    "Sin canal de línea; solo muestras y contorno.",
                                )
                            )
                    except Exception as failure:
                        messages.append(f"{name}: {failure}")
                elif error:
                    messages.append(f"{name}: {error}")
                else:
                    from .survey_map_dialog import choose_map_channels
                    from ..terraworkbench_core.survey_map import survey_map_channels

                    current = survey_map_channels(store, database_id)[0]
                    fields = [row["name"] for row in store.channels(database_id)]
                    channels = choose_map_channels(self, current, fields)
                    if channels is not None:
                        store.configure_geometry(
                            database_id,
                            channels.x,
                            channels.y,
                            channels.crs,
                            line=channels.line,
                        )
                        retry.append(
                            (name, lambda _store, canceled, value=database_id: value)
                        )
            if retry:
                self._start_gdb_survey_maps(
                    store.root.parent, retry, workspace=store.root
                )
            if messages:
                from qgis.utils import iface

                if iface is not None:
                    iface.messageBar().pushWarning(
                        "TerraWorkbench", " | ".join(messages)
                    )

        def fail(message):
            if not getattr(self, "_tw_disposing", False):
                QMessageBox.warning(self, "TerraWorkbench", message)

        worker.completed.connect(complete)
        worker.failed.connect(fail)
        worker.progress.connect(progress.setLabelText)
        progress.canceled.connect(worker.requestInterruption)
        worker.finished.connect(progress.close)
        worker.finished.connect(progress.deleteLater)
        worker.finished.connect(worker.deleteLater)
        progress.show()
        worker.start()

    def _load_geosoft_outputs(self, source, output, temporary_root=None):
        self._last_geosoft_point_layer = None
        self._geosoft_survey_map_started = False
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
                f"{Path(source).stem} — {suffix} — Geosoft GeoDatabase",
                "delimitedtext",
            )
            if layer.isValid():
                self._mark_geosoft_source(layer, source, manifest)
                if temporary_root is not None:
                    self._mark_import(layer, temporary_root)
                QgsProject.instance().addMapLayer(layer)
                loaded += 1
        csv_path = manifest.get("csv")
        if csv_path and Path(csv_path).is_file():
            from ..qgis_plugin.survey_map_import import import_geosoft_observations

            name = Path(source).stem

            def import_data(store, canceled):
                return import_geosoft_observations(
                    store, csv_path, name, manifest, canceled
                )

            self._start_gdb_survey_maps(
                QgsApplication.qgisSettingsDirPath(), [(name, import_data)]
            )
            self._geosoft_survey_map_started = True
        return loaded

    def _offer_survey_gridding(self, point_layer):
        answer = QMessageBox.question(
            self,
            text("Create analysis grid", "Crear grilla de análisis"),
            text(
                "The GeoDatabase points are now open QGIS data. Open the gridding tool to select a channel and create a GeoTIFF for RTP/RTE and the Filter Stack?",
                "Los puntos de GeoDatabase ya son datos abiertos de QGIS. ¿Abrir la herramienta de interpolación para elegir un canal y crear un GeoTIFF para RTP/RTE y la pila de filtros?",
            ),
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
    def _mark_geosoft_source(layer, source, manifest):
        layer.setCustomProperty(
            "TerraWorkbench/sourceFormat",
            manifest.get("source_format", "Geosoft GeoDatabase"),
        )
        layer.setCustomProperty("TerraWorkbench/sourceFile", str(source))
        layer.setCustomProperty(
            "TerraWorkbench/conversionEngine",
            manifest.get("conversion_engine", "Geosoft runtime"),
        )
        metadata = layer.metadata()
        metadata.setTitle(layer.name())
        metadata.setAbstract(
            "Imported from a Geosoft GeoDatabase and converted to open CSV by "
            "TerraWorkbench. The exported layer is standard QGIS data."
        )
        metadata.addHistoryItem(f"Source: Geosoft GeoDatabase: {Path(source).name}")
        layer.setMetadata(metadata)

    def import_filegdb(self, source=None):
        if not source:
            source = QFileDialog.getExistingDirectory(
                self, text("Choose Esri FileGDB folder", "Elegir carpeta Esri FileGDB")
            )
        if not source:
            return
        if Path(source).suffix.lower() != ".gdb":
            QMessageBox.warning(
                self,
                "TerraWorkbench",
                text(
                    "Choose a folder ending in .gdb.",
                    "Elija una carpeta que termine en .gdb.",
                ),
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
        from functools import partial
        from qgis.core import QgsWkbTypes
        from ..qgis_plugin.survey_map_import import import_filegdb_points

        jobs = []
        loaded = 0
        for name in names:
            layer = QgsVectorLayer(f"{source}|layername={name}", name, "ogr")
            if not layer.isValid():
                continue
            point = QgsWkbTypes.flatType(layer.wkbType()) == qt_enum(
                QgsWkbTypes, "Type", "Point"
            )
            if point:
                survey_name = f"{Path(source).stem} — {name}"
                jobs.append(
                    (
                        survey_name,
                        partial(
                            import_filegdb_points,
                            source=source,
                            layer_name=name,
                            name=survey_name,
                        ),
                    )
                )
            else:
                QgsProject.instance().addMapLayer(layer)
            loaded += 1
        if jobs:
            self._start_gdb_survey_maps(Path(source).parent, jobs)
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

    def _import_error(self, error):
        QMessageBox.critical(
            self, "TerraWorkbench",
            text("Import failed:\n{error}", "Falló la importación:\n{error}").format(error=error),
        )

    @staticmethod
    def _mark_import(layer, root=None):
        mark_temporary_import(layer, text("temporary", "temporal"), root)

    def _import_destination(self, source, destination=None):
        directory = destination or self._active_work_directory()
        temporary_root = temporary_import_root() if directory is None else None
        return new_import_directory(source, directory or temporary_root), temporary_root

    def _update_import_actions(self):
        layer = self._selected_raster()
        self.save_import_action.setText(
            text("Save in work folder", "Guardar en la carpeta de trabajo")
            if import_working_directory() else text("Save as…", "Guardar como…")
        )
        self.save_import_action.setEnabled(layer is not None and is_temporary_import(layer))
        self.hillshade.refresh()

    def _work_project_changed(self, *_args):
        self._ignored_temporary_imports.clear()
        self._warned_work_directories.clear()
        self.refresh_work_directory()

    def _active_work_directory(self):
        from qgis import utils

        configured = project_work_directory()
        active = import_working_directory()
        if (configured is not None and active is None
                and configured not in self._warned_work_directories and utils.iface is not None):
            self._warned_work_directories.add(configured)
            utils.iface.messageBar().pushWarning("TerraWorkbench", text(
                "Work folder unavailable: {path}. Using QGIS temporary storage.",
                "Carpeta de trabajo no disponible: {path}. Se usa la carpeta temporal de QGIS.",
            ).format(path=configured))
        return active

    def refresh_work_directory(self):
        active = self._active_work_directory()
        button = self.work_directory_button
        label = text("Work folder", "Carpeta de trabajo")
        if active is None:
            value = text("Temporary (QGIS)", "Temporal (QGIS)")
            button.setToolTip(str(temporary_import_root()))
        else:
            value = button.fontMetrics().elidedText(
                active.name or str(active), qt_enum(Qt, "TextElideMode", "ElideMiddle"), 160
            )
            button.setToolTip(str(active))
        button.setText(f"{label}: {value}")
        self._layout_quick_tools()
        self._update_import_actions()

    def _populate_work_directory_menu(self):
        self.refresh_work_directory()
        menu = self.work_directory_menu
        menu.clear()
        menu.addAction(text("Choose folder…", "Elegir carpeta…"), self._choose_work_directory)
        recents = recent_work_directories()
        if recents:
            menu.addSeparator()
            for directory in recents:
                path = Path(directory)
                label = path.name or str(path)
                action = menu.addAction(label.replace("&", "&&"))
                action.setToolTip(str(path))
                action.setEnabled(path.is_dir())
                action.triggered.connect(lambda _checked=False, path=path: self._set_work_directory(path))
        menu.addSeparator()
        menu.addAction(
            text("Open folder in file explorer", "Abrir carpeta en el explorador"),
            self._open_work_directory,
        )
        menu.addAction(
            text("Use QGIS temporary folder", "Usar temporal de QGIS"),
            lambda: self._set_work_directory(None),
        )

    def _choose_work_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self, text("Choose folder…", "Elegir carpeta…"),
            str(import_working_directory() or QgsProject.instance().homePath()),
        )
        if directory:
            self._set_work_directory(directory)

    def _set_work_directory(self, directory):
        write_project_work_directory(QgsProject.instance(), directory)
        if directory is not None:
            remember_work_directory(directory)
        self.refresh_work_directory()

    def _open_work_directory(self):
        directory = self._active_work_directory()
        if directory is None:
            directory = temporary_import_root()
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                self._import_error(error)
                return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def _finish_import(self, source, subdataset=None):
        path = Path(source)
        QApplication.setOverrideCursor(qt_enum(Qt, "CursorShape", "WaitCursor"))
        try:
            native = subdataset is None and path.is_file() and path.suffix.casefold() in {".tif", ".tiff"}
            if native:
                imported = str(path)
            else:
                batch, temporary_root = self._import_destination(path)
                destination = batch / f"{path.stem}.tif"
                imported, _metadata = import_survey_grid(source, destination, subdataset=subdataset)
            layer = QgsRasterLayer(imported, path.stem)
            if not layer.isValid():
                raise QgsProcessingException("The imported GeoTIFF is not a valid QGIS raster.")
            if not native and temporary_root is not None:
                self._mark_import(layer, temporary_root)
            QgsProject.instance().addMapLayer(layer)
            self.refresh_layers()
            self.layer_combo.setCurrentIndex(self.layer_combo.findData(layer.id()))
            return layer
        except (OSError, ValueError, QgsProcessingException) as error:
            self._import_error(error)
        finally:
            QApplication.restoreOverrideCursor()

    def save_imported_grid(self):
        layer = self._selected_raster()
        if layer is None or not is_temporary_import(layer):
            return
        source = import_layer_path(layer)
        try:
            directory = self._active_work_directory()
            if directory is not None:
                path = new_import_directory(source, directory) / source.name
            else:
                project = QgsProject.instance()
                suggested = Path(project.homePath() or Path.home()) / source.name
                destination, _ = QFileDialog.getSaveFileName(
                    self, text("Save as…", "Guardar como…"), str(suggested), "GeoTIFF (*.tif *.tiff)"
                )
                if not destination:
                    return
                path = Path(destination)
                if path.suffix.casefold() not in {".tif", ".tiff"}:
                    path = path.with_suffix(".tif")
            copy_imported_raster(layer, path)
            self.refresh_layers()
            self.layer_combo.setCurrentIndex(self.layer_combo.findData(layer.id()))
        except (OSError, ValueError) as error:
            self._import_error(error)

    def warn_temporary_imports(self, document):
        project = QgsProject.instance()
        configured = project_work_directory(project)
        if configured is not None and configured.is_absolute():
            write_project_work_directory(project, configured)
        layers = [layer for layer in project.mapLayers().values()
                  if layer.id() not in self._ignored_temporary_imports and is_temporary_import(layer)]
        if not layers:
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle(text("Temporary survey imports", "Importaciones temporales de levantamientos"))
        dialog.setText(text(
            "{count} imported layer(s) will be lost when QGIS closes unless saved.",
            "{count} capa(s) importada(s) se perderán al cerrar QGIS si no se guardan.",
        ).format(count=len(layers)))
        move_label = text("Choose work folder and move…", "Elegir carpeta de trabajo y mover…")
        save = dialog.addButton(move_label,
                                qt_enum(QMessageBox, "ButtonRole", "AcceptRole"))
        ignore = dialog.addButton(text("Ignore", "Ignorar"),
                                  qt_enum(QMessageBox, "ButtonRole", "RejectRole"))
        dialog.setDefaultButton(save)
        dialog.setEscapeButton(ignore)
        dialog.exec()
        clicked = dialog.clickedButton()
        dialog.deleteLater()
        if clicked == ignore:
            self._ignored_temporary_imports.update(layer.id() for layer in layers)
            return
        if clicked != save:
            return
        destination = QFileDialog.getExistingDirectory(
            self, move_label, str(import_working_directory(project) or project.homePath())
        )
        if not destination:
            return
        try:
            save_temporary_imports(layers, destination)
            self._set_work_directory(destination)
        except (OSError, ValueError) as error:
            self._import_error(error)
        # QGIS emits writeProject after cloning the tree but before writing the layers.
        persisted = {layer.id(): layer for layer in layers if not is_temporary_import(layer)}
        nodes = document.elementsByTagName("layer-tree-layer")
        for index in range(nodes.count()):
            node = nodes.item(index).toElement()
            if layer := persisted.get(node.attribute("id")):
                node.setAttribute("name", layer.name())
                node.setAttribute("source", layer.source())
        self.refresh_layers()

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
            self,
            text("Choose output folder", "Elegir carpeta de salida"),
            self.output_directory.text(),
        )
        if directory:
            self.output_directory.setText(directory)

    def save_stack(self):
        if not self.update_current_parameters():
            QMessageBox.warning(
                self,
                "TerraWorkbench",
                text(
                    "Correct the highlighted parameter values.",
                    "Corrija los valores de parámetros resaltados.",
                ),
            )
            return
        if not self.steps():
            QMessageBox.warning(
                self,
                "TerraWorkbench",
                text("The filter stack is empty.", "La pila de filtros está vacía."),
            )
            return
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            text("Save filter stack", "Guardar pila de filtros"),
            "terraworkbench-stack.json",
            "JSON (*.json)",
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
            self,
            text("Load filter stack", "Cargar pila de filtros"),
            "",
            "JSON (*.json)",
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
                self,
                "TerraWorkbench",
                text(
                    "Could not load stack:\n{error}",
                    "No se pudo cargar la pila:\n{error}",
                ).format(error=error),
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
                self,
                "TerraWorkbench",
                text(
                    "Correct the highlighted parameter values.",
                    "Corrija los valores de parámetros resaltados.",
                ),
            )
            return
        layer = self._selected_raster()
        if layer is None:
            QMessageBox.warning(
                self,
                "TerraWorkbench",
                text(
                    "Choose a valid input raster layer.",
                    "Elija una capa ráster de entrada válida.",
                ),
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

            from ..algorithms.spectral_filters import SpectralFilterBase

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
                self,
                "TerraWorkbench",
                text(
                    "Spectrum preview failed:\n{error}",
                    "Falló la vista previa del espectro:\n{error}",
                ).format(error=error),
            )
            return
        finally:
            QApplication.restoreOverrideCursor()

        dialog = SpectrumDialog(frequencies, original_power, filtered_power, note, self)
        execute = getattr(dialog, "exec", None) or dialog.exec_
        execute()

    def review_stages(self):
        if self.last_stages:
            from .raster_stage_review import RasterStageReview

            dialog = RasterStageReview(self.last_stages, self)
            dialog.exec()
            dialog.deleteLater()

    def run_stack(self):
        if not self.update_current_parameters():
            QMessageBox.warning(
                self,
                "TerraWorkbench",
                text(
                    "Correct the highlighted parameter values.",
                    "Corrija los valores de parámetros resaltados.",
                ),
            )
            return
        layer = self._selected_raster()
        if layer is None:
            QMessageBox.warning(
                self,
                "TerraWorkbench",
                text(
                    "Choose a valid input raster layer.",
                    "Elija una capa ráster de entrada válida.",
                ),
            )
            return
        steps = self.steps()
        if not steps:
            QMessageBox.warning(
                self,
                "TerraWorkbench",
                text("Add at least one filter.", "Añada al menos un filtro."),
            )
            return

        output_directory = self.output_directory.text().strip() or None
        progress = QProgressDialog(
            text("Running filter stack…", "Ejecutando pila de filtros…"),
            text("Cancel", "Cancelar"),
            0,
            100,
            self,
        )
        progress.setWindowModality(qt_enum(Qt, "WindowModality", "WindowModal"))
        progress.setMinimumDuration(0)
        feedback = QgsProcessingFeedback()
        feedback.progressChanged.connect(lambda value: progress.setValue(int(value)))
        progress.canceled.connect(feedback.cancel)
        progress.show()
        QApplication.setOverrideCursor(qt_enum(Qt, "CursorShape", "WaitCursor"))
        try:
            if output_directory:
                run_folder = Path(output_directory) / ("run_" + uuid.uuid4().hex)
                run_folder.mkdir(parents=True, exist_ok=False)
                output_directory = str(run_folder)
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
            self.last_stages = [
                {
                    "label": "Input · " + layer.name(),
                    "path": layer.source(),
                    "band": self.band_spin.value(),
                }
            ] + [
                {
                    "label": f"{index + 1} · {step.algorithm_id}",
                    "path": str(path),
                    "band": 1,
                    "algorithm": step.algorithm_id,
                    "parameters": dict(step.parameters),
                }
                for index, (step, path) in enumerate(zip(steps, outputs))
            ]
            self.review_stages_button.setEnabled(True)
            source_identity = {
                "source": layer.source(),
                "band": self.band_spin.value(),
                "crs": layer.crs().toWkt(),
                "identity_scope": "file metadata only; not a content hash",
            }
            source_path = Path(layer.source().split("|", 1)[0])
            if source_path.is_file():
                state = source_path.stat()
                source_identity.update(size=state.st_size, mtime_ns=state.st_mtime_ns)
            implementations = {}
            for step in steps:
                algorithm = self._algorithm(step.algorithm_id)
                module_path = inspect.getsourcefile(type(algorithm))
                implementations[step.algorithm_id] = {
                    "module": type(algorithm).__module__,
                    "module_sha256": hashlib.sha256(
                        Path(module_path).read_bytes()
                    ).hexdigest()
                    if module_path
                    else None,
                    "hash_scope": "algorithm module only, not transitive dependencies",
                }
            manifest = {
                "format": PIPELINE_FORMAT_VERSION,
                "steps": [step.to_dict() for step in steps],
                "source": source_identity,
                "stages": self.last_stages,
                "implementations": implementations,
                "finished_utc": datetime.now(timezone.utc).isoformat(),
                "host": "QGIS",
                "scope": "execution recipe; source data are not snapshotted",
            }
            recipe_path = Path(final_output).parent / (
                "recipe_" + uuid.uuid4().hex + ".json"
            )
            recipe_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self.last_recipe = str(recipe_path)
            self.review_stages_button.setToolTip(self.last_recipe)
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
        except (OSError, ValueError, TypeError, QgsProcessingException) as error:
            QMessageBox.critical(
                self,
                "TerraWorkbench",
                text(
                    "Filter stack failed:\n{error}",
                    "Falló la pila de filtros:\n{error}",
                ).format(error=error),
            )
        finally:
            QApplication.restoreOverrideCursor()
            progress.close()
