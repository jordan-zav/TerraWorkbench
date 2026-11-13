"""Licensed Tellus A9 concentration benchmark; no raw survey data bundled."""
import numpy as np
from scripts.benchmark_public_processing import member_bytes, compare

TELLUS_A9_ATTRIBUTION = 'Contains Irish Public Sector Data (Geological Survey Ireland) licensed under a Creative Commons Attribution 4.0 International (CC BY 4.0) licence'
TELLUS_A9_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"

def radiometry_case(paths, output):
    from terraworkbench_core.survey_text_import import inspect_text
    from terraworkbench_core.survey_store import SurveyStore
    from terraworkbench_core.radiometry import (
        ternary_rgb,
        safe_ratio,
        terrestrial_dose_rate,
        channel_qc,
    )

    text = output / "tellus.xyz"
    payload = member_bytes(paths["tellus"], "RAD_A9_DATA_2022/RAD_A9_2022_WEB.XYZ")
    text.write_bytes(payload)
    options, warnings, _ = inspect_text(text)
    for column in options.columns:
        if column.name == "C_POT_DLU":
            column.unit = "percent"
        if column.name in ("C_URA_DLU", "C_THO_DLU"):
            column.unit = "ppm"
    store = SurveyStore(output / "tellus_workspace", create=True)
    database = store.import_file(
        text,
        text_options=options,
        metadata={
            "horizontal_crs": "EPSG:2157",
            "height_reference": "MSL",
            "dataset": "GSI Tellus A9 download labelled 2022",
            "license": "CC BY 4.0",
            "license_url": TELLUS_A9_LICENSE_URL,
            "attribution": TELLUS_A9_ATTRIBUTION,
        },
    )
    store.configure_geometry(database, "ITM_X", "ITM_Y", "EPSG:2157")
    columns = ["C_POT_DLU", "C_URA_DLU", "C_THO_DLU"]
    arrays = [[] for _ in columns]
    lines, dates = set(), set()
    for batch in store.batches(database, [*columns, "LINE", "DATE"]):
        for i in range(3):
            arrays[i].append(batch.column(i).to_numpy(zero_copy_only=False))
        lines.update(batch.column(3).to_pylist())
        dates.update(batch.column(4).to_pylist())
    k, u, th = [np.concatenate(a) for a in arrays]
    numeric = (
        line
        for line in payload.decode("utf-8-sig").splitlines()
        if line.strip()
        and not line.lstrip().startswith("/")
        and not (len(line.split()) == 2 and line.split()[0] in ("Line", "Tie"))
    )
    independent = np.genfromtxt(numeric, missing_values="*", filling_values=np.nan)
    if independent.shape != (251233, 21):
        raise AssertionError("Unexpected pinned Tellus rows/channels")
    np.testing.assert_array_equal(np.column_stack([k, u, th]), independent[:, 18:21])
    rgb = ternary_rgb(k, u, th, normalize=True)
    # Explicit scalar formula independently checks concentration products.
    ratio = safe_ratio(u, th, minimum_denominator=0.1)
    reference = np.full(len(k), np.nan)
    valid = np.isfinite(u) & np.isfinite(th) & (abs(th) > 0.1)
    reference[valid] = u[valid] / th[valid]
    ratios = compare(ratio, reference, atol=1e-12)
    dose = compare(
        terrestrial_dose_rate(k, u, th), 13.078 * k + 5.675 * u + 2.494 * th, atol=1e-10
    )
    total = np.nansum(rgb, axis=0)
    colored = np.isfinite(rgb).all(axis=0)
    rounding_error = float(np.max(abs(total[colored] - 255)))
    np.savez_compressed(
        output / "radiometry_products.npz",
        normalized_rgb=rgb,
        dose=terrestrial_dose_rate(k, u, th),
    )
    return dict(
        attribution=TELLUS_A9_ATTRIBUTION,
        license="CC BY 4.0",
        license_url=TELLUS_A9_LICENSE_URL,
        passed=ratios["passed"] and dose["passed"] and rounding_error <= 1.5,
        rows=len(k),
        assigned_crs="EPSG:2157",
        line_ids=len(lines),
        date_values=sorted(dates),
        unit_k="percent",
        unit_u_th="ppm",
        ratios=ratios,
        dose=dose,
        normalized_rgb_max_sum_rounding=rounding_error,
        qc={name: channel_qc(value) for name, value in zip(columns, (k, u, th))},
        importer_warnings=warnings,
        scope="Published corrected concentrations only. No inverse recovery of undocumented calibration coefficients, no validation of atmospheric radon correction. Archive/report label and date channels are recorded as published, without repairing their discrepancy.",
    )
