"""Headless GDAL/database integration, CRS rejection and publication rollback."""
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from TerraWorkbench.dependencies import import_harmonica
from TerraWorkbench.survey_store import SurveyStore
from TerraWorkbench.magnetic_pipeline import MagneticPipelineOptions
from osgeo import gdal, osr
import numpy as np


def main():
    import_harmonica()
    import pyarrow as pa
    import pyarrow.parquet as pq
    with tempfile.TemporaryDirectory(prefix="tw_magnetic_") as folder:
        root = Path(folder)
        source = root / "input.parquet"
        pq.write_table(pa.table({"x": [0., 1, 2, 3, 0, 1, 2, 3], "y": [0.] * 4 + [3.] * 4,
            "line": ["a"] * 4 + ["b"] * 4, "mag": [10.] * 8}), source)
        store = SurveyStore(root / "project", create=True)
        database = store.import_file(source)
        store.configure_geometry(database, "x", "y", "EPSG:26910")
        store.rename_channel(database, "mag", "mag", unit="nT")
        store.level_lines(database, "mag", "line", [("a", "b", 4.)], "correction", "leveled")
        template = root / "template.tif"
        ds = gdal.GetDriverByName("GTiff").Create(str(template), 4, 4, 1, gdal.GDT_Float64)
        ds.SetGeoTransform((-.5, 1., 0., 3.5, 0., -1.))
        crs = osr.SpatialReference()
        crs.ImportFromEPSG(26910)
        ds.SetProjection(crs.ExportToWkt())
        values = np.arange(16.).reshape(4, 4)
        values[1, 2] = np.nan
        ds.GetRasterBand(1).SetNoDataValue(float("nan"))
        ds.GetRasterBand(1).WriteArray(values)
        ds = None
        options = MagneticPipelineOptions(90., 0., padding_rows=2, padding_columns=2)
        def run(**kwargs):
            return store.magnetic_grid_pipeline(database, template, "x", "y", "line", "correction", options, **kwargs)
        result = run()
        assert len(result["products"]) == 15
        recipe = json.loads(Path(result["recipe"]).read_text())
        assert len(recipe["inputs"]) == 4 and recipe["source_unit"] == "nT"
        for name, path in result["products"].items():
            ds = gdal.Open(path)
            assert np.array_equal(np.isnan(ds.ReadAsArray()), np.isnan(values))
            assert np.isnan(ds.GetRasterBand(1).GetNoDataValue())
            assert ds.GetRasterBand(1).GetUnitType() == ("radians" if name in ("Tilt", "Theta", "TDX") else "nT/m^2" if name == "DZ2_2VD" else "nT/m" if name in ("DX", "DY", "DZ_1VD", "THDR", "AS", "45HG") else "nT")
            ds = None
        before = set((store.root / "grids").iterdir())
        # Cancel after the first output is written, not just at preflight.
        def canceled():
            return any((store.root / "grids").glob("*.partial/*.tif"))
        try:
            run(canceled=canceled)
            raise AssertionError("Cancellation was ignored")
        except InterruptedError:
            pass
        assert set((store.root / "grids").iterdir()) == before
        store.configure_geometry(database, "x", "y", "EPSG:26911")
        try:
            run()
            raise AssertionError("CRS mismatch accepted")
        except ValueError as error:
            assert "same projected metre CRS" in str(error)
        assert set((store.root / "grids").iterdir()) == before
        print("PASS: 15 products, NoData, units, provenance, mid-publication cancellation and CRS rejection", flush=True)


if __name__ == "__main__":
    main()
