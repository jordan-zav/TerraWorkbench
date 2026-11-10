"""Read-only workspace and manual captures using QGIS Python offscreen.

The caller supplies an existing workspace, new PNG paths and an isolated new
profile. This uses no desktop input. Captures do not execute an inversion.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace")
    parser.add_argument("--synthetic", action="store_true",
                        help="Import bundled CC0 points and capture both widgets to a new folder")
    parser.add_argument("--database-id")
    parser.add_argument("--output", required=True)
    parser.add_argument("--profile-dir", required=True)
    parser.add_argument("--language", choices=("es", "en", "pt"), default="es")
    parser.add_argument(
        "--channels",
        nargs="+",
        default=["line", "field_nt", "corrected_nt", "tutorial_selected"],
    )
    parser.add_argument("--filter-channel")
    parser.add_argument("--filter-values", nargs="*", default=[])
    parser.add_argument("--dataset-label", default="TerraWorkbench")
    parser.add_argument("--catalog-dir")
    parser.add_argument("--manual-output")
    args = parser.parse_args()
    profile = Path(args.profile_dir).resolve()
    profile.mkdir(parents=True, exist_ok=False)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QGIS_CUSTOM_CONFIG_PATH"] = str(profile)
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    # A checkout/worktree may have any folder name; bind the QGIS package explicitly.
    if "TerraWorkbench" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "TerraWorkbench", root / "__init__.py", submodule_search_locations=[str(root)]
        )
        package = importlib.util.module_from_spec(spec)
        sys.modules["TerraWorkbench"] = package
        spec.loader.exec_module(package)
    from qgis.core import QgsApplication, Qgis
    from qgis.PyQt.QtCore import QSettings, QCoreApplication
    from qgis.PyQt.QtGui import QFont, QFontDatabase
    from TerraWorkbench.ui.evidence_api import capture_workspace, capture_widget
    from TerraWorkbench.ui.full_manual import FullManualWidget
    from TerraWorkbench.ui.i18n import set_language
    from TerraWorkbench.terraworkbench_core.survey_store import SurveyStore
    from TerraWorkbench.qgis_plugin.provider import TerraWorkbenchProvider

    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(
        QSettings.IniFormat, QSettings.UserScope, str(profile / "settings")
    )
    QCoreApplication.setOrganizationName("TerraWorkbenchDocumentation")
    QCoreApplication.setApplicationName("IsolatedEvidence")
    QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication([], False, str(profile))
    app.initQgis()
    if os.name == "nt":
        QFontDatabase.addApplicationFont(
            str(Path(os.environ["WINDIR"]) / "Fonts/arial.ttf")
        )
    app.setFont(QFont("Arial", 10))
    set_language(args.language)
    if args.synthetic:
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=False)
        source = root / "sample_data/synthetic/synthetic_survey_points.csv"
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        from TerraWorkbench.terraworkbench_core.survey_text_import import inspect_text

        options, _, _ = inspect_text(source)
        store = SurveyStore(output / "workspace", create=True)
        identifier = store.import_file(source, "Synthetic CC0 survey", text_options=options)
        store.configure_geometry(identifier, "easting", "northing", "EPSG:32718")
        args.workspace = str(store.root)
        args.database_id = identifier
        args.channels = ["line_id", "magnetic_nt", "gravity_mgal", "height_m"]
        args.dataset_label = "TerraWorkbench / Synthetic CC0 survey"
        args.output = str(output / "workspace_canada.png")
        args.manual_output = str(output / "manual_completo.png")
        assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    elif not args.workspace:
        parser.error("Supply --workspace or --synthetic")
    store = SurveyStore(args.workspace)
    database = next(
        (
            d
            for d in store.databases()
            if args.database_id is None or d["id"] == args.database_id
        ),
        None,
    )
    if database is None:
        raise ValueError("Database not found")
    capture_workspace(
        store.root,
        database["id"],
        args.channels,
        args.output,
        filter_channel=args.filter_channel,
        filter_values=args.filter_values,
        workspace_label=args.dataset_label,
    )
    if args.manual_output:
        viewer = FullManualWidget()
        viewer.retranslate(args.language)
        viewer.set_chapter_id("01")
        assert viewer.chapter_combo.count() == 28
        capture_widget(viewer, args.manual_output, width=1280, height=1000)
        viewer.close()
    provider = TerraWorkbenchProvider()
    if not app.processingRegistry().addProvider(provider):
        raise RuntimeError("Could not register the actual provider")
    catalog = [
        {
            "id": algorithm.id(),
            "name": algorithm.displayName(),
            "group": algorithm.group(),
            "parameters": [p.name() for p in algorithm.parameterDefinitions()],
        }
        for algorithm in sorted(provider.algorithms(), key=lambda item: item.id())
    ]
    if args.catalog_dir:
        target = Path(args.catalog_dir)
        target.mkdir(parents=True, exist_ok=True)
        record = {
            "qgis_version": Qgis.QGIS_VERSION,
            "locale": args.language,
            "scope": "Actual provider inventory, not numerical or field validation",
            "algorithms": catalog,
        }
        (target / ("qgis_" + args.language + ".json")).write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if args.language == "en":
            (target / "qgis.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        labels = {
            "es": (
                "Catálogo real del proveedor QGIS",
                "Índice",
                "Nombre visible",
                "Parámetros",
                "Los IDs y parámetros son identificadores técnicos. Abrir un formulario no ejecuta ni valida un cálculo.",
            ),
            "en": (
                "Actual QGIS provider catalogue",
                "Contents",
                "Display name",
                "Parameters",
                "IDs and parameters are technical identifiers. Opening a form does not execute or validate a calculation.",
            ),
            "pt": (
                "Catálogo real do provedor QGIS",
                "Índice",
                "Nome visível",
                "Parâmetros",
                "IDs e parâmetros são identificadores técnicos. Abrir formulário não executa nem valida um cálculo.",
            ),
        }[args.language]
        lines = [
            "# " + labels[0],
            "",
            "[English](qgis_en.md) · [Español](qgis_es.md) · [Português](qgis_pt.md)",
            "",
            f"[{labels[1]}](../../manuals/{args.language}/README.md)",
            "",
            "QGIS "
            + Qgis.QGIS_VERSION
            + " · "
            + str(len(catalog))
            + " · "
            + args.language,
            "",
            labels[4],
            "",
            "| ID | " + labels[2] + " | " + labels[3] + " |",
            "| --- | --- | --- |",
        ]
        lines += [
            "| "
            + item["id"]
            + " | "
            + item["name"].replace("|", "/")
            + " | "
            + ", ".join(item["parameters"])
            + " |"
            for item in catalog
        ]
        (target / ("qgis_" + args.language + ".md")).write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
    print(
        json.dumps(
            {
                "platform": app.platformName(),
                "rows": database["rows"],
                "language": args.language,
                "algorithms": len(catalog),
                "manual_chapters": 28 if args.manual_output else None,
            }
        )
    )
    # The isolated process owns providers and widgets through normal exit.


if __name__ == "__main__":
    main()
