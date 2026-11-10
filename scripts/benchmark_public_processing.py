"""Pinned public 2-D processing campaign; no QGIS or private survey required.

Downloads stay in the explicitly supplied cache. Reports separate numerical
agreement, field-data integration, interpolation diagnostics and unmet scope.
Downloaded code is never executed. See docs/validation/reports/public_processing_benchmark.md.
"""

import argparse
import ast
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import io
import json
import lzma
from pathlib import Path
import platform
import re
import sys
import time
from urllib.request import Request, urlopen
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.public_files import repository_provenance  # noqa: E402
MANIFEST = Path(__file__).with_name("public_processing_sources.json")


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def fetch(cache, source, offline=False):
    """Verify every cached byte; preserve corrupt originals for diagnosis."""
    cache = Path(cache)
    name = source["filename"]
    if Path(name).name != name or name in (".", "..") or "\\" in name:
        raise ValueError("Expected a plain cache filename")
    target = cache / name
    cache.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        if offline:
            raise FileNotFoundError("Offline cache is missing " + name)
        total, sha = 0, hashlib.sha256()
        request = Request(
            source["url"], headers={"User-Agent": "TerraWorkbench validation"}
        )
        # Exclusive creation, no duplicate payload. Interrupted/invalid bytes
        # remain for diagnosis and cannot be returned as a verified input.
        with urlopen(request, timeout=90) as response, target.open("xb") as stream:
            for block in iter(lambda: response.read(1 << 20), b""):
                total += len(block)
                if total > source["bytes"]:
                    raise ValueError("Download exceeds pinned size: " + name)
                sha.update(block)
                stream.write(block)
        if total != source["bytes"] or sha.hexdigest() != source["sha256"]:
            raise ValueError("Downloaded checksum/size mismatch: " + name)
    if target.stat().st_size != source["bytes"] or digest(target) != source["sha256"]:
        raise ValueError("Cached checksum/size mismatch: " + name)
    return target


def member_bytes(archive, name, maximum=65_000_000):
    """Read named regular members without extracting archive paths."""
    with zipfile.ZipFile(archive) as stream:
        matches = [entry for entry in stream.infolist() if entry.filename == name]
        if len(matches) != 1 or matches[0].is_dir():
            raise ValueError("Missing/ambiguous archive member: " + name)
        if matches[0].file_size > maximum:
            raise ValueError("Archive member exceeds budget")
        return stream.read(matches[0])


def compare(actual, expected, *, atol, rtol=0):
    a, b = np.asarray(actual), np.asarray(expected)
    if a.shape != b.shape:
        raise AssertionError("Reference shape mismatch")
    if not np.array_equal(np.isfinite(a), np.isfinite(b)):
        raise AssertionError("Reference validity mask mismatch")
    valid = np.isfinite(a)
    if not valid.any():
        raise AssertionError("No finite reference support")
    error = a[valid] - b[valid]
    metrics = dict(
        samples=int(valid.sum()),
        max_abs_error=float(np.max(abs(error))),
        rms_error=float(np.sqrt(np.mean(error**2))),
        atol=atol,
        rtol=rtol,
        passed=bool(np.all(abs(error) <= atol + rtol * abs(b[valid]))),
    )
    return metrics


def gravity_case(paths, output):
    import boule
    import pandas as pd
    from terraworkbench_core.gravity_corrections import (
        gravity_disturbance,
        land_gravity_reduction,
        normal_gravity_grs80,
    )

    bush = pd.read_csv(paths["bushveld"])
    normal = boule.WGS84.normal_gravity(
        (
            bush.longitude.to_numpy(),
            bush.latitude.to_numpy(),
            bush.height_geometric_m.to_numpy(),
        )
    )
    actual = gravity_disturbance(bush.gravity_mgal, normal)
    published = compare(actual, bush.gravity_disturbance_mgal, atol=2e-6)
    southern = pd.read_csv(paths["southern_africa"])
    lat, height = southern.latitude.to_numpy(), southern.height_sea_level_m.to_numpy()
    reference_normal = boule.GRS80.normal_gravity(
        (np.zeros_like(lat), lat, np.zeros_like(lat))
    )
    constants = dict(
        height_reference="MSL", density_kg_m3=2670.0, slab_coefficient=0.04193
    )
    products, recipe = land_gravity_reduction(
        southern.gravity_mgal.to_numpy(), lat, height, height, **constants
    )
    # Explicit linear free-air and infinite slab recipe, not the published
    # Bushveld finite-topography disturbance (a different physical product).
    expected = (
        southern.gravity_mgal.to_numpy()
        - reference_normal
        + 0.3086 * height
        - 0.04193 * 2.670 * height
    )
    reduction = compare(products["simple_bouguer_anomaly"], expected, atol=2e-4)
    surface = compare(normal_gravity_grs80(lat), reference_normal, atol=2e-4)
    np.savez_compressed(
        output / "gravity.npz",
        bushveld_disturbance=actual,
        southern_simple_bouguer=products["simple_bouguer_anomaly"],
    )
    return dict(
        passed=all(item["passed"] for item in (published, reduction, surface)),
        unit="mGal",
        published_bushveld=published,
        southern_reduction=reduction,
        grs80_surface=surface,
        recipe=recipe,
        scope="Published disturbance plus explicit land slab recipe. No field validation of full terrain, tides or atmospheric corrections. Southern Africa horizontal datum is unspecified by publisher; no reprojection applied.",
    )


def magnetic_case(paths, output):
    import harmonica as hm
    import xarray as xr
    from terraworkbench_core import spectral as sp

    grid = xr.load_dataarray(paths["lightning"])
    dy, dx = float(np.diff(grid.northing)[0]), float(np.diff(grid.easting)[0])
    ke, kn, k = sp.frequency_grid(grid.shape, dy, dx)
    comparisons = {}
    for height in (50.0, 250.0, 1000.0):
        comparisons[f"upward_{height:g}m"] = compare(
            sp.apply_transfer(grid.values, np.exp(-k * height)),
            hm.upward_continuation(grid, height).values,
            atol=2e-9,
            rtol=1e-11,
        )
    for order in (1, 2):
        comparisons[f"upward_derivative_{order}"] = compare(
            sp.apply_transfer(grid.values, (-k) ** order),
            hm.derivative_upward(grid, order=order).values,
            atol=2e-10,
            rtol=1e-10,
        )
    for inclination, declination in ((-55.0, 12.0), (55.0, -20.0), (-15.0, 80.0)):
        transform = sp.magnetic_field_transform(
            ke, kn, k, inclination, declination, 90.0, 0.0, max_gain=1e8
        )
        actual = sp.apply_transfer(grid.values, transform)
        comparisons[f"rtp_{inclination:g}_{declination:g}"] = compare(
            actual,
            hm.reduction_to_pole(grid, inclination, declination).values,
            atol=2e-8,
            rtol=1e-10,
        )
    # Independent real-space convolution on field data, including real edges.
    from scipy.ndimage import convolve
    from terraworkbench_core.basic_processing import smooth_nine_point

    kernel = np.outer([1.0, 2.0, 1.0], [1.0, 2.0, 1.0]) / 16
    comparisons["binomial_interior"] = compare(
        smooth_nine_point(grid.values)[1:-1, 1:-1],
        convolve(grid.values, kernel, mode="nearest")[1:-1, 1:-1],
        atol=2e-12,
        rtol=1e-12,
    )
    for name, metrics in comparisons.items():
        metrics["unit"] = (
            "nT/m^2"
            if name == "upward_derivative_2"
            else "nT/m"
            if name == "upward_derivative_1"
            else "nT"
        )
    np.savez_compressed(
        output / "magnetic.npz",
        upward_250m=sp.apply_transfer(grid.values, np.exp(-k * 250)),
    )
    return dict(
        passed=all(m["passed"] for m in comparisons.values()),
        shape=list(grid.shape),
        cells=int(grid.size),
        spacing_m=[dy, dx],
        comparisons=comparisons,
        scope="Periodic FFT, no detrend, taper or padding. Reference Harmonica independently constructs transfers. Directions are declared numerical stress cases, not recovered acquisition parameters.",
    )


def interpolation_case(paths, output):
    import xarray as xr
    from scipy.interpolate import LinearNDInterpolator
    from terraworkbench_core.basic_processing import ThinPlateGridder
    from terraworkbench_core.gridding_methods import MinimumCurvatureGridder

    grid = xr.load_dataarray(paths["lightning"]).isel(
        northing=slice(40, 137), easting=slice(40, 141)
    )
    x = grid.easting.values - grid.easting.values[0]
    y = grid.northing.values - grid.northing.values[0]
    xx, yy = np.meshgrid(x, y)
    # Deterministic withheld blocks, not a random interleaved split presented
    # as independent spatial validation. Already gridded input is disclosed.
    train = np.zeros(grid.shape, bool)
    train[::5, ::5] = True
    withheld = (xx > 1700) & (xx < 2700) & (yy > 1700) & (yy < 2700)
    train[withheld] = False
    points, values = np.c_[xx[train], yy[train]], grid.values[train]
    query = np.c_[xx[withheld], yy[withheld]]
    predictions = {
        "linear_scipy": LinearNDInterpolator(points, values)(query),
        "global_tps": ThinPlateGridder(points, values)(query),
        "local_tps_32": ThinPlateGridder(points, values, neighbors=32)(query),
    }
    solver_diagnostics = {}
    for solver in ("multilevel", "variational"):
        model = MinimumCurvatureGridder(
            points,
            values,
            50.0,
            solver=solver,
            coarse_grid=4,
            max_iterations=6400,
            tolerance=1e-5,
        )
        predictions["minimum_curvature_" + solver] = model.grid(x, y)[withheld]
        solver_diagnostics[solver] = model.metadata
    expected = grid.values[withheld]
    metrics = {}
    for name, prediction in predictions.items():
        finite = np.isfinite(prediction)
        if not finite.all():
            raise AssertionError("Incomplete interior interpolation: " + name)
        error = prediction - expected
        metrics[name] = dict(
            rms_nt=float(np.sqrt(np.mean(error**2))),
            bias_nt=float(error.mean()),
            max_abs_nt=float(np.max(abs(error))),
        )
    np.savez_compressed(output / "interpolation.npz", expected=expected, **predictions)
    return dict(
        passed=all(item["converged"] for item in solver_diagnostics.values()),
        training_points=int(train.sum()),
        withheld_cells=int(withheld.sum()),
        metrics=metrics,
        solver_diagnostics=solver_diagnostics,
        source_std_nt=float(grid.values.std()),
        scope="Interpolation diagnostics on a withheld block of an already interpolated public grid. Finite-output and declared solver-convergence checks only; no predeclared scientific accuracy acceptance and no raw-survey ground truth.",
    )


def terrain_case(paths, output):
    import xarray as xr
    from pyproj import Transformer
    from rasterio.transform import from_origin
    from rasterio.warp import reproject, Resampling
    from geoana.gravity import Prism
    from terraworkbench_core.adaptive_terrain import terrain_gravity_adaptive
    from terraworkbench_core.isostasy import (
        airy_prisms,
        airy_root_effect,
        airy_root_effect_fft,
    )

    original = xr.load_dataarray(paths["topography"])
    east, north = Transformer.from_crs(4326, 32734, always_xy=True).transform(
        18.4, -33.9
    )
    cell = 2500.0
    x = east + np.arange(-16, 17) * cell
    y = north + np.arange(-15, 16) * cell
    destination = np.full((len(y), len(x)), np.nan)
    lon, lat = original.longitude.values, original.latitude.values
    reproject(
        original.values[::-1],
        destination,
        src_transform=from_origin(
            lon[0] - (lon[1] - lon[0]) / 2,
            lat[-1] + (lat[1] - lat[0]) / 2,
            lon[1] - lon[0],
            lat[1] - lat[0],
        ),
        src_crs="EPSG:4326",
        dst_transform=from_origin(x[0] - cell / 2, y[-1] + cell / 2, cell, cell),
        dst_crs="EPSG:32734",
        dst_nodata=np.nan,
        resampling=Resampling.average,
    )
    z = destination[::-1].copy()
    if not np.isfinite(z).all():
        raise AssertionError("Incomplete projected DEM")
    xx, yy = np.meshgrid(x[::6], y[::6])
    obs = np.c_[xx.ravel(), yy.ravel(), np.full(xx.size, float(z.max() + 2000.0))]
    obs = np.vstack([obs, [east + 500000, north + 600000, 15000.0]])
    direct = np.zeros(len(obs))
    for row, col in np.ndindex(z.shape):
        height = z[row, col]
        if height == 0:
            continue
        density = 2670.0 if height > 0 else 1040.0 - 2670.0
        body = Prism(
            [x[col] - cell / 2, y[row] - cell / 2, min(0.0, height)],
            [x[col] + cell / 2, y[row] + cell / 2, max(0.0, height)],
            rho=density,
        )
        direct -= 1e5 * body.gravitational_field(obs)[:, 2]
    checks = {}
    for tolerance in (0.0, 1e-5, 1e-3):
        result = terrain_gravity_adaptive(
            x,
            y,
            z,
            obs,
            density_crust=2670.0,
            density_water=1040.0,
            reference_elevation_m=0.0,
            absolute_tolerance_mgal=tolerance,
        )
        error = abs(result["prism_effect_mgal"] - direct)
        bound = result["truncation_bound_mgal"]
        checks[str(tolerance)] = dict(
            max_abs_mgal=float(error.max()),
            max_bound_mgal=float(bound.max()),
            tolerance_mgal=tolerance,
            exact_prism_evaluations=result["recipe"]["exact_prism_evaluations"],
            monopole_evaluations=result["recipe"]["monopole_evaluations"],
            passed=bool(np.all(error <= bound + 2e-7)),
        )
    water = np.maximum(-z, 0)
    prisms, density = airy_prisms(x, y, z, water_thickness=water, density_mantle=3270.0)
    root_reference = np.zeros(len(obs))
    for prism, rho in zip(prisms, density):
        body = Prism(prism[[0, 2, 4]], prism[[1, 3, 5]], rho=rho)
        root_reference -= 1e5 * body.gravitational_field(obs)[:, 2]
    finite = compare(
        airy_root_effect(tuple(obs.T), prisms, density),
        root_reference,
        atol=2e-7,
        rtol=1e-9,
    )
    periodic, recipe = airy_root_effect_fft(
        z, (cell, cell), boundary="periodic", water_thickness=water
    )
    mean_expected = -2 * np.pi * 6.67430e-6 * float(np.mean(2670 * z + 1040 * water))
    dc = compare(np.array([periodic.mean()]), np.array([mean_expected]), atol=1e-8)
    np.savez_compressed(
        output / "terrain.npz",
        dem_m=z,
        x=x,
        y=y,
        stations=obs,
        geoana_attraction_mgal=direct,
        airy_periodic_mgal=periodic,
    )
    return dict(
        passed=all(c["passed"] for c in checks.values())
        and finite["passed"]
        and dc["passed"],
        cells=z.size,
        stations=len(obs),
        crs="EPSG:32734",
        height_reference="MSL retained; no vertical transformation",
        land_cells=int((z > 0).sum()),
        water_cells=int((z < 0).sum()),
        adaptive=checks,
        airy_finite_geoana=finite,
        airy_periodic_dc=dc,
        airy_fft_recipe=recipe,
        scope="ETOPO1 coastal DEM projected to a finite Cartesian model. Independent Geoana prism reference, explicit upward/downward and SI/mGal conversion. Bounds cover tree truncation only. Airy finite and periodic conditions checked separately; no geologically calibrated isostatic residual.",
    )


def survey_case(paths, output):
    import pandas as pd
    from terraworkbench_core.survey_store import SurveyStore
    from terraworkbench_core.survey_text_import import inspect_text
    from terraworkbench_core.channel_filters import ChannelFilterOptions
    from scipy.ndimage import uniform_filter1d

    text = output / "britain.csv"
    with lzma.open(paths["britain"], "rb") as incoming, text.open("xb") as stream:
        for block in iter(lambda: incoming.read(1 << 20), b""):
            stream.write(block)
    options, _, _ = inspect_text(text)
    # The publisher's line_and_segment channel is explicit metadata, not an
    # inferred time or uniformly spaced distance axis (contour digitization).
    for column in options.columns:
        if column.name == "line_and_segment":
            column.role = "line"
        if column.name == "total_field_anomaly_nt":
            column.unit = "nT"
    store = SurveyStore(output / "britain_workspace", create=True)
    database = store.import_file(
        text,
        text_options=options,
        metadata={
            "horizontal_crs": "EPSG:4326",
            "height_datum": "unspecified",
            "dataset": "10.5281/zenodo.5879260",
        },
    )
    store.configure_geometry(database, "longitude", "latitude", "EPSG:4326")
    store.filter_channel(
        database,
        "total_field_anomaly_nt",
        "mag_mean5_samples",
        ChannelFilterOptions(method="mean", group="line_and_segment", window=5),
    )
    arrays = {
        name: []
        for name in ("line_and_segment", "total_field_anomaly_nt", "mag_mean5_samples")
    }
    batches = 0
    for batch in store.batches(database, list(arrays)):
        batches += 1
        for i, name in enumerate(arrays):
            arrays[name].append(batch.column(i).to_numpy(zero_copy_only=False))
    arrays = {k: np.concatenate(v) for k, v in arrays.items()}
    original = pd.read_csv(paths["britain"])
    np.testing.assert_array_equal(
        arrays["total_field_anomaly_nt"], original.total_field_anomaly_nt
    )
    np.testing.assert_array_equal(arrays["line_and_segment"], original.line_and_segment)
    if len(original) != 541508:
        raise AssertionError("Unexpected pinned Britain row count")
    groups = arrays["line_and_segment"]
    bounds = np.r_[0, np.flatnonzero(groups[1:] != groups[:-1]) + 1, len(groups)]
    expected = np.full(len(groups), np.nan)
    for start, stop in zip(bounds[:-1], bounds[1:]):
        if stop - start >= 5:
            expected[start + 2 : stop - 2] = uniform_filter1d(
                arrays["total_field_anomaly_nt"][start:stop].astype(float), size=5
            )[2:-2]
    comparison = compare(arrays["mag_mean5_samples"], expected, atol=1e-8)
    lineage = store.channel_pipeline(database, "mag_mean5_samples")
    if not lineage["edges"]:
        raise AssertionError("Missing channel processing provenance")
    return dict(
        passed=comparison["passed"],
        rows=len(groups),
        contiguous_segments=len(bounds) - 1,
        batches=batches,
        assigned_crs="EPSG:4326",
        output_unit="nT",
        lineage_nodes=len(lineage["nodes"]),
        mean5=comparison,
        scope="All digitized rows; sample-domain smoothing split by published contiguous IDs. Irregular contour samples are not treated as uniformly spaced distance or time.",
    )


def radiometry_case(paths, output):
    """Explicit development-only adapter, absent from public source exports."""
    from importlib import import_module
    adapter = import_module("scripts.private_" + "tellus")
    return adapter.radiometry_case(paths, output)


def spectra_case(paths, output):
    import pandas as pd
    from scipy.optimize import lsq_linear
    from scipy.linalg import svdvals
    from terraworkbench_core.radiometric_spectra import (
        energy_rebin,
        integrate_energy_windows,
        fit_full_spectrum,
        poisson_nasvd,
    )

    comparisons = {}
    fits = {}
    measured_spectra = 0
    nasvd_diagnostics = {}
    with zipfile.ZipFile(paths["spectra"]) as archive:
        data_files = [
            m.filename
            for m in archive.infolist()
            if "/Data/" in m.filename and m.filename.endswith(".csv")
        ]
    for name in data_files:
        raw = member_bytes(paths["spectra"], name).decode()
        exposure = np.atleast_1d(
            ast.literal_eval(raw.splitlines()[0].split("=", 1)[1].strip())
        )
        frame = pd.read_csv(io.StringIO(raw), comment="#")
        centers = frame.iloc[:, 0].to_numpy()
        counts = frame.iloc[:, 1:].to_numpy(float).T
        if len(exposure) != len(counts) or not np.all(
            np.isfinite(exposure) & (exposure > 0)
        ):
            raise AssertionError("Invalid measured exposure metadata")
        measured_spectra += len(counts)
        mid = (centers[1:] + centers[:-1]) / 2
        edges = np.r_[
            centers[0] - (mid[0] - centers[0]),
            mid,
            centers[-1] + (centers[-1] - mid[-1]),
        ]
        target = edges[::4]
        if target[-1] != edges[-1]:
            target = np.r_[target, edges[-1]]
        result = energy_rebin(counts, edges, target)
        expected = np.add.reduceat(counts, np.arange(0, counts.shape[-1], 4), axis=-1)
        comparisons[name + "_rebin"] = compare(result["counts"], expected, atol=1e-8)
        if len(counts) >= 3:
            denoised = poisson_nasvd(counts, 2, exposure_s=exposure)
            full_rank = poisson_nasvd(counts, min(counts.shape), exposure_s=exposure)
            identity = compare(full_rank["counts"], counts, atol=1e-8, rtol=1e-11)
            rate = counts.sum(axis=0) / exposure.sum()
            active = rate > 0
            scale = np.sqrt(exposure[:, None] * rate[active])
            singular = svdvals(counts[:, active] / scale)
            weighted_residual = np.sum(
                ((counts[:, active] - denoised["counts"][:, active]) / scale) ** 2
            )
            optimal = compare(
                np.array([weighted_residual]),
                np.array([np.sum(singular[2:] ** 2)]),
                atol=1e-7,
                rtol=1e-10,
            )
            nasvd_diagnostics[name] = dict(
                full_rank_identity=identity,
                rank_two_optimum=optimal,
                selected_rank=2,
                negative_reconstructed_bins=int(denoised["negative"].sum()),
            )
    for case in ("HF_Cs", "HF_Ba"):
        prefix = "data_v1_1_0/" + case
        raw = member_bytes(paths["spectra"], prefix + "/Data/gross_all.csv").decode()
        exposure = float(raw.splitlines()[0].split("=")[1])
        frame = pd.read_csv(io.StringIO(raw), comment="#")
        centers = frame.iloc[:, 0].to_numpy()
        counts = frame.iloc[:, 1].to_numpy(float)
        mid = (centers[1:] + centers[:-1]) / 2
        edges = np.r_[
            centers[0] - (mid[0] - centers[0]),
            mid,
            centers[-1] + (centers[-1] - mid[-1]),
        ]
        target = edges[::4]
        if target[-1] != edges[-1]:
            target = np.r_[target, edges[-1]]
        result = energy_rebin(counts, edges, target)
        expected = np.add.reduceat(counts, np.arange(0, len(counts), 4))
        comparisons[case + "_conservation"] = compare(
            result["counts"], expected, atol=1e-8
        )
        windows = integrate_energy_windows(
            counts, edges, [[1370.0, 1570.0], [1660.0, 1860.0], [2410.0, 2810.0]]
        )
        # Independent scalar interval-overlap integration, not Core weights.
        direct = [
            sum(
                float(c) * max(0.0, min(b, hi) - max(a, lo)) / (b - a)
                for c, a, b in zip(counts, edges[:-1], edges[1:])
            )
            for lo, hi in [[1370.0, 1570.0], [1660.0, 1860.0], [2410.0, 2810.0]]
        ]
        comparisons[case + "_windows"] = compare(windows["counts"], direct, atol=1e-8)
        labels = ["Cs" if case == "HF_Cs" else "Ba", "K", "U", "Th", "Rn"]
        templates = []
        template_units = {}
        supported = (centers >= 100.0) & (centers <= 2800.0)
        for name in labels:
            template = pd.read_csv(
                io.BytesIO(
                    member_bytes(
                        paths["spectra"], prefix + "/Templates/" + name + ".csv"
                    )
                )
            )
            # Published templates are per second, per keV and per source-unit.
            # Interpolate their densities onto measured bin centers; do not
            # extrapolate outside published support or call this detector calibration.
            tx, ty = template.iloc[:, 0].to_numpy(), template.iloc[:, 1].to_numpy()
            template_units[name] = str(template.columns[1])
            supported &= (centers >= tx.min()) & (centers <= tx.max())
            templates.append(np.interp(centers, tx, ty) * np.diff(edges) * exposure)
        a = np.column_stack(templates)[supported]
        y = counts[supported]
        # Declared diagnostic Gaussian weights with an explicit one-count floor.
        # They are not the paper's Poisson Bayesian likelihood or calibration errors.
        std = np.sqrt(np.maximum(y, 1.0))
        fitted = fit_full_spectrum(y, a, count_std=std)
        reference = lsq_linear(
            a / std[:, None], y / std, bounds=(0, np.inf), method="bvls", tol=1e-12
        )
        check = compare(fitted["predicted"], a @ reference.x, atol=1e-6, rtol=1e-9)
        gradient = (a / std[:, None]).T @ ((fitted["predicted"] - y) / std)
        kkt_violation = np.where(
            fitted["active"], abs(gradient), np.maximum(-gradient, 0)
        )
        fits[case] = dict(
            prediction_reference=check,
            labels=labels,
            template_density_units=template_units,
            fitted_energy_keV=[
                float(centers[supported].min()),
                float(centers[supported].max()),
            ],
            coefficients=fitted["coefficients"].tolist(),
            chi_squared=fitted["chi_squared"],
            reduced_chi_squared=fitted["chi_squared"]
            / max(1, len(y) - int(fitted["active"].sum())),
            bins=len(y),
            live_time_s=exposure,
            maximum_kkt_violation=float(np.max(kkt_violation)),
        )
    return dict(
        passed=all(m["passed"] for m in comparisons.values())
        and all(f["prediction_reference"]["passed"] for f in fits.values())
        and all(
            n["full_rank_identity"]["passed"] and n["rank_two_optimum"]["passed"]
            for n in nasvd_diagnostics.values()
        ),
        measured_files=len(data_files),
        measured_spectra=measured_spectra,
        count_unit="counts",
        nasvd_diagnostics=nasvd_diagnostics,
        comparisons=comparisons,
        template_fit_diagnostics=fits,
        scope="Measured hover-flight spectra and published simulated templates, independent BVLS optimizer reference. Activity coefficients are conditional diagnostics, not certified activities or reproduction of the publication's Bayesian estimates. Rn is a spectral template, not validation of paired-detector atmospheric reconstruction.",
    )


CASES = {
    "gravity": gravity_case,
    "magnetic": magnetic_case,
    "interpolation": interpolation_case,
    "terrain": terrain_case,
    "survey": survey_case,
    "radiometry": radiometry_case,
    "spectra": spectra_case,
}
CASE_DATASETS = {
    "gravity": ("bushveld", "southern_africa"),
    "magnetic": ("lightning",),
    "interpolation": ("lightning",),
    "terrain": ("topography",),
    "survey": ("britain",),
    "radiometry": ("tellus",),
    "spectra": ("spectra",),
}


def publication_report(report):
    """Export every terminal outcome, retaining failures without local paths."""
    if report.get("status") not in ("passed", "failed"):
        raise ValueError("Only completed evidence can be published")
    public = json.loads(json.dumps(report, allow_nan=False))
    locations = [str(ROOT)]
    for dataset in public.get("datasets", {}).values():
        if dataset.get("cache_path"):
            locations.extend(
                [dataset["cache_path"], str(Path(dataset["cache_path"]).parent)]
            )
        dataset.pop("cache_path", None)

    def scrub(value):
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items()}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        if isinstance(value, str):
            for location in sorted(locations, key=len, reverse=True):
                if len(location) > 3:
                    value = value.replace(location, "[local path]")
            return re.sub(
                r"(?<![A-Za-z])[A-Za-z]:[\\/][^\s\"']+", "[local path]", value
            )
        return value

    public = scrub(public)
    return public


def run(cache, output, *, offline=False, cases=None, allow_unconfirmed_data=False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "status": "running",
        "utc": datetime.now(timezone.utc).isoformat(),
        "datasets": {},
        "cases": {},
        "versions": {},
        "python": platform.python_version(),
        "platform": platform.system() + " " + platform.release(),
        "limits": [
            "No complete-geophysics or proprietary-parity claim.",
            "No calibrated airborne paired-detector radon field reference was validated.",
            "No independent field truth for minimum-curvature or inverse geological models.",
        ],
    }
    for library in (
        "numpy",
        "scipy",
        "harmonica",
        "boule",
        "pandas",
        "xarray",
        "netCDF4",
        "pyarrow",
        "pyproj",
        "rasterio",
        "geoana",
    ):
        try:
            report["versions"][library] = version(library)
        except PackageNotFoundError:
            report["versions"][library] = "unavailable"
    report["source_sha256"] = {
        p.relative_to(ROOT).as_posix(): digest(p)
        for p in (ROOT / "terraworkbench_core").glob("*.py")
    }
    report["runner_sha256"] = digest(__file__)
    report["manifest_sha256"] = digest(MANIFEST)
    provenance = repository_provenance(ROOT)
    report["git_head"] = provenance["commit"]
    report["git_dirty"] = provenance["dirty"]
    report["source_provenance"] = provenance

    def save():
        (output / "report.json").write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )

    save()
    try:
        sources = json.loads(MANIFEST.read_text(encoding="utf-8"))
        paths = {}
        selected = list(cases) if cases is not None else [
            name for name in CASES
            if all(key in sources and sources[key].get("enabled_by_default", True)
                   for key in CASE_DATASETS[name])
        ]
        for name in selected:
            for key in CASE_DATASETS[name]:
                if key not in sources:
                    raise ValueError("Dataset is not distributed in this edition: " + key)
                if not sources[key].get("enabled_by_default", True) and not allow_unconfirmed_data:
                    raise ValueError("Dataset rights are unconfirmed; explicit development opt-in required")
        required = {key for case in selected for key in CASE_DATASETS[case]}
        for key, source in sources.items():
            if key not in required:
                continue
            paths[key] = fetch(cache, source, offline=offline)
            report["datasets"][key] = dict(source, cache_path=str(paths[key]))
        save()
        for name in selected:
            start = time.perf_counter()
            try:
                value = CASES[name](paths, output)
                value["status"] = "passed" if value["passed"] else "failed"
            except Exception as error:
                value = dict(status="failed", error=repr(error))
            value["seconds"] = time.perf_counter() - start
            report["cases"][name] = value
            save()
            print(json.dumps({"case": name, **value}), flush=True)
        report["status"] = (
            "passed"
            if all(c["status"] == "passed" for c in report["cases"].values())
            else "failed"
        )
    except Exception as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        save()
        (output / "report.public.json").write_text(
            json.dumps(publication_report(report), indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--case", choices=CASES, action="append")
    parser.add_argument("--allow-unconfirmed-data", action="store_true",
                        help="Development-only opt-in; does not grant redistribution rights")
    args = parser.parse_args()
    report = run(args.cache, args.output, offline=args.offline, cases=args.case,
                 allow_unconfirmed_data=args.allow_unconfirmed_data)
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
