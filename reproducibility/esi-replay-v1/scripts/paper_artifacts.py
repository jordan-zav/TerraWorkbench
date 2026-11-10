"""Make publication tables and labelled figures from the frozen campaign."""

import argparse
import csv
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def build(run, cache, target):
    from scripts.paper_campaign import leaves, dump

    run, cache, target = Path(run), Path(cache), Path(target)
    target.mkdir(parents=True, exist_ok=False)
    record = json.loads((run / "campaign.json").read_text(encoding="utf-8"))
    dump(target / "campaign.json", record)
    for name in ("historical_registry.json", "historical_metrics.csv"):
        shutil.copyfile(run / name, target / name)
    lines = [
        "# Frozen reproducibility replay: results",
        "",
        "[Paper index](../README.md)",
        "",
        "This replay uses previously explored datasets. It is not new blind confirmation. All attempted outcomes are retained; reference disagreement, data prediction and model recovery have different meanings.",
        "",
        "Protocol: "
        + record["protocol_id"]
        + ". Execution source: "
        + record["git_head"]
        + ".",
        "",
        "[Complete current record](campaign.json) · [Current metric index](current_metrics.csv) · [Historical registry](historical_registry.json) · [All indexed historical metrics](historical_metrics.csv)",
        "",
        "## Primary real-data workflows",
        "",
        "| Workflow | Status | Scope |",
        "| --- | --- | --- |",
    ]
    primary = record["outcomes"].get("processing", {})
    for name, case in primary.get("cases", {}).items():
        lines.append(
            "| "
            + name
            + " | "
            + case["status"]
            + " | "
            + case.get("scope", case.get("error", "see record")).replace("|", "/")
            + " |"
        )
    lines += [
        "",
        "## Numerical comparisons and interpolation diagnostics",
        "",
        "| JSON pointer | RMS/error value | Unit | Meaning |",
        "| --- | ---: | --- | --- |",
    ]

    def comparisons(value, pointer="", inherited_unit="see record"):
        if not isinstance(value, dict):
            return
        unit = value.get("unit", inherited_unit)
        for key in ("rms_error", "rms_nt"):
            if key in value:
                meaning = (
                    "Reference-operator disagreement"
                    if key == "rms_error"
                    else "Prediction against already gridded input; descriptive, not geological truth"
                )
                lines.append(
                    f"| {pointer}/{key} | {value[key]:.8g} | {'nT' if key == 'rms_nt' else unit} | {meaning} |"
                )
        for key, item in value.items():
            if isinstance(item, dict):
                comparisons(item, pointer + "/" + key, unit)

    comparisons(primary.get("cases", {}), "/outcomes/processing/cases")
    secondary = record["outcomes"].get("tutorial_inversion", {})
    lines += [
        "",
        "## Secondary tutorial inversion: simulated examples",
        "",
        "These are pinned simulated tutorial observations, not new field surveys. Thresholds WRMS ≤ 2 training and ≤ 3 withheld are inherited engineering regression gates. The known every-fifth-station split does not establish independent regional validation or model recovery.",
        "",
        "| Case | Set | n | RMSE | Unit | WRMS | NRMSE/std (%) |",
        "| --- | --- | ---: | ---: | --- | ---: | ---: |",
    ]
    for case in secondary.get("cases", []):
        for short, label, count, wrms in (
            ("train", "training", case["training"], case["training_wrms"]),
            ("held", "withheld", case["withheld"], case["withheld_wrms"]),
        ):
            metric = case["prediction_metrics"][short]
            percentage = metric["nrmse_std_percent"]
            displayed = "undefined" if percentage is None else f"{percentage:.6g}"
            lines.append(
                f"| {case['kind']} | {label} | {count} | {metric['rmse']:.8g} | {case['prediction_metrics_unit']} | {wrms:.6g} | {displayed} |"
            )
    lines += [
        "",
        "NRMSE uses population standard deviation of observed target on the named evaluation set; it is not percentage geological accuracy. Constant-target values are undefined. Timing is observational, not a controlled performance comparison.",
        "",
        "## Historical evidence",
        "",
        "The historical registry preserves source-record hashes and links back to the original dates. CSV rows identify values by JSON pointer. Nested booleans, intentionally failed controls and solver diagnostics are not independent experiments and must not be pooled into a success percentage.",
    ]
    with (target / "current_metrics.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.writer(stream)
        writer.writerow(["json_pointer", "value_json"])
        writer.writerows(
            (pointer, json.dumps(value, ensure_ascii=False))
            for pointer, value in leaves(record)
        )
    if primary.get("cases", {}).get("magnetic", {}).get("status") == "passed":
        import numpy as np
        import xarray as xr
        import harmonica as hm
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        grid = xr.load_dataarray(cache / "lightning-creek-magnetic-grid.nc")
        with np.load(run / "processing/magnetic.npz", allow_pickle=False) as arrays:
            transformed = arrays["upward_250m"]
        reference = hm.upward_continuation(grid, 250).values
        fig, axes = plt.subplots(1, 3, figsize=(14, 4.4), constrained_layout=True)
        extent = [
            float(grid.easting.min()),
            float(grid.easting.max()),
            float(grid.northing.min()),
            float(grid.northing.max()),
        ]
        for ax, data, title in zip(
            axes,
            (grid.values, transformed, transformed - reference),
            (
                "Published gridded anomaly",
                "Upward continuation: +250 m",
                "Core minus Harmonica reference",
            ),
        ):
            limit = max(float(np.nanmax(abs(data))), np.finfo(float).eps)
            view = ax.imshow(
                data,
                origin="lower",
                extent=extent,
                cmap="RdBu_r",
                vmin=-limit,
                vmax=limit,
            )
            fig.colorbar(view, ax=ax, label="nT")
            ax.set(title=title, xlabel="Easting (m)", ylabel="Northing (m)")
            ax.ticklabel_format(axis="both", style="plain", useOffset=False)
        fig.suptitle(
            "Lightning Creek: real published grid; reference disagreement is not geological error"
        )
        fig.savefig(target / "lightning_workflow.png", dpi=160)
        plt.close(fig)
        lines += [
            "",
            "## Real-data processing figure",
            "",
            "![Lightning Creek processing and reference comparison](lightning_workflow.png)",
            "",
            "Published 50 m Lightning Creek grid and a 250 m upward continuation, with separate symmetric scales per panel. The right panel shows numerical reference disagreement, not field prediction residual. Source: Geophysical Acquisition & Processing Section (2019), Geoscience Australia P1029, prepared by Uieda and Gomez / Fatiando a Terra, [Zenodo 7079711](https://doi.org/10.5281/zenodo.7079711), CC-BY source attribution. This replay does not reprocess raw flight data.",
        ]
    (target / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.run, args.cache, args.output)
