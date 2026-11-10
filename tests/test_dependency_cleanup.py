"""Profile-bound cleanup never follows a link or removes unrelated state."""

import os
import subprocess
import sys
from types import ModuleType

import pytest

from qgis_plugin.dependency_cleanup import (
    DependenciesInUseError, cleanup_plan, remove_dependencies, validate_cleanup_target,
)
from ui.processing_labels import optional_description


def tree(tmp_path, custom=False):
    profile = tmp_path / ("custom-root/selected" if custom else "profiles/default")
    target = profile / "python/dependencies/TerraWorkbench/3.12"
    target.mkdir(parents=True)
    (target / "package").mkdir()
    (target / "one.dat").write_bytes(b"abc")
    (target / "package/two.dat").write_bytes(b"12345")
    return profile, target


@pytest.mark.parametrize("custom", [False, True])
def test_only_confirmed_profile_version_tree_is_removed(tmp_path, custom):
    profile, target = tree(tmp_path, custom)
    sibling = target.parent / "3.11"
    sibling.mkdir()
    sentinel = sibling / "keep.dat"
    sentinel.write_bytes(b"keep")
    plan = cleanup_plan(profile, target, "3.12", ["TerraWorkbench/language"])
    assert plan.file_count == 2 and plan.total_bytes == 8
    with pytest.raises(PermissionError):
        remove_dependencies(plan)
    assert (target / "one.dat").is_file()
    remove_dependencies(plan, confirmed=True)
    assert not target.exists()
    assert sentinel.read_bytes() == b"keep" and profile.is_dir()


@pytest.mark.parametrize("relative", ["outside", "python/dependencies/Other/3.12", "python/dependencies/TerraWorkbench/3.11"])
def test_rejects_other_paths_before_removing_anything(tmp_path, relative):
    profile, target = tree(tmp_path)
    candidate = tmp_path / "outside" if relative == "outside" else profile / relative
    candidate.mkdir(parents=True)
    sentinel = candidate / "keep.dat"
    sentinel.write_bytes(b"keep")
    with pytest.raises(ValueError):
        validate_cleanup_target(profile, candidate, "3.12")
    assert (target / "one.dat").read_bytes() == b"abc"
    assert sentinel.read_bytes() == b"keep"


def link_directory(link, outside):
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True)


@pytest.mark.parametrize("at_target", [False, True])
def test_rejects_external_symlink_or_windows_junction(tmp_path, at_target):
    profile = tmp_path / "profiles/default"
    target = profile / "python/dependencies/TerraWorkbench/3.12"
    target.parent.mkdir(parents=True)
    outside = tmp_path / "unrelated"
    outside.mkdir()
    (outside / "sentinel.dat").write_bytes(b"do not delete")
    if at_target:
        link_directory(target, outside)
    else:
        target.mkdir()
        link_directory(target / "linked", outside)
    with pytest.raises(ValueError, match="link|directory"):
        cleanup_plan(profile, target, "3.12")
    assert (outside / "sentinel.dat").read_bytes() == b"do not delete"


def test_confirmation_becomes_invalid_when_inventory_changes(tmp_path):
    profile, target = tree(tmp_path)
    plan = cleanup_plan(profile, target, "3.12")
    (target / "new.dat").write_bytes(b"new")
    with pytest.raises(ValueError, match="changed"):
        remove_dependencies(plan, confirmed=True)
    assert (target / "one.dat").exists()


@pytest.mark.parametrize("attribute", ["__file__", "__path__"])
def test_loaded_dependency_blocks_every_deletion(tmp_path, monkeypatch, attribute):
    profile, target = tree(tmp_path)
    plan = cleanup_plan(profile, target, "3.12")
    module = ModuleType("tw_fake_loaded_dependency")
    setattr(module, attribute, str(target / "package/locked.pyd") if attribute == "__file__"
            else [str(target / "package")])
    monkeypatch.setitem(sys.modules, module.__name__, module)
    with pytest.raises(DependenciesInUseError):
        remove_dependencies(plan, confirmed=True)
    assert cleanup_plan(profile, target, "3.12") == plan
    assert (target / "one.dat").read_bytes() == b"abc"
    assert (target / "package/two.dat").read_bytes() == b"12345"


def test_settings_namespace_is_strict_and_missing_folder_is_safe(tmp_path):
    profile = tmp_path / "active"
    profile.mkdir()
    target = profile / "python/dependencies/TerraWorkbench/3.12"
    with pytest.raises(ValueError, match="settings"):
        cleanup_plan(profile, target, "3.12", ["OtherPlugin/keep"])
    plan = cleanup_plan(profile, target, "3.12", ["TerraWorkbench/language"])
    assert plan.file_count == plan.total_bytes == 0
    remove_dependencies(plan, confirmed=True)
    assert profile.exists()


@pytest.mark.parametrize("locale,label,expected", [
    ("en", "Standard deviation field (optional)", "Standard deviation field"),
    ("es", "Altura (opcional; Z o 0)", "Altura (Z o 0)"),
    ("pt", "Altura (m, opcional)", "Altura (m)"),
    ("en", "Total count (optional if dead time is zero)", "Total count (may be blank if dead time is zero)"),
    ("es", "Conteo (opcional si el tiempo es cero)", "Conteo (puede quedar vacío si el tiempo es cero)"),
    ("pt", "Contagem (opcional se o tempo é zero)", "Contagem (pode ficar vazio se o tempo é zero)"),
])
def test_optional_marker_keeps_fallback_and_unit_information(locale, label, expected):
    assert optional_description(label, locale) == expected
