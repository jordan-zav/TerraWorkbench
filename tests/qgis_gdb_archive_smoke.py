"""Open verified synthetic GDB archives and survey layers with GX blocked."""

import importlib.abc
import os
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np
from qgis.core import QgsApplication, QgsProject

from TerraWorkbench.qgis_plugin.survey_map_layers import add_survey_map
from TerraWorkbench.terraworkbench_core.gdb_archive import convert_database, open_archive
from TerraWorkbench.terraworkbench_core.survey_store import SurveyStore
from TerraWorkbench.ui.survey_workspace_dialog import SurveyWorkspaceDialog
from TerraWorkbench.ui.workflow_dock import FilterStackDock


class NoGeosoft(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"geosoft", "gxpy", "gxapi"}:
            raise AssertionError("Open archives must not load Geosoft: " + fullname)


class SyntheticReader:
    def catalogue(self):
        return {
            "channels": [
                {"name": name, "dtype": "<f8", "array_width": 1,
                 "dummy": -1e32, "unit": "m" if name in ("X", "Y") else "nT"}
                for name in ("X", "Y", "MAG")
            ],
            "lines": [
                {"name": "L100", "kind": "traverse", "selected": True},
                {"name": "L200", "kind": "traverse", "selected": True},
                {"name": "T300", "kind": "tie", "selected": True},
            ],
            "coordinate_system": {"esri_wkt": "EPSG:32610"},
            "x_field": "X", "y_field": "Y", "database_metadata": {},
        }

    def read(self, line, channel):
        i = np.arange(6, dtype="float64")
        if channel == "X":
            values = 500000 + (i * 100 if line != "T300" else i * 0 + 200)
        elif channel == "Y":
            values = 6000000 + (i * 100 if line == "T300" else i * 0 + (200 if line == "L200" else 0))
        else:
            values = 12 + i
        return values, (0.0, 1.0)


def main():
    QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication([], False)
    app.initQgis()
    project = QgsProject.instance()
    blocker = NoGeosoft()
    sys.meta_path.insert(0, blocker)
    root = Path(os.environ["TEMP"])
    dock = None
    try:
        assert not any(name.startswith("geosoft") for name in sys.modules)
        archive = root / "synthetic.twarchive"
        result = convert_database(SyntheticReader(), archive, {"source_path": "synthetic.gdb"})
        assert result["verified"] and result["samples"] == 18, result
        store, database_id, _ = open_archive(archive)
        assert sum(batch.num_rows for batch in store.batches(database_id, ["MAG"])) == 18
        # Exercise the UI entry point; run its import job synchronously for this check.
        destination = SurveyStore(root / "workspace", create=True)
        imported = []

        def start(folder, jobs):
            for name, job in jobs:
                database_id = job(destination, lambda: False)
                database_id, name, package, error = SurveyWorkspaceDialog._try_survey_map(
                    destination, database_id, None, None
                )
                assert package and not error, error
                imported.append(add_survey_map(project, destination, database_id, name, package))

        dock = FilterStackDock()
        with patch.object(dock, "_start_gdb_survey_maps", side_effect=start):
            dock.import_open_archive(archive / "archive.json")
        assert len(imported) == 1
        layers = imported[0]
        assert layers["flight_lines"].featureCount() == 2
        assert layers["tie_lines"].featureCount() == 1
        assert layers["survey_boundary"].featureCount() >= 1
        assert layers["samples"].featureCount() == 18
        assert all(layer.isValid() and layer.crs().authid() == "EPSG:32610" for layer in layers.values())
        assert not any(name.startswith("geosoft") for name in sys.modules)
        print("PASS: verified open GDB, UI import, native samples, flight/tie/boundary layers; Geosoft imports blocked")
    finally:
        if dock is not None:
            dock.disconnect_project()
            dock.close()
        project.clear()
        sys.meta_path.remove(blocker)
        app.exitQgis()


if __name__ == "__main__":
    main()
