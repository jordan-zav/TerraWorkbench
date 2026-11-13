"""Follow the real QGIS locale and retain explicit overrides in isolated settings."""

import os

from qgis.core import QgsApplication, QgsSettings

from TerraWorkbench.ui.i18n import language, language_preference, set_language
from TerraWorkbench.ui.workflow_dock import FilterStackDock


def main():
    QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication([], False)
    app.initQgis()
    settings = QgsSettings()
    settings.setValue("locale/overrideFlag", True)
    set_language("auto")
    dock = FilterStackDock()
    try:
        for locale, expected, label in (
            ("es_PE", "es", "Bases de datos…"),
            ("pt_BR", "pt", "Bancos de dados…"),
            ("en_US", "en", "Databases…"),
            ("fr_FR", "en", "Databases…"),
        ):
            settings.setValue("locale/userLocale", locale)
            assert QgsApplication.locale().split("_")[0] == locale.split("_")[0]
            assert language() == expected, (locale, language())
            dock.retranslate()
            assert dock.workspace_button.text() == label
            assert language_preference() == "auto"
        set_language("pt")
        settings.setValue("locale/userLocale", "es_PE")
        assert language() == "pt"
        set_language("auto")
        assert language() == "es"
        print("PASS: real QGIS locale es/pt/en, unsupported fallback, explicit override and automatic restore")
    finally:
        dock.disconnect_project()
        dock.close()
        app.exitQgis()


if __name__ == "__main__":
    main()
