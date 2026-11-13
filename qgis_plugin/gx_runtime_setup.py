"""Prepare the official full GX redistributable without a desktop installer."""

import argparse
import hashlib
import json
import os
import importlib
import shutil
from pathlib import Path, PurePosixPath
import site
import sys
import tempfile
import uuid
import zipfile

GX_REDIST_URL = "https://github.com/GeosoftInc/gxcore/releases/download/v2024.2/RELEASE_2024.2.0_26_20241130_redist_full.zip"
GX_REDIST_BYTES = 362081059


def _runtime_checksum():
    """Read the public vendor checksum in standard sha256sum resource format."""
    resource = Path(__file__).resolve().parents[1] / "assets/runtime/SHA256SUMS"
    checksum, filename = resource.read_text(encoding="ascii").strip().split("  ")
    if (
        len(checksum) != 64
        or any(character not in "0123456789abcdef" for character in checksum)
        or filename != GX_REDIST_URL.rsplit("/", 1)[-1]
    ):
        raise ValueError("Invalid bundled GX runtime checksum")
    return checksum


GX_REDIST_SHA256 = _runtime_checksum()
GX_LICENSE_URL = "https://raw.githubusercontent.com/GeosoftInc/gxcore/v2024.2/LICENSE"
GX_LICENSE_TERMS = (
    "https://geosoftgxdev.atlassian.net/wiki/spaces/GD/pages/2359406/License"
)
GX_THIRD_PARTY_TERMS = "https://geosoftgxdev.atlassian.net/wiki/spaces/GD/pages/2359438/Third-Party+Licenses"


def validate_runtime_configuration(root):
    """Reject incomplete GX configuration before any native library is loaded."""
    data = (Path(root) / "geosoft.redist").read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("geosoft.redist must use UTF-8 without BOM")
    lines = data.decode("utf-8").splitlines()
    if len(lines) != 2 or data != ("\r\n".join(lines) + "\r\n").encode("utf-8"):
        raise ValueError("geosoft.redist must contain two CRLF-terminated paths")
    paths = [Path(line) for line in lines]
    for path in paths:
        if not path.is_absolute() or not path.is_dir():
            raise ValueError("GX configuration folder does not exist: " + str(path))
        with tempfile.TemporaryFile(dir=path) as stream:
            stream.write(b"GX configuration write check")
    return {"user_dir": str(paths[0]), "temp_dir": str(paths[1])}


def ensure_runtime_configuration(root, *, target=None):
    """Create or repair persistent, installer-owned user/temp directories."""
    root = Path(root).resolve()
    if target is None:
        target = next((parent for parent in root.parents if parent.name == "_gx_runtime"), root)
    target = Path(target).resolve()
    if root != target and target not in root.parents:
        raise ValueError("Runtime configuration is outside its managed folder")
    user, temporary = target / "user", target / "temp"
    user.mkdir(parents=True, exist_ok=True)
    temporary.mkdir(parents=True, exist_ok=True)
    expected = f"{user}\r\n{temporary}\r\n".encode("utf-8")
    config = root / "geosoft.redist"
    if not config.is_file() or config.read_bytes() != expected:
        pending = root / ("geosoft.redist-" + uuid.uuid4().hex + ".tmp")
        pending.write_bytes(expected)
        pending.replace(config)
    return validate_runtime_configuration(root)


DOTNET_VERSION = "6.0.36"
DOTNET_ASSETS = (
    ("Runtime", "dotnet-runtime-6.0.36-win-x64.zip", 33057872),
    ("WindowsDesktop", "windowsdesktop-runtime-6.0.36-win-x64.zip", 36315065),
)
DOTNET_BYTES = sum(asset[2] for asset in DOTNET_ASSETS)
DOTNET_SOURCE = "https://builds.dotnet.microsoft.com/dotnet"
DOTNET_FRAMEWORKS = ("Microsoft.NETCore.App", "Microsoft.WindowsDesktop.App")


def extract_runtime_zip(archive, destination):
    with zipfile.ZipFile(archive) as bundle:
        if sum(info.file_size for info in bundle.infolist()) > 2 * 1024**3:
            raise ValueError("Unexpected redistributable extraction size")
        for info in bundle.infolist():
            relative = PurePosixPath(info.filename)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or ":" in info.filename
                or "\\" in info.filename
                or (info.external_attr >> 16) & 0o170000 == 0o120000
            ):
                raise ValueError("Unsafe redistributable path")
        bundle.extractall(destination)


def dotnet_checksums():
    resource = Path(__file__).resolve().parents[1] / "assets/runtime/SHA512SUMS"
    return {name: digest for digest, name in
            (line.split("  ", 1) for line in resource.read_text(encoding="ascii").splitlines())}


def complete_dotnet(root):
    return all(any((root / "shared" / framework).glob("6.*")) for framework in DOTNET_FRAMEWORKS)


def dotnet_root(target, environment=None):
    env = os.environ if environment is None else environment
    for location in (env.get("DOTNET_ROOT_X64"), env.get("DOTNET_ROOT"),
                     str(Path(env.get("ProgramFiles", "C:/Program Files")) / "dotnet")):
        if location and complete_dotnet(Path(location)):
            return Path(location)
    target = Path(target).resolve()
    try:
        record = json.loads((target / "dotnet6.json").read_text(encoding="utf-8"))
        root = (target / record["root"]).resolve()
        if (root.parent == target and root.name.startswith("dotnet6-") and complete_dotnet(root)
                and (root / "dotnet.exe").is_file() and (root / "LICENSE.txt").is_file()
                and record["checksums"] == dotnet_checksums()):
            return root
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def dotnet_environment(target, environment=None):
    root = dotnet_root(target, environment)
    if root is None:
        return {}
    return {"DOTNET_ROOT": str(root), "DOTNET_ROOT_X64": str(root),
            "DOTNET_MULTILEVEL_LOOKUP": "0", "DOTNET_DISABLE_GUI_ERRORS": "1"}


def prepare_dotnet(target):
    """Stage both verified runtime archives and publish one atomic marker."""
    target = Path(target).resolve()
    existing = dotnet_root(target)
    if existing is not None:
        return existing
    site.addsitedir(str(target.parent))
    requests = importlib.import_module("requests")
    target.mkdir(parents=True, exist_ok=True)
    checksums = dotnet_checksums()
    root = target / ("dotnet6-" + uuid.uuid4().hex)
    root.mkdir()
    received_total = 0
    try:
        with tempfile.TemporaryDirectory(dir=target) as temp:
            for family, name, size in DOTNET_ASSETS:
                archive = Path(temp) / name
                digest = hashlib.sha512()
                received = 0
                with requests.get(f"{DOTNET_SOURCE}/{family}/{DOTNET_VERSION}/{name}",
                                  timeout=60, stream=True) as response, archive.open("xb") as stream:
                    response.raise_for_status()
                    for chunk in response.iter_content(1024 * 1024):
                        received += len(chunk)
                        if received > size:
                            raise ValueError("Unexpected .NET runtime download size")
                        digest.update(chunk)
                        stream.write(chunk)
                        print(f".NET runtime: {received_total + received}/{DOTNET_BYTES} bytes", flush=True)
                if received != size or digest.hexdigest() != checksums[name]:
                    raise ValueError("Official .NET runtime size/SHA-512 mismatch")
                extract_runtime_zip(archive, root)
                received_total += received
        if not (complete_dotnet(root) and (root / "dotnet.exe").is_file()
                and (root / "LICENSE.txt").is_file()):
            raise ValueError("Incomplete .NET 6 portable runtime")
        pending = target / (root.name + ".json")
        pending.write_text(json.dumps({"root": root.name, "checksums": checksums}), encoding="utf-8")
        pending.replace(target / "dotnet6.json")
    except Exception:
        shutil.rmtree(root)
        raise
    return root


def prepare_runtime(target, *, archive=None):
    """Download/verify/extract vendor binaries; do not execute them or sign in."""
    if sys.platform != "win32":
        raise RuntimeError(
            "GDB conversion requires Windows; converted archives open on any platform"
        )
    target = Path(target).resolve()
    previous = []
    if (target / "installed.json").is_file():
        record = json.loads((target / "installed.json").read_text(encoding="utf-8"))
        existing = (target / record["root"]).resolve()
        if target not in existing.parents or not (existing / "bin/geodist.dll").is_file():
            raise ValueError("Existing runtime marker is invalid; files were preserved")
        if record.get("archive_sha256") == GX_REDIST_SHA256:
            ensure_runtime_configuration(existing, target=target)
            return existing
        previous = list(record.get("previous_roots", []))
        previous.append({"root": record["root"], "archive_sha256": record.get("archive_sha256")})
    target.mkdir(parents=True, exist_ok=True)
    # A fresh QGIS process may not have activated this profile's Python packages.
    site.addsitedir(str(target.parent))
    requests = importlib.import_module("requests")
    staging = target / ("install-" + uuid.uuid4().hex)
    staging.mkdir()
    downloaded = archive is None
    if downloaded:
        archive = staging / "download.zip"
        with (
            requests.get(GX_REDIST_URL, timeout=60, stream=True) as response,
            archive.open("xb") as stream,
        ):
            response.raise_for_status()
            received = 0
            for chunk in response.iter_content(1024 * 1024):
                received += len(chunk)
                if received > GX_REDIST_BYTES:
                    raise ValueError("Unexpected redistributable download size")
                stream.write(chunk)
                print(f"GX runtime: {received}/{GX_REDIST_BYTES} bytes", flush=True)
    archive = Path(archive)
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    if (
        archive.stat().st_size != GX_REDIST_BYTES
        or digest.hexdigest() != GX_REDIST_SHA256
    ):
        raise ValueError("Official GX runtime size/SHA-256 mismatch")
    extract_runtime_zip(archive, staging / "files")
    candidates = list((staging / "files").rglob("geodist.dll"))
    roots = [p.parent.parent for p in candidates if p.parent.name == "bin"]
    if len(roots) != 1:
        raise ValueError("Cannot uniquely locate the official redistributable")
    ensure_runtime_configuration(roots[0], target=target)
    if downloaded:
        archive.unlink()
    for name, url in (
        ("LICENSE.txt", GX_LICENSE_URL),
        ("License.html", GX_LICENSE_TERMS),
        ("Third-Party-Licenses.html", GX_THIRD_PARTY_TERMS),
    ):
        with requests.get(url, timeout=60, stream=True) as response:
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > 4 * 1024 * 1024:
                    raise ValueError("Unexpected vendor terms size")
            (target / name).write_bytes(content)
    record = {
        "version": "2024.2",
        "source_url": GX_REDIST_URL,
        "archive_sha256": digest.hexdigest(),
        "root": roots[0].relative_to(target).as_posix(),
        "previous_roots": previous,
    }
    pending = target / ("installed-" + uuid.uuid4().hex + ".json")
    pending.write_text(
        json.dumps(record, indent=2), encoding="utf-8"
    )
    pending.replace(target / "installed.json")
    return roots[0]


def previous_runtime_folders(target):
    """Return only installer-owned previous folders, never the active runtime."""
    target = Path(target).resolve()
    record = json.loads((target / "installed.json").read_text(encoding="utf-8"))
    active = (target / record["root"]).resolve()
    folders = []
    for item in record.get("previous_roots", []):
        relative = PurePosixPath(item["root"])
        if not relative.parts or not relative.parts[0].startswith("install-"):
            continue
        candidate = (target / relative.parts[0]).resolve()
        if candidate.parent != target or candidate == active or candidate in active.parents:
            continue
        if candidate.is_dir() and not (target / relative.parts[0]).is_symlink():
            folders.append(candidate)
    return list(dict.fromkeys(folders))


def remove_previous_runtime(target, folder, *, confirmed=False):
    """Remove one explicitly confirmed, bounded old install; preserve everything else."""
    if not confirmed:
        raise PermissionError("Confirm removal of the previous runtime first")
    target, folder = Path(target).resolve(), Path(folder).resolve()
    if folder.parent != target or folder not in previous_runtime_folders(target):
        raise ValueError("Folder is not a previous managed runtime")
    shutil.rmtree(folder)
    path = target / "installed.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["previous_roots"] = [item for item in record.get("previous_roots", [])
                                if (target / PurePosixPath(item["root"]).parts[0]).resolve() != folder]
    pending = target / ("installed-" + uuid.uuid4().hex + ".json")
    pending.write_text(json.dumps(record, indent=2), encoding="utf-8")
    pending.replace(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--accept-terms", action="store_true", required=True)
    parser.add_argument("--prepare-dotnet", action="store_true")
    options = parser.parse_args()
    try:
        runtime = prepare_runtime(options.target, archive=options.archive)
        if options.prepare_dotnet:
            prepare_dotnet(options.target)
    except (OSError, ValueError, UnicodeError, KeyError, zipfile.BadZipFile) as error:
        result = {"ok": False, "error_code": "runtime_setup_failed", "error": str(error)}
        if "geosoft.redist" in str(error) or "configuration" in str(error):
            result["error_code"] = "invalid_redist_configuration"
        print("TW_GX_CHECK:" + json.dumps(result), flush=True)
        raise SystemExit(2) from None
    print(runtime, flush=True)
    if __package__:
        from .gx_runtime_check import check_in_subprocess
    else:
        from gx_runtime_check import check_in_subprocess

    result = check_in_subprocess(runtime)
    if result["ok"] and result.get("missing_frameworks"):
        result.update(ok=False, error="Required .NET framework is missing", error_code="missing_framework")
    (options.target / "load-check.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("TW_GX_CHECK:" + json.dumps(result), flush=True)
    raise SystemExit(0 if result["ok"] else 2)
