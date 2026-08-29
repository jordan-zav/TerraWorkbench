"""Persistent TerraWorkbench preferences and developer information."""

from pathlib import Path

from qgis.PyQt.QtCore import QLocale, QSettings, QUrl, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .embedded_qpip import dependency_directory
from .i18n import language, set_language, text
from .metadata_utils import plugin_metadata, plugin_version
from .qgis_compat import qt_enum


KEY_OUTPUT = "TerraWorkbench/defaultOutputDirectory"
KEY_KEEP = "TerraWorkbench/keepIntermediate"
KEY_BAND = "TerraWorkbench/defaultBand"
KEY_INSPECTOR = "TerraWorkbench/openInspectorAfterAdd"
KEY_CONFIRM_CLEAR = "TerraWorkbench/confirmClearStack"
KEY_ADD_RESULT = "TerraWorkbench/addFinalResultToProject"
KEY_TOOLTIPS = "TerraWorkbench/showScientificTooltips"
KEY_GEOb = "TerraWorkbench/geosoftLocation"
KEY_LOCAL_DATA = "TerraWorkbench/localTestDataDirectory"


class SettingsDialog(QDialog):
    """Detailed settings surface for the plugin-owned workflow."""

    preferencesChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TerraWorkbenchSettings")
        self.setMinimumSize(580, 500)
        self.resize(660, 580)
        self._settings = QSettings()

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs, 1)
        self._build_general_tab()
        self._build_processing_tab()
        self._build_integrations_tab()
        self._build_about_tab()

        self.buttons = QDialogButtonBox(
            qt_enum(QDialogButtonBox, "StandardButton", "Save")
            | qt_enum(QDialogButtonBox, "StandardButton", "Cancel")
            | qt_enum(QDialogButtonBox, "StandardButton", "RestoreDefaults"),
            parent=self,
        )
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        restore = self.buttons.button(
            qt_enum(QDialogButtonBox, "StandardButton", "RestoreDefaults")
        )
        restore.clicked.connect(self.restore_defaults)
        layout.addWidget(self.buttons)
        self.load()
        self.retranslate()

    def _build_general_tab(self):
        self.general_tab = QWidget()
        form = QFormLayout(self.general_tab)
        self.language_combo = QComboBox()
        self.language_combo.addItem("Español", "es")
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("Português", "pt")
        form.addRow("Language", self.language_combo)
        self.open_inspector = QCheckBox()
        form.addRow(self.open_inspector)
        self.confirm_clear = QCheckBox()
        form.addRow(self.confirm_clear)
        self.scientific_tooltips = QCheckBox()
        form.addRow(self.scientific_tooltips)
        self.language_note = QLabel()
        form.addRow(self.language_note)
        self.tabs.addTab(self.general_tab, "General")

    def _build_processing_tab(self):
        self.processing_tab = QWidget()
        layout = QVBoxLayout(self.processing_tab)
        output_group = QGroupBox()
        output_form = QFormLayout(output_group)
        output_row = QHBoxLayout()
        self.output_directory = QLineEdit()
        self.output_browse = QPushButton()
        self.output_browse.clicked.connect(self.choose_output_directory)
        output_row.addWidget(self.output_directory, 1)
        output_row.addWidget(self.output_browse)
        self.output_label = QLabel()
        output_form.addRow(self.output_label, output_row)
        self.default_band = QSpinBox()
        self.default_band.setRange(1, 9999)
        self.band_label = QLabel()
        output_form.addRow(self.band_label, self.default_band)
        self.keep_intermediate = QCheckBox()
        output_form.addRow(self.keep_intermediate)
        self.add_final_result = QCheckBox()
        output_form.addRow(self.add_final_result)
        layout.addWidget(output_group)
        note = QLabel()
        note.setObjectName("processingNote")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        self.output_group = output_group
        self.processing_note = note
        self.tabs.addTab(self.processing_tab, "Processing")

    def _build_integrations_tab(self):
        self.integrations_tab = QWidget()
        layout = QVBoxLayout(self.integrations_tab)
        geosoft_group = QGroupBox()
        geosoft_layout = QVBoxLayout(geosoft_group)
        self.geosoft_note = QLabel()
        self.geosoft_note.setWordWrap(True)
        geosoft_layout.addWidget(self.geosoft_note)
        geosoft_row = QHBoxLayout()
        self.geosoft_location = QLineEdit()
        self.geosoft_browse = QPushButton()
        self.geosoft_browse.clicked.connect(self.choose_geosoft_directory)
        geosoft_row.addWidget(self.geosoft_location, 1)
        geosoft_row.addWidget(self.geosoft_browse)
        geosoft_layout.addLayout(geosoft_row)
        layout.addWidget(geosoft_group)
        local_group = QGroupBox()
        local_layout = QVBoxLayout(local_group)
        self.local_data_note = QLabel()
        self.local_data_note.setWordWrap(True)
        local_layout.addWidget(self.local_data_note)
        local_row = QHBoxLayout()
        self.local_data_location = QLineEdit()
        self.local_data_browse = QPushButton()
        self.local_data_browse.clicked.connect(self.choose_local_data_directory)
        local_row.addWidget(self.local_data_location, 1)
        local_row.addWidget(self.local_data_browse)
        local_layout.addLayout(local_row)
        layout.addWidget(local_group)
        paths_group = QGroupBox()
        paths_layout = QVBoxLayout(paths_group)
        self.manage_dependencies = QPushButton()
        self.manage_dependencies.clicked.connect(self.open_dependency_manager)
        self.open_dependencies = QPushButton()
        self.open_dependencies.clicked.connect(
            lambda: self._open_path(dependency_directory())
        )
        self.open_samples = QPushButton()
        self.open_samples.clicked.connect(
            lambda: self._open_path(Path(__file__).parent / "sample_data" / "synthetic")
        )
        paths_layout.addWidget(self.manage_dependencies)
        paths_layout.addWidget(self.open_dependencies)
        paths_layout.addWidget(self.open_samples)
        layout.addWidget(paths_group)
        layout.addStretch(1)
        self.geosoft_group = geosoft_group
        self.local_data_group = local_group
        self.paths_group = paths_group
        self.tabs.addTab(self.integrations_tab, "Integrations")

    def _build_about_tab(self):
        self.about_tab = QWidget()
        layout = QVBoxLayout(self.about_tab)
        self.about_label = QLabel()
        self.about_label.setWordWrap(True)
        self.about_label.setOpenExternalLinks(True)
        self.about_label.setTextInteractionFlags(self.about_label.textInteractionFlags())
        layout.addWidget(self.about_label)
        layout.addStretch(1)
        self.tabs.addTab(self.about_tab, "About")

    @staticmethod
    def _open_path(path):
        Path(path).mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_dependency_manager(self):
        from .dependency_dialog import open_dependency_dialog

        open_dependency_dialog(self)

    def choose_output_directory(self):
        selected = QFileDialog.getExistingDirectory(
            self,
            text("Choose default output folder", "Elegir carpeta de salida predeterminada"),
            self.output_directory.text(),
        )
        if selected:
            self.output_directory.setText(selected)

    def choose_geosoft_directory(self):
        selected = QFileDialog.getExistingDirectory(
            self,
            text("Locate Geosoft or Oasis montaj", "Ubicar Geosoft u Oasis montaj"),
            self.geosoft_location.text() or r"C:\Program Files\Geosoft",
        )
        if selected:
            self.geosoft_location.setText(selected)

    def load(self):
        index = self.language_combo.findData(language())
        self.language_combo.setCurrentIndex(max(0, index))
        self.output_directory.setText(
            self._settings.value(KEY_OUTPUT, "", type=str)
        )
        self.keep_intermediate.setChecked(
            self._settings.value(KEY_KEEP, False, type=bool)
        )
        self.default_band.setValue(
            self._settings.value(KEY_BAND, 1, type=int)
        )
        self.open_inspector.setChecked(
            self._settings.value(KEY_INSPECTOR, True, type=bool)
        )
        self.confirm_clear.setChecked(
            self._settings.value(KEY_CONFIRM_CLEAR, True, type=bool)
        )
        self.add_final_result.setChecked(
            self._settings.value(KEY_ADD_RESULT, True, type=bool)
        )
        self.scientific_tooltips.setChecked(
            self._settings.value(KEY_TOOLTIPS, True, type=bool)
        )
        self.geosoft_location.setText(
            self._settings.value(KEY_GEOb, "", type=str)
        )
        self.local_data_location.setText(
            self._settings.value(KEY_LOCAL_DATA, "", type=str)
        )

    def restore_defaults(self):
        system_language = QLocale.system().name().casefold()
        default_language = (
            "es"
            if system_language.startswith("es")
            else "pt"
            if system_language.startswith("pt")
            else "en"
        )
        self.language_combo.setCurrentIndex(
            self.language_combo.findData(default_language)
        )
        self.output_directory.clear()
        self.keep_intermediate.setChecked(False)
        self.default_band.setValue(1)
        self.open_inspector.setChecked(True)
        self.confirm_clear.setChecked(True)
        self.add_final_result.setChecked(True)
        self.scientific_tooltips.setChecked(True)
        self.geosoft_location.clear()
        self.local_data_location.clear()

    def save(self):
        set_language(self.language_combo.currentData())
        self._settings.setValue(KEY_OUTPUT, self.output_directory.text().strip())
        self._settings.setValue(KEY_KEEP, self.keep_intermediate.isChecked())
        self._settings.setValue(KEY_BAND, self.default_band.value())
        self._settings.setValue(KEY_INSPECTOR, self.open_inspector.isChecked())
        self._settings.setValue(KEY_CONFIRM_CLEAR, self.confirm_clear.isChecked())
        self._settings.setValue(KEY_ADD_RESULT, self.add_final_result.isChecked())
        self._settings.setValue(KEY_TOOLTIPS, self.scientific_tooltips.isChecked())
        self._settings.setValue(KEY_GEOb, self.geosoft_location.text().strip())
        self._settings.setValue(
            KEY_LOCAL_DATA, self.local_data_location.text().strip()
        )
        self.preferencesChanged.emit()
        self.accept()

    def retranslate(self):
        self.setWindowTitle(text("TerraWorkbench — Settings", "TerraWorkbench — Configuración"))
        self.tabs.setTabText(0, text("General", "General"))
        self.tabs.setTabText(1, text("Processing", "Procesamiento"))
        self.tabs.setTabText(2, text("Integrations", "Integraciones"))
        self.tabs.setTabText(3, text("About", "Acerca de"))
        form = self.general_tab.layout()
        form.labelForField(self.language_combo).setText(text("Language", "Idioma"))
        self.open_inspector.setText(text("Open parameter inspector after adding a filter", "Abrir el inspector de parámetros al añadir un filtro"))
        self.confirm_clear.setText(text("Confirm before clearing the complete stack", "Confirmar antes de borrar toda la pila"))
        self.scientific_tooltips.setText(text("Show scientific tooltips and domain labels", "Mostrar ayudas científicas y etiquetas de dominio"))
        self.language_note.setText(
            text(
                "Language changes apply to TerraWorkbench only.",
                "Los cambios de idioma se aplican solo a TerraWorkbench.",
            )
        )
        self.output_group.setTitle(text("Defaults for new workflows", "Valores para flujos nuevos"))
        self.output_label.setText(text("Output folder", "Carpeta de salida"))
        self.band_label.setText(text("Input band", "Banda de entrada"))
        self.output_browse.setText(text("Browse…", "Examinar…"))
        self.keep_intermediate.setText(text("Keep intermediate rasters when an output folder is used", "Conservar rásteres intermedios al usar una carpeta de salida"))
        self.add_final_result.setText(text("Add the final result to the QGIS project", "Añadir el resultado final al proyecto QGIS"))
        self.processing_note.setText(text("Scientific parameters remain explicit in every filter. These preferences control workflow behavior, not geophysical assumptions.", "Los parámetros científicos permanecen explícitos en cada filtro. Estas preferencias controlan el flujo, no los supuestos geofísicos."))
        self.geosoft_group.setTitle(text("Geosoft GeoDatabase reader", "Lector de GeoDatabase Geosoft"))
        self.geosoft_note.setText(text("TerraWorkbench first uses the standalone BSD GX Developer runtime installed by its dependency manager. Oasis montaj is not required. An installed Oasis runtime is retained only as an optional fallback.", "TerraWorkbench usa primero el runtime autónomo BSD de GX Developer instalado por su gestor de dependencias. Oasis montaj no es necesario. Una instalación de Oasis se conserva únicamente como respaldo opcional."))
        self.geosoft_browse.setText(text("Locate…", "Ubicar…"))
        self.local_data_group.setTitle(
            text("Local test datasets", "Datos locales de prueba")
        )
        self.local_data_note.setText(
            text(
                "Choose a private Raw/test folder containing GeoTIFF, GRD, GXF, ASCII, CSV or .gdb data. Files remain outside the plugin and are never added to its ZIP.",
                "Elija una carpeta privada Raw/de prueba con datos GeoTIFF, GRD, GXF, ASCII, CSV o .gdb. Los archivos permanecen fuera del complemento y nunca se añaden a su ZIP.",
            )
        )
        self.local_data_browse.setText(text("Locate…", "Ubicar…"))
        self.paths_group.setTitle(text("Plugin data", "Datos del complemento"))
        self.manage_dependencies.setText(text("Manage Python dependencies…", "Administrar dependencias de Python…"))
        self.open_dependencies.setText(text("Open dependency folder", "Abrir carpeta de dependencias"))
        self.open_samples.setText(text("Open bundled sample-data folder", "Abrir carpeta de datos de ejemplo"))
        metadata = plugin_metadata()
        self.about_label.setText(
            "<h2>TerraWorkbench</h2>"
            f"<p><b>{text('Version', 'Versión')}:</b> {plugin_version()}</p>"
            "<p><b>Jordan Zavaleta (GisGeo Dev)</b><br>"
            '<a href="mailto:jordanzav@gisgeo.dev">jordanzav@gisgeo.dev</a></p>'
            f"<p>{text('Open-source QGIS plugin for magnetic, gravity, spectral, survey-preparation and 3D inversion workflows.', 'Complemento QGIS de código abierto para flujos magnéticos, gravimétricos, espectrales, preparación de levantamientos e inversión 3D.')}</p>"
            f'<p><a href="{metadata.get("repository")}">{text("Source repository", "Repositorio del código")}</a><br>'
            f'<a href="{metadata.get("tracker")}">{text("Report an issue", "Reportar un problema")}</a></p>'
            "<p>GPL-3.0-or-later</p>"
        )

    def choose_local_data_directory(self):
        selected = QFileDialog.getExistingDirectory(
            self,
            text("Choose local test-data folder", "Elegir carpeta local de datos de prueba"),
            self.local_data_location.text(),
        )
        if selected:
            self.local_data_location.setText(selected)
