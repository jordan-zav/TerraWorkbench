"""Explicit dependency cleanup with an immutable inventory and strict path bounds.

This module has no QGIS imports. It never runs during plugin unload.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
import sys


class DependenciesInUseError(RuntimeError):
    """A loaded module belongs to the dependency tree being considered."""


def ensure_dependencies_not_in_use(target):
    """Refuse cleanup when a module or namespace package uses this directory."""
    target = Path(target).resolve()
    for module in tuple(sys.modules.values()):
        if module is None:
            continue
        try:
            namespace = vars(module)
        except TypeError:
            continue
        paths = [namespace.get("__file__")]
        package_paths = namespace.get("__path__")
        if package_paths is not None:
            if isinstance(package_paths, (str, bytes, os.PathLike)):
                paths.append(package_paths)
            else:
                paths.extend(package_paths)
        for path in paths:
            if not isinstance(path, (str, os.PathLike)):
                continue
            candidate = Path(path)
            if candidate.absolute().is_relative_to(target) or candidate.resolve().is_relative_to(target):
                raise DependenciesInUseError("Dependencies are in use in this session")


@dataclass(frozen=True)
class CleanupPlan:
    profile: Path
    target: Path
    python_version: str
    entries: tuple
    setting_keys: tuple
    file_count: int
    total_bytes: int


def _link(info):
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def validate_cleanup_target(profile, target, python_version):
    """Reject another profile/version, traversal, symlinks and Windows junctions."""
    if not re.fullmatch(r"\d+\.\d+", python_version):
        raise ValueError("Invalid Python version")
    profile = Path(profile).resolve(strict=True)
    if not profile.is_dir():
        raise ValueError("The active profile must be a directory")
    candidate = Path(target)
    expected = profile / "python" / "dependencies" / "TerraWorkbench" / python_version
    if not candidate.is_absolute() or candidate != expected:
        raise ValueError("Cleanup target is not the active profile dependency directory")
    current = profile
    for component in expected.relative_to(profile).parts:
        current = current / component
        if os.path.lexists(current):
            info = current.lstat()
            if _link(info) or not stat.S_ISDIR(info.st_mode):
                raise ValueError("Cleanup refuses linked or non-directory ancestors")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(profile) or resolved != expected:
        raise ValueError("Cleanup target escapes the active profile")
    return profile, expected


def cleanup_plan(profile, target, python_version, setting_keys=()):
    profile, target = validate_cleanup_target(profile, target, python_version)
    keys = tuple(sorted(setting_keys))
    if any(not key.startswith("TerraWorkbench/") for key in keys):
        raise ValueError("Cleanup refuses settings outside TerraWorkbench/")
    entries = []

    def visit(folder):
        with os.scandir(folder) as children:
            for entry in sorted(children, key=lambda child: child.name):
                info = entry.stat(follow_symlinks=False)
                if _link(info) or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                    raise ValueError("Cleanup refuses symbolic links, junctions and special files")
                relative = Path(entry.path).relative_to(target).as_posix()
                is_dir = stat.S_ISDIR(info.st_mode)
                # Windows may finish updating directory timestamps after a child
                # write. Names and directory identity guard structure; only file
                # sizes/timestamps belong in the content confirmation snapshot.
                entries.append((relative, is_dir, 0 if is_dir else info.st_size,
                                0 if is_dir else info.st_mtime_ns, info.st_dev, info.st_ino))
                if is_dir:
                    visit(entry.path)

    if target.exists():
        visit(target)
    entries = tuple(entries)
    return CleanupPlan(profile, target, python_version, entries, keys,
                       sum(not row[1] for row in entries),
                       sum(row[2] for row in entries if not row[1]))


def remove_dependencies(plan, *, confirmed=False):
    """Remove only the inventoried tree, after confirmation and a fresh safety scan."""
    if not confirmed:
        raise PermissionError("Explicit confirmation is required")
    if cleanup_plan(plan.profile, plan.target, plan.python_version, plan.setting_keys) != plan:
        raise ValueError("Dependency inventory changed; request confirmation again")
    ensure_dependencies_not_in_use(plan.target)
    for relative, is_dir, *_ in sorted(plan.entries, key=lambda row: (row[0].count("/"), row[0]), reverse=True):
        validate_cleanup_target(plan.profile, plan.target, plan.python_version)
        path = plan.target / relative
        # Recheck every parent immediately before touching a leaf. Never recurse
        # through shutil.rmtree or follow a directory link during deletion.
        for parent in [path, *path.parents]:
            if parent == plan.target.parent:
                break
            if _link(parent.lstat()):
                raise ValueError("Dependency path became a link; cleanup aborted")
        if is_dir:
            path.rmdir()
        else:
            path.unlink()
    if plan.target.exists():
        validate_cleanup_target(plan.profile, plan.target, plan.python_version)
        plan.target.rmdir()
