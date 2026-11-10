"""Portable raster/vector integration workflow without desktop GIS dependencies."""

from pathlib import Path
import csv
import hashlib
import json
import uuid
import warnings
import numpy as np
from .multisensor_fusion import (
    rgb_composite,
    pca_fusion,
    anomaly_coincidence,
    shift_without_wrap,
)
from .vector_grid_audit import prepare_polygon, prepared_samples


def vector_operations(
    path, target_crs, bounds=None, grid_directory=None, source_crs=None
):
    import geopandas as gpd
    from pyproj import CRS, datadir
    from pyproj.aoi import AreaOfInterest
    from pyproj.transformer import TransformerGroup
    from rasterio.warp import transform_bounds

    if grid_directory:
        folder = Path(grid_directory)
        if not folder.is_dir():
            raise ValueError("PROJ grid directory does not exist.")
        datadir.append_data_dir(str(folder))
    frame = gpd.read_file(path, engine="pyogrio")
    source = CRS(source_crs or frame.crs) if source_crs or frame.crs else None
    if source is None:
        raise ValueError("Vector source CRS is missing; declare it explicitly.")
    aoi = None
    if bounds:
        b = transform_bounds(target_crs, "EPSG:4326", *bounds)
        aoi = AreaOfInterest(*b)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        group = TransformerGroup(
            source,
            target_crs,
            always_xy=True,
            area_of_interest=aoi,
            allow_ballpark=False,
        )
    return dict(
        source_crs=source.to_string(),
        declared_source_crs=str(frame.crs),
        target_crs=str(target_crs),
        columns=[c for c in frame.columns if c != "geometry"],
        best_available=group.best_available,
        available=[
            dict(name=t.description, accuracy_m=t.accuracy, pipeline=t.definition)
            for t in group.transformers
        ],
        unavailable=[
            dict(
                name=o.name,
                accuracy_m=o.accuracy,
                grids=[g.short_name for g in o.grids if not g.available],
            )
            for o in group.unavailable_operations
        ],
    )


def run_project(recipe, progress=None, canceled=None):
    """Run explicit user inputs; return saved products, tables and provenance.

    Required: magnetic_grid, terrain_grid, gpr_layers[{path,label,depth_m}],
    output_directory. Optional: vector_path, vector_class_field,
    vector_operation, vector_source_crs, proj_grid_directory, buffers_m,
    thresholds, offsets_m, terrain_kind ('dtm'/'relief'), terrain_scale_m,
    terrain_elevation_unit ('m'/'ft'), report_percentile.
    """
    import rasterio
    from rasterio.warp import reproject, Resampling, transform_bounds
    from affine import Affine

    def check():
        if canceled and canceled():
            raise InterruptedError("Multisensor analysis canceled.")

    def emit(value):
        check()
        if progress:
            progress(value)

    config = json.loads(json.dumps(recipe))
    for key in ("magnetic_grid", "terrain_grid", "output_directory"):
        if not str(config.get(key, "")).strip():
            raise ValueError("Required parameter: " + key)
    gprs = config.get("gpr_layers", [])
    if not gprs:
        raise ValueError("Add at least one GPR GeoTIFF.")
    thresholds = [float(v) for v in config.get("thresholds", [80, 90, 95])]
    buffers = [float(v) for v in config.get("buffers_m", [0, 0.25, 0.5])]
    offsets = [float(v) for v in config.get("offsets_m", [0.25, 0.5, 1])]
    level = float(config.get("report_percentile", 90))
    if not thresholds or any(
        not np.isfinite(v) or not 0 < v < 100 for v in thresholds + [level]
    ):
        raise ValueError("Thresholds must be between 0 and 100.")
    if level not in thresholds:
        raise ValueError("Report percentile must be included in the thresholds.")
    if not buffers or any(not np.isfinite(v) or v < 0 or v > 100 for v in buffers):
        raise ValueError("Buffers must be between 0 and 100 metres.")
    if any(not np.isfinite(v) or v <= 0 or v > 100 for v in offsets):
        raise ValueError("Offsets must be positive and at most 100 metres.")
    labels = [str(v.get("label") or Path(v["path"]).stem) for v in gprs]
    if len(set(labels)) != len(labels):
        raise ValueError("GPR labels must be unique.")
    for layer in gprs:
        if layer.get("depth_m") is not None and (
            not np.isfinite(float(layer["depth_m"])) or float(layer["depth_m"]) < 0
        ):
            raise ValueError("GPR depths must be nonnegative metres or null.")
    for p in (
        [config["magnetic_grid"], config["terrain_grid"]]
        + [v["path"] for v in gprs]
        + ([config["vector_path"]] if config.get("vector_path") else [])
    ):
        if not Path(p).is_file():
            raise ValueError("Input does not exist: " + str(p))
    output = Path(config["output_directory"])
    output.mkdir(parents=True, exist_ok=True)
    job = output / ("multisensor-" + uuid.uuid4().hex[:12])
    job.mkdir()
    manifest = dict(
        status="running",
        recipe=config,
        products=[],
        sources=[],
        vectors=None,
        metrics=[],
        alignment_sensitivity=[],
        vector_summary=[],
        warnings=[],
    )

    def save():
        (job / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

    save()

    def source(path):
        check()
        path = Path(path)
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                check()
                digest.update(chunk)
        manifest["sources"].append(
            dict(path=str(path.resolve()), sha256=digest.hexdigest())
        )

    try:
        with rasterio.open(config["magnetic_grid"]) as src:
            if (
                not src.crs
                or not src.crs.is_projected
                or src.crs.linear_units.lower()
                not in ("metre", "meter", "metres", "meters")
            ):
                raise ValueError("Magnetic grid must have a projected CRS in metres.")
            if (
                src.transform.b
                or src.transform.d
                or src.transform.a <= 0
                or src.transform.e >= 0
            ):
                raise ValueError("Reference grid must be north-up.")
            if src.width * src.height > 4_000_000:
                raise ValueError("Reference grid exceeds four million cells.")
            shape = src.shape
            transform = src.transform
            crs = src.crs
            bounds = tuple(src.bounds)
            cell = src.res[0]
            if not np.isclose(src.res[0], src.res[1]):
                raise ValueError("Reference grid requires square cells.")
            mag = src.read(1, masked=True).astype(float).filled(np.nan)
        if np.isfinite(mag).sum() < 3:
            raise ValueError("Magnetic grid has insufficient valid data.")
        source(config["magnetic_grid"])
        manifest["geometry"] = dict(
            shape=list(shape), transform=list(transform), crs=str(crs), cell_m=cell
        )

        def aligned(
            path, out_shape=shape, out_transform=transform, method=Resampling.bilinear
        ):
            check()
            a = np.full(out_shape, np.nan)
            with rasterio.open(path) as src:
                if not src.crs:
                    raise ValueError("Raster CRS is missing: " + str(path))
                reproject(
                    rasterio.band(src, 1),
                    a,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    src_nodata=src.nodata,
                    dst_transform=out_transform,
                    dst_crs=crs,
                    dst_nodata=np.nan,
                    resampling=method,
                )
            return a

        def export(name, a, units, description):
            check()
            if a.ndim == 2:
                a = a[..., None]
            path = job / (name + ".tif")
            with rasterio.open(
                path,
                "w",
                driver="GTiff",
                width=shape[1],
                height=shape[0],
                count=a.shape[-1],
                dtype="float32",
                crs=crs,
                transform=transform,
                nodata=np.nan,
                compress="deflate",
            ) as dst:
                dst.write(np.moveaxis(a.astype("float32"), -1, 0))
                dst.update_tags(units=units, description=description)
                for n in range(a.shape[-1]):
                    dst.set_band_unit(n + 1, units)
            return str(path)

        emit("Aligning terrain")
        kind = config.get("terrain_kind", "dtm")
        scale = float(config.get("terrain_scale_m", 2))
        unit = config.get("terrain_elevation_unit", "m")
        if kind not in ("dtm", "relief") or unit not in ("m", "ft"):
            raise ValueError("Choose DTM or existing relief, with m or ft elevations.")
        factor = 1.0 if unit == "m" else 0.3048
        if kind == "dtm":
            if not np.isfinite(scale) or scale <= 0:
                raise ValueError("Terrain relief scale must be positive.")
            pad = int(np.ceil(scale / cell / 2)) + 2
            expanded = (shape[0] + 2 * pad, shape[1] + 2 * pad)
            if np.prod(expanded) > 4_000_000:
                raise ValueError(
                    "DTM including halo exceeds the processing cell limit."
                )
            dtm = (
                aligned(
                    config["terrain_grid"],
                    expanded,
                    transform * Affine.translation(-pad, -pad),
                    Resampling.average,
                )
                * factor
            )
            from .terrain_analysis import relief_arrays

            grids, terrain_recipe = relief_arrays(
                dtm, cell, [scale], scale / 2, scale, canceled=canceled
            )
            key = next(k for k in grids if k.startswith("terrain_lrm_"))
            relief = grids[key][pad:-pad, pad:-pad]
            manifest["terrain_recipe"] = terrain_recipe
            del grids, dtm
        else:
            relief = aligned(config["terrain_grid"]) * factor
        source(config["terrain_grid"])
        terrain_path = export(
            "terrain_relief", relief, "m", "Terrain local relief used for fusion"
        )
        mag_path = export("magnetic_reference", mag, "nT", "Magnetic reference grid")
        frame = None
        prepared = {}
        vector_rows = []
        if config.get("vector_path"):
            emit("Inspecting vector CRS and transformation")
            import geopandas as gpd
            from pyproj.aoi import AreaOfInterest
            from pyproj.transformer import TransformerGroup
            from shapely.ops import transform as transform_geometry

            details = vector_operations(
                config["vector_path"],
                crs,
                bounds,
                config.get("proj_grid_directory"),
                config.get("vector_source_crs"),
            )
            frame = gpd.read_file(config["vector_path"], engine="pyogrio")
            if len(frame) > 100_000:
                raise ValueError("Vector layer exceeds 100,000 features.")
            if (
                frame.geometry.isna().any()
                or frame.geometry.is_empty.any()
                or not frame.geometry.is_valid.all()
            ):
                raise ValueError(
                    "Vector layer contains missing, empty or invalid geometry; repair it before analysis."
                )
            if not frame.geom_type.isin(
                [
                    "Polygon",
                    "MultiPolygon",
                    "Point",
                    "MultiPoint",
                    "LineString",
                    "MultiLineString",
                ]
            ).all():
                raise ValueError("Unsupported vector geometry type.")
            field = config.get("vector_class_field") or next(
                (c for c in frame.columns if c != "geometry"), None
            )
            if field not in frame.columns or field == "geometry":
                raise ValueError("Select an existing vector class field.")
            geo_bounds = transform_bounds(crs, "EPSG:4326", *bounds)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                group = TransformerGroup(
                    details["source_crs"],
                    crs,
                    always_xy=True,
                    area_of_interest=AreaOfInterest(*geo_bounds),
                    allow_ballpark=False,
                )
            selected = config.get("vector_operation")
            candidates = [
                t
                for t in group.transformers
                if not selected or t.description == selected
            ]
            if not candidates:
                raise ValueError(
                    "Selected datum operation is unavailable; inspect operations and PROJ grids."
                )
            if not selected and len(candidates) > 1:
                raise ValueError(
                    "Multiple datum operations are available; explicitly select one."
                )
            transformer = candidates[0]
            source_centers = frame.geometry.centroid
            tx, ty = transformer.transform(
                source_centers.x.to_numpy(), source_centers.y.to_numpy(), errcheck=True
            )

            def horizontal(x, y, z=None):
                xx, yy = transformer.transform(x, y, errcheck=True)
                return (xx, yy, z) if z is not None else (xx, yy)

            geometries = [transform_geometry(horizontal, g) for g in frame.geometry]
            original_crs = str(frame.crs)
            frame = frame.copy()
            frame.geometry = geometries
            frame = frame.set_crs(crs, allow_override=True)
            frame["target_x"] = frame.geometry.centroid.x
            frame["target_y"] = frame.geometry.centroid.y
            vector_file = job / "interpretation.gpkg"
            frame.to_file(vector_file, layer="interpretation", engine="pyogrio")
            shp = job / "interpretation.shp"
            frame.to_file(shp, engine="pyogrio", encoding="UTF-8")
            manifest["vectors"] = dict(
                path=str(vector_file),
                shapefile=str(shp),
                class_field=field,
                declared_crs=original_crs,
                used_source_crs=details["source_crs"],
                target_crs=str(crs),
                operation=transformer.description,
                accuracy_m=transformer.accuracy,
                pipeline=transformer.definition,
                class_counts={
                    str(k): int(v)
                    for k, v in frame[field].astype(str).value_counts().items()
                },
            )
            if transformer.accuracy < 0 or transformer.accuracy > cell:
                manifest["warnings"].append(
                    "Vector datum-operation accuracy is unknown or larger than one reference-grid cell. It is not field validation."
                )
            if original_crs != details["source_crs"]:
                manifest["warnings"].append(
                    "Vector source CRS was explicitly overridden by the recipe."
                )
            path = Path(config["vector_path"])
            for p in (
                [path]
                if path.suffix.lower() != ".shp"
                else sorted(path.parent.glob(path.stem + ".*"))
            ):
                source(p)
            for buffer in buffers:
                prepared[buffer] = [
                    prepare_polygon(shape, g.buffer(buffer) if buffer else g, transform)
                    for g in frame.geometry
                ]
        emit("Computing fixed RGB stretch across GPR layers")
        stretch = []
        for layer in gprs:
            check()
            preview = aligned(layer["path"])
            common = np.isfinite(mag) & np.isfinite(preview) & np.isfinite(relief)
            if common.sum() < 3:
                raise ValueError("Insufficient common coverage: " + layer["path"])
            stretch.append(
                np.percentile(
                    np.stack(
                        [np.abs(mag[common]), preview[common], np.abs(relief[common])],
                        axis=-1,
                    ),
                    (2, 98),
                    axis=0,
                ).T
            )
        stretch = np.asarray(stretch)
        fixed_bounds = np.column_stack(
            [stretch[:, :, 0].min(axis=0), stretch[:, :, 1].max(axis=0)]
        )
        manifest["rgb_stretch_method"] = (
            "Fixed envelope of per-layer common-cell P2/P98 across all selected layers"
        )
        del preview, stretch
        for index, layer in enumerate(gprs):
            label = labels[index]
            emit(f"Fusing {index + 1}/{len(gprs)} Â· {label}")
            gpr = aligned(layer["path"])
            source(layer["path"])
            rgb, rm = rgb_composite(
                [np.abs(mag), gpr, np.abs(relief)], bounds=fixed_bounds
            )
            pca, pm = pca_fusion([mag, gpr, relief])
            prefix = f"layer_{index + 1:03d}"
            product = dict(
                label=label,
                depth_m=layer.get("depth_m"),
                gpr=export(
                    prefix + "_gpr", gpr, "supplied units", "Aligned supplied GPR slice"
                ),
                rgb=export(
                    prefix + "_rgb",
                    rgb,
                    "unitless",
                    "RGB: absolute magnetic, GPR, absolute terrain relief",
                ),
                pca=export(
                    prefix + "_pca", pca, "unitless", "Standardized PCA components"
                ),
                rgb_recipe=rm,
                pca_recipe=pm,
                terrain=terrain_path,
                magnetic=mag_path,
            )
            for threshold in thresholds:
                codes, cm = anomaly_coincidence(
                    [np.abs(mag), gpr, np.abs(relief)], threshold
                )
                manifest["metrics"].append(
                    dict(
                        label=label,
                        depth_m=layer.get("depth_m"),
                        threshold=threshold,
                        **cm,
                    )
                )
                codepath = export(
                    prefix + "_classes_" + str(threshold).replace(".", "p"),
                    codes,
                    "class code",
                    "Bits 1 magnetic, 2 GPR, 4 terrain; no archaeological confidence",
                )
                if threshold == level:
                    product["classes"] = codepath
                    product["class_recipe"] = cm
            manifest["products"].append(product)
            with rasterio.open(product["classes"]) as src:
                codes = src.read(1, masked=True).filled(np.nan)
            if frame is not None:
                for buffer, locations in prepared.items():
                    groups = {}
                    for number, (location, cls) in enumerate(
                        zip(locations, frame[field].astype(str))
                    ):
                        check()
                        sample, coverage = prepared_samples(codes, location)
                        bits = sample.astype(int)
                        row = dict(
                            label=label,
                            depth_m=layer.get("depth_m"),
                            buffer_m=buffer,
                            feature_index=number + 1,
                            source_class=cls,
                            **coverage,
                            magnetic_cells=int(np.sum((bits & 1) > 0)),
                            gpr_cells=int(np.sum((bits & 2) > 0)),
                            terrain_cells=int(np.sum((bits & 4) > 0)),
                            mag_gpr_cells=int(np.sum((bits & 3) == 3)),
                            all_three_cells=int(np.sum(bits == 7)),
                        )
                        vector_rows.append(row)
                        groups.setdefault(cls, []).append(row)
                    for cls, rows in groups.items():
                        eligible = [
                            r
                            for r in rows
                            if r["coverage_fraction"] is not None
                            and r["coverage_fraction"] >= 0.5
                        ]
                        manifest["vector_summary"].append(
                            dict(
                                label=label,
                                depth_m=layer.get("depth_m"),
                                buffer_m=buffer,
                                source_class=cls,
                                total=len(rows),
                                covered=len(eligible),
                                subcell=sum(r["expected_cells"] == 0 for r in rows),
                                magnetic=sum(r["magnetic_cells"] > 0 for r in eligible),
                                gpr=sum(r["gpr_cells"] > 0 for r in eligible),
                                terrain=sum(r["terrain_cells"] > 0 for r in eligible),
                                mag_gpr=sum(r["mag_gpr_cells"] > 0 for r in eligible),
                                all_three=sum(
                                    r["all_three_cells"] > 0 for r in eligible
                                ),
                            )
                        )
            for offset in offsets:
                delta = max(1, int(round(offset / cell)))
                for dy, dx in ((0, delta), (0, -delta), (delta, 0), (-delta, 0)):
                    check()
                    shifted = shift_without_wrap(gpr, dy, dx)
                    mask = (
                        np.isfinite(mag)
                        & np.isfinite(gpr)
                        & np.isfinite(relief)
                        & np.isfinite(shifted)
                    )
                    if mask.sum() < 3:
                        continue
                    _, base = anomaly_coincidence(
                        [
                            np.where(mask, a, np.nan)
                            for a in (np.abs(mag), gpr, np.abs(relief))
                        ],
                        level,
                    )
                    _, test = anomaly_coincidence(
                        [
                            np.where(mask, a, np.nan)
                            for a in (np.abs(mag), shifted, np.abs(relief))
                        ],
                        level,
                    )
                    manifest["alignment_sensitivity"].append(
                        dict(
                            label=label,
                            requested_offset_m=offset,
                            actual_offset_m=delta * cell,
                            dy=dy,
                            dx=dx,
                            common_cells=int(mask.sum()),
                            baseline_dice=base["pairs"]["0-1"]["dice"],
                            shifted_dice=test["pairs"]["0-1"]["dice"],
                        )
                    )
            save()
            del gpr, rgb, pca, codes

        def write_csv(name, rows):
            if not rows:
                return
            with (job / name).open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)

        write_csv("vector_features.csv", vector_rows)
        write_csv("vector_summary.csv", manifest["vector_summary"])
        write_csv("alignment_sensitivity.csv", manifest["alignment_sensitivity"])
        manifest["core_sources"] = {
            name: hashlib.sha256(
                Path(__file__).with_name(name + ".py").read_bytes()
            ).hexdigest()
            for name in (
                "multisensor_project",
                "multisensor_fusion",
                "vector_grid_audit",
                "terrain_analysis",
            )
        }
        manifest["warnings"].extend(
            [
                "Interpretation classes may overlap and are not independent ground truth.",
                "PCA variance and threshold coincidence are not detection accuracy or confidence probabilities.",
            ]
        )
        manifest["status"] = "complete"
        save()
        emit("Complete")
        return dict(directory=str(job), manifest=str(job / "manifest.json"), **manifest)
    except Exception as exc:
        manifest["status"] = (
            "canceled" if isinstance(exc, InterruptedError) else "failed"
        )
        manifest["error"] = str(exc)
        save()
        raise
