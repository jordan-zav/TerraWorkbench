"""Explicit public source boundary and distribution privacy checks."""

from pathlib import Path, PurePosixPath
import hashlib
import re
import subprocess


MANIFEST_NAME = "public_manifest.txt"
PRIVATE_RECORDS = {
    "docs/validation/records/lagged_irls_20261102.json",
    "docs/validation/records/mvi_stability_20261102.json",
    "docs/validation/records/public_processing_20261028.json",
}

DEVELOPMENT_FILES = {
    "scripts/private_tellus.py", "scripts/paper_campaign.py", "scripts/paper_artifacts.py",
    "scripts/capture_paper_environment.py", "tests/test_paper_campaign.py",
    "docs/development/PROCESSING_CORE_OWNERSHIP.md",
    "docs/validation/reports/mvi_diagnostic_plan.md",
}


def repository_provenance(root):
    """Record a real checkout revision, or identify an archive without inventing HEAD."""
    root = Path(root).resolve()
    manifest = root / MANIFEST_NAME
    result = {
        "mode": "archive", "commit": None, "dirty": None,
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest() if manifest.is_file() else None,
    }
    if not (root / ".git").exists():
        return result
    try:
        top = subprocess.run(["git", "--no-optional-locks", "rev-parse", "--show-toplevel"],
                             cwd=root, capture_output=True, text=True)
        if top.returncode or Path(top.stdout.strip()).resolve() != root:
            return result
        head = subprocess.run(["git", "--no-optional-locks", "rev-parse", "HEAD"],
                              cwd=root, capture_output=True, text=True)
        status = subprocess.run(["git", "--no-optional-locks", "status", "--porcelain"],
                                cwd=root, capture_output=True, text=True)
        if not head.returncode and not status.returncode:
            result.update(mode="git", commit=head.stdout.strip(), dirty=bool(status.stdout.strip()))
    except OSError:
        pass
    return result


def forbidden_path(relative):
    parts = PurePosixPath(relative).parts
    return (
        not parts
        or ".." in parts
        or relative.startswith("/")
        or "\\" in relative
        or ":" in relative
        or any(p in (".git", ".devresources", "local_private") for p in parts)
        or parts[-1] == "AGENTS.md"
        or parts[:2] == ("docs", "publication")
        or parts[:2] == ("sample_data", "nrcan")
        or parts[:2] == (".github", "workflows")
        and relative != ".github/workflows/public-ci.yml"
        or relative in PRIVATE_RECORDS
        or relative in DEVELOPMENT_FILES
        or relative in ("assets/branding/logo.psd", "assets/branding/logo.jpg")
    )


def read_manifest(root):
    root = Path(root).resolve()
    lines = (root / MANIFEST_NAME).read_text(encoding="utf-8").splitlines()
    if not lines or len(set(p.casefold() for p in lines)) != len(lines):
        raise ValueError("Public manifest is empty or has duplicate/case-colliding paths")
    for relative in lines:
        if (relative.strip() != relative or PurePosixPath(relative).as_posix() != relative
                or forbidden_path(relative)):
            raise ValueError("Invalid public manifest entry: " + relative)
        path = root / relative
        if path.is_symlink() or not path.is_file() or root not in path.resolve().parents:
            raise ValueError("Public manifest target is missing or escapes source: " + relative)
    return lines


def content_findings(relative, data):
    """Inspect decoded text and metadata strings; rendered pixels need capture provenance."""
    if b"\x00" not in data[:8192]:
        try:
            value = data.decode("utf-8-sig")
        except UnicodeError:
            value = ""
    else:
        value = "\n".join(s.decode("ascii") for s in re.findall(rb"[\x20-\x7e]{8,}", data))
        value += "\n" + "\n".join(
            s.decode("utf-16-le") for s in re.findall(rb"(?:[\x20-\x7e]\x00){8,}", data)
        )
    patterns = {
        "local_location": r"(?i)(?<!\w)[DNO]:[\\/]+[A-Za-z0-9_ ]|C:[\\/]+Users[\\/]",
        "machine_name": "Jz_" + "Workstation",
        "academic_email": r"(?i)[\w.+-]+@uni[.]pe\b",
        "editorial_location": "docs/" + "publication",
        "private_key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        "credential": r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})",
    }
    return [f"{relative}: {kind}" for kind, pattern in patterns.items() if re.search(pattern, value)]
