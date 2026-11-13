"""Convert GDB files recursively using public GX APIs, with verification by default."""

import argparse
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qgis_plugin.gdb_archive_gx import convert_gdb_archive as convert_file  # noqa: E402


def main(argv=None):
    """Run a batch, logging every failure and stopping on sign-in/license requests."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verify", action=argparse.BooleanOptionalAction, default=True)
    options = parser.parse_args(argv)
    options.output.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=options.output / "conversion.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    from qgis_plugin.geosoft_runtime import conversion_notice, find_seequent_connector

    print(
        conversion_notice("en", connector_missing=find_seequent_connector() is None),
        flush=True,
    )
    source = options.input.resolve()
    files = (
        [source]
        if source.is_file()
        else sorted(
            p for p in source.rglob("*") if p.is_file() and p.suffix.lower() == ".gdb"
        )
    )
    results = []
    for path in files:
        relative = path.relative_to(source) if source.is_dir() else Path(path.name)
        destination = options.output / relative.parent / (path.stem + ".twarchive")
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = {"source": str(path), "destination": str(destination)}
        try:
            report = convert_file(path, destination, verify=options.verify)
            result.update(
                status=report["status"], verified=report["verified"], report=report
            )
        except Exception as error:
            result.update(
                status="failed",
                verified=False,
                error=f"{type(error).__name__}: {error}",
            )
        logging.info("%s", json.dumps(result, ensure_ascii=False))
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if result.get("error", "").startswith("GXAccessRequired:") or result.get(
            "report", {}
        ).get("access_required"):
            result["batch_stopped"] = "No sign-in or license reservation accepted"
            break
    (options.output / "batch-report.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return 0 if results and all(r["verified"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
