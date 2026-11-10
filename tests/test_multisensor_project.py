import json
import hashlib
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from terraworkbench_core.multisensor_project import run_project


@pytest.fixture
def recipe(tmp_path):
    y, x = np.indices((12, 14))
    paths = {}
    for name, a in [
        ("magnetic", np.sin(x) + np.cos(y)),
        ("terrain", 100 + 0.02 * y),
        ("gpr", np.sin(x * 0.5) + y * 0.01),
    ]:
        p = tmp_path / (name + ".tif")
        with rasterio.open(
            p,
            "w",
            driver="GTiff",
            height=12,
            width=14,
            count=1,
            dtype="float32",
            crs="EPSG:32617",
            transform=from_origin(1000, 2000, 0.25, 0.25),
            nodata=np.nan,
        ) as out:
            out.write(a.astype("float32"), 1)
        paths[name] = str(p)
    return dict(
        magnetic_grid=paths["magnetic"],
        terrain_grid=paths["terrain"],
        terrain_kind="dtm",
        terrain_scale_m=1,
        terrain_elevation_unit="m",
        gpr_layers=[dict(path=paths["gpr"], label="slice", depth_m=0)],
        output_directory=str(tmp_path / "outputs"),
        thresholds=[90],
        buffers_m=[0, 0.25],
        offsets_m=[0.25],
        report_percentile=90,
    )


def test_raster_outputs_masks_geometry_and_source_preservation(recipe):
    sources = [
        recipe["magnetic_grid"],
        recipe["terrain_grid"],
        recipe["gpr_layers"][0]["path"],
    ]
    before = {p: hashlib.sha256(open(p, "rb").read()).hexdigest() for p in sources}
    result = run_project(recipe)
    assert result["status"] == "complete" and len(result["alignment_sensitivity"]) == 4
    p = result["products"][0]
    with rasterio.open(p["rgb"]) as src:
        a = src.read()
        assert src.count == 3 and src.crs.to_epsg() == 32617
        assert np.nanmin(a) >= 0 and np.nanmax(a) <= 1
    with rasterio.open(p["classes"]) as src:
        assert set(np.unique(src.read(1)[np.isfinite(src.read(1))])).issubset(
            set(range(8))
        )
    assert all(
        hashlib.sha256(open(p, "rb").read()).hexdigest() == before[p] for p in sources
    )
    assert json.load(open(result["manifest"]))["status"] == "complete"


def test_empty_output_is_rejected_before_writing(recipe, tmp_path):
    recipe["output_directory"] = ""
    with pytest.raises(ValueError, match="output_directory"):
        run_project(recipe)
    assert not (tmp_path / "outputs").exists()


def test_nonoverlap_is_not_fabricated(recipe, tmp_path):
    p = tmp_path / "far.tif"
    with rasterio.open(
        p,
        "w",
        driver="GTiff",
        height=12,
        width=14,
        count=1,
        dtype="float32",
        crs="EPSG:32617",
        transform=from_origin(5000, 6000, 0.25, 0.25),
        nodata=np.nan,
    ) as out:
        out.write(np.ones((12, 14), dtype="float32"), 1)
    recipe["gpr_layers"][0]["path"] = str(p)
    with pytest.raises(ValueError, match="common coverage"):
        run_project(recipe)
    manifest = list((tmp_path / "outputs").glob("*/manifest.json"))[0]
    assert json.load(open(manifest))["status"] == "failed"


def test_cancel_records_status_and_leaves_sources(recipe, tmp_path):
    with pytest.raises(InterruptedError):
        run_project(recipe, canceled=lambda: True)
    assert (
        json.load(open(next((tmp_path / "outputs").glob("*/manifest.json"))))["status"]
        == "canceled"
    )
    assert all(
        __import__("pathlib").Path(recipe[k]).exists()
        for k in ("magnetic_grid", "terrain_grid")
    )


def test_vector_horizontal_reprojection_preserves_z_and_attributes(recipe, tmp_path):
    import geopandas as gpd
    from shapely.geometry import Polygon

    v = tmp_path / "vectors.gpkg"
    geom = Polygon(
        [(1001, 1999, 10), (1002, 1999, 10), (1002, 1998, 10), (1001, 1998, 10)]
    )
    gpd.GeoDataFrame(
        {"class": ["target"], "original_x": [12]}, geometry=[geom], crs="EPSG:32617"
    ).to_file(v, engine="pyogrio")
    recipe.update(vector_path=str(v), vector_class_field="class")
    result = run_project(recipe)
    frame = gpd.read_file(result["vectors"]["path"], engine="pyogrio")
    assert frame.geometry.iloc[0].has_z and frame.original_x.iloc[0] == 12
    assert frame.target_x.iloc[0] == pytest.approx(1001.5)
    assert (
        len(result["vector_summary"]) == 2
        and result["vector_summary"][0]["covered"] == 1
    )
