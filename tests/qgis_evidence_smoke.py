"""Real offscreen evidence API, without desktop input or user settings."""

import inspect
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from qgis.PyQt.QtCore import QSettings, QCoreApplication
from qgis.PyQt.QtWidgets import QApplication, QLabel

from TerraWorkbench.ui.evidence_api import capture_widget, capture_workspace
from TerraWorkbench.ui.core_parameter_form import CoreParameterForm
from TerraWorkbench.ui.i18n import set_language
from TerraWorkbench.terraworkbench_core.survey_store import SurveyStore
from TerraWorkbench.terraworkbench_core.inversion import run_potential_field_inversion


def main():
    # mkdtemp preserves screenshots for debugging. The caller controls TEMP.
    folder = Path(tempfile.mkdtemp(prefix="tw_evidence_"))
    assert os.environ.get("QT_QPA_PLATFORM") == "offscreen"
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(folder / "settings"))
    QCoreApplication.setOrganizationName("TerraWorkbenchEvidenceTest")
    QCoreApplication.setApplicationName("Offscreen")
    app = QApplication([])
    assert app.platformName() == "offscreen"
    source = folder / "source.csv"
    source.write_text("x,y,value,role\n1,2,5,1\n2,3,6,2\n3,4,7,0\n")
    store = SurveyStore(folder / "workspace", create=True)
    database = store.import_file(source)
    set_language("es")
    capture_workspace(store.root, database, ["value", "role"], folder / "database.png",
                      filter_channel="role", filter_values=["1", "2"])
    widget = QLabel("Actual widget evidence")
    capture_widget(widget, folder / "widget.png")
    try:
        capture_widget(widget, folder / "widget.png")
    except FileExistsError:
        pass
    else:
        raise AssertionError("Evidence must never overwrite an earlier capture")
    params = dict(cell_xy=150., cell_z=100., depth=1200., padding=3, iterations=60,
                  field_amplitude=57000., field_inclination=74., field_declination=21.)
    api = inspect.signature(run_potential_field_inversion)
    signature = inspect.Signature([api.parameters[key] for key in params])
    for locale in ("es", "en", "pt"):
        set_language(locale)
        form = CoreParameterForm(signature)
        form.set_parameters(params)
        assert form.parameters() == params
        capture_widget(form, folder / f"parameters_{locale}.png", height=1000)
        form.close()
    widget.close()
    assert len(list(folder.glob("*.png"))) == 5
    print("PASS offscreen evidence, real workspace filters, overwrite guard and EN/ES/PT parameters", folder)


if __name__ == "__main__":
    main()
