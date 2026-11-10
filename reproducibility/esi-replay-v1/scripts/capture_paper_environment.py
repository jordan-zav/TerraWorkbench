"""Observe dependency versions after analysis; never install or change packages."""

import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def capture(folder):
    folder = Path(folder)
    campaign = json.loads((folder / "campaign.json").read_text(encoding="utf-8"))
    roots = list(campaign["versions"]) + [
        "pandas",
        "xarray",
        "netCDF4",
        "pyproj",
        "matplotlib",
    ]
    pending, packages, unavailable = list(roots), {}, []
    while pending:
        name = canonicalize_name(pending.pop())
        if name in packages or name in unavailable:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            unavailable.append(name)
            continue
        packages[name] = dist.version
        for entry in dist.requires or ():
            requirement = Requirement(entry)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
    for name, expected in campaign["versions"].items():
        if (
            expected != "unavailable"
            and packages.get(canonicalize_name(name)) != expected
        ):
            raise ValueError("Analysis environment changed: " + name)
    record = {
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "role": "Post-run observation of the unchanged analysis SDK; not an install action or independently solved cross-platform wheel lock",
        "python": campaign["python"],
        "platform": campaign["platform"],
        "roots": sorted(set(roots)),
        "packages": dict(sorted(packages.items())),
        "unavailable": sorted(unavailable),
        "privacy": "Distribution names/versions only; no direct install URLs, usernames, credentials or workstation paths",
    }
    (folder / "environment.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    files = {}
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.name != "artifact_manifest.json":
            value = path.read_bytes()
            if path.suffix != ".png":
                value = value.replace(b"\r\n", b"\n")
            files[path.name] = hashlib.sha256(value).hexdigest()
    (folder / "artifact_manifest.json").write_text(
        json.dumps(
            {
                "hash_scheme": "SHA256, PNG exact bytes; UTF-8 text normalized to LF",
                "files": files,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("Observed dependency closure:", len(packages), "distributions")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    capture(parser.parse_args().results)
