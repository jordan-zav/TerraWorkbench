"""Freeze and replay a bounded software-paper protocol; keep every outcome."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version, PackageNotFoundError
import json
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "docs/publication"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def dump(path, value):
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def freeze(protocol, target):
    """Refuse to overwrite a freeze. Amendments require a new version/file."""
    target = Path(target)
    if target.exists():
        raise FileExistsError(target)
    config = json.loads(Path(protocol).read_text(encoding="utf-8"))
    paths = list((ROOT / "terraworkbench_core").glob("*.py"))
    paths += [ROOT / name for name in config["implementation_files"]]
    paths += [Path(protocol), PAPER / "data_registry.json"]
    snapshot = {
        "protocol_id": config["protocol_id"],
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "base_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "hash_scheme": "SHA256 text normalized to LF",
        "source_sha256_lf": {
            p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(set(paths))
        },
    }
    dump(target, snapshot)
    return snapshot


def verify(snapshot):
    changed = [
        name
        for name, expected in snapshot["source_sha256_lf"].items()
        if not (ROOT / name).is_file() or sha(ROOT / name) != expected
    ]
    if changed:
        raise ValueError("Frozen source changed: " + ", ".join(changed))


def leaves(value, pointer=""):
    if isinstance(value, dict):
        for key, item in value.items():
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            yield from leaves(item, pointer + "/" + escaped)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from leaves(item, pointer + "/" + str(index))
    else:
        yield pointer, value


def prediction_metrics(observed, predicted):
    """Percent error scale is target variation, never the background field."""
    import numpy as np

    observed, predicted = np.asarray(observed), np.asarray(predicted)
    error = predicted - observed
    rmse = float(np.sqrt(np.mean(error**2)))
    scale = float(np.std(observed, ddof=0))
    return {
        "rmse": rmse,
        "bias": float(error.mean()),
        "target_std_ddof0": scale,
        "nrmse_std_percent": 100 * rmse / scale if scale > 0 else None,
        "undefined_reason": None if scale > 0 else "constant observed target",
    }


def evidence_inventory(output):
    """Index historical metrics losslessly by record and JSON pointer, never vote/count nested gates."""
    records = sorted((ROOT / "docs/validation/records").glob("*.json"))
    registry = []
    rows = []
    for path in records:
        content = json.loads(path.read_text(encoding="utf-8"))
        registry.append(
            {
                "file": path.relative_to(ROOT).as_posix(),
                "sha256_lf": sha(path),
                "role": "historical_development_not_new_blind_validation",
            }
        )
        for pointer, value in leaves(content):
            if re.search(
                r"rms|error|misfit|chi_squared|correlation|bias|passed|status|converg",
                pointer,
                re.I,
            ):
                rows.append(
                    (
                        path.name,
                        pointer,
                        json.dumps(value, ensure_ascii=False, allow_nan=False),
                    )
                )
    dump(
        Path(output) / "historical_registry.json",
        {
            "records": registry,
            "metric_rows": len(rows),
            "interpretation": "Nested diagnostics are not independent methods, experiments or pass-rate denominators. Units and definitions belong to the linked original record.",
        },
    )
    with (Path(output) / "historical_metrics.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.writer(stream)
        writer.writerow(["record", "json_pointer", "value_json"])
        writer.writerows(rows)
    return registry


def run(protocol, snapshot_path, cache, output):
    from scripts import benchmark_public_processing as processing
    from scripts import benchmark_downloaded_potential_fields as inversion

    config = json.loads(Path(protocol).read_text(encoding="utf-8"))
    snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    verify(snapshot)
    output, cache = Path(output), Path(cache)
    output.mkdir(parents=True, exist_ok=False)
    record = {
        "protocol_id": config["protocol_id"],
        "protocol_sha256_lf": sha(protocol),
        "freeze_sha256_lf": sha(snapshot_path),
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "study_role": config["study_role"],
        "python": platform.python_version(),
        "platform": platform.platform(),
        "versions": {},
        "outcomes": {},
    }
    for name in (
        "numpy",
        "scipy",
        "harmonica",
        "boule",
        "pyarrow",
        "simpeg",
        "geoana",
        "choclo",
        "PyWavelets",
    ):
        try:
            record["versions"][name] = version(name)
        except PackageNotFoundError:
            record["versions"][name] = "unavailable"
    dump(output / "campaign.json", record)
    try:
        try:
            result = processing.run(
                cache,
                output / "processing",
                offline=True,
                cases=config["processing_cases"],
            )
            record["outcomes"]["processing"] = processing.publication_report(result)
        except Exception as error:
            raw = output / "processing/report.json"
            result = (
                json.loads(raw.read_text())
                if raw.exists()
                else {"datasets": {}, "cases": {}}
            )
            result.update(status="failed", error=repr(error))
            record["outcomes"]["processing"] = processing.publication_report(result)
        dump(output / "campaign.json", record)
        try:
            result = inversion.run(cache / "acceptance", output / "tutorial_inversion")
            import numpy as np

            for row in result["cases"]:
                with np.load(
                    output / "tutorial_inversion" / (row["kind"] + ".npz"),
                    allow_pickle=False,
                ) as arrays:
                    held = arrays["held_mask"]
                    row["prediction_metrics"] = {
                        name: prediction_metrics(
                            arrays["observed"][mask], arrays["predicted_" + name]
                        )
                        for name, mask in (("train", ~held), ("held", held))
                    }
                    row["prediction_metrics_unit"] = (
                        "mGal" if row["kind"] == "gravity" else "nT"
                    )
            passed = all(
                row["prediction_passed"] and row["all_audited_cg_tolerances_met"]
                for row in result["cases"]
            )
            result.update(
                status="passed" if passed else "failed",
                datasets={},
                data_origin="tutorial_simulated_observations_not_real_field_ground_truth",
            )
            record["outcomes"]["tutorial_inversion"] = processing.publication_report(
                result
            )
        except Exception as error:
            raw = output / "tutorial_inversion/report.json"
            result = json.loads(raw.read_text()) if raw.exists() else {}
            result.update(status="failed", datasets={}, error=repr(error))
            record["outcomes"]["tutorial_inversion"] = processing.publication_report(
                result
            )
    finally:
        record["completed_utc"] = datetime.now(timezone.utc).isoformat()
        record["status"] = (
            "passed"
            if len(record["outcomes"]) == 2
            and all(v["status"] == "passed" for v in record["outcomes"].values())
            else "failed"
        )
        record["source_verified_after_run"] = False
        try:
            verify(snapshot)
            record["source_verified_after_run"] = True
        finally:
            dump(output / "campaign.json", record)
        evidence_inventory(output)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "check", "run"))
    parser.add_argument("--protocol", type=Path, default=PAPER / "protocol-v1.json")
    parser.add_argument("--freeze", type=Path, default=PAPER / "freeze-v1.json")
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.protocol, args.freeze)
    elif args.action == "check":
        verify(json.loads(args.freeze.read_text(encoding="utf-8")))
        print("Frozen protocol and implementation verified")
    else:
        if args.cache is None or args.output is None:
            parser.error("run requires --cache and --output")
        result = run(args.protocol, args.freeze, args.cache, args.output)
        print(json.dumps({"status": result["status"], "output": str(args.output)}))
        raise SystemExit(result["status"] != "passed")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
