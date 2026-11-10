"""The full manual tracks actual source, resolves links and ships its images."""

from pathlib import Path

from scripts.check_manual import check
from scripts.package_plugin import package_files

ROOT = Path(__file__).resolve().parents[1]


def test_svg_integrity_is_portable_and_binary_integrity_remains_exact(tmp_path):
    from scripts.build_manual_figures import asset_sha256

    unix, windows = tmp_path / "unix.svg", tmp_path / "windows.svg"
    unix.write_bytes(b"<svg>\n<text>Diagram</text>\n</svg>\n")
    windows.write_bytes(unix.read_bytes().replace(b"\n", b"\r\n"))
    assert asset_sha256(unix) == asset_sha256(windows)
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    a.write_bytes(b"binary\n")
    b.write_bytes(b"binary\r\n")
    assert asset_sha256(a) != asset_sha256(b)


def test_manual_covers_current_source_and_has_no_broken_links():
    result = check()
    assert result["chapters"] == 28
    assert result["locales"] == ["es", "en", "pt"]
    assert result["numbered_figures"] == 18
    assert result["local_links_checked"] > 300
    assert not result["errors"], result["errors"]


def test_manual_and_images_are_in_plugin_package():
    from scripts.public_files import read_manifest

    included = set(package_files())
    for relative in read_manifest(ROOT):
        if relative.startswith("docs/manuals/"):
            assert ROOT / relative in included


def test_translation_manifest_detects_source_drift(tmp_path, monkeypatch):
    import json
    from scripts import build_manual_localization as localization

    folder = tmp_path / "manuals"
    (folder / "_meta").mkdir(parents=True)
    (folder / "_meta/coverage.json").write_text(json.dumps([{"file": "01_start.md"}]))
    for locale in localization.LOCALES:
        (folder / locale).mkdir()
        for name in ("01_start.md", "README.md", "fuentes.md"):
            (folder / locale / name).write_text("# Original\n")
    monkeypatch.setattr(localization, "MANUAL", folder)
    before = localization.product()
    (folder / "es/01_start.md").write_text("# Changed scientific convention\n")
    after = localization.product()
    assert (
        before["chapters"][0]["versions"]["es"]["sha256_lf"]
        != after["chapters"][0]["versions"]["es"]["sha256_lf"]
    )
    assert (
        before["chapters"][0]["versions"]["en"]
        == after["chapters"][0]["versions"]["en"]
    )


def test_teaching_examples_run_real_apis(tmp_path):
    from examples.manual.workspace import run as workspace
    from examples.manual.fft import run as fft
    from examples.manual.workflow import run as workflow

    database = workspace(tmp_path / "workspace")
    assert database["original_unchanged"] and database["rows"] == 400
    assert database["max_formula_error_nt"] < 1e-10
    spectrum = fft(tmp_path / "fft")
    assert spectrum["max_error"] < 1e-12
    chain = workflow(tmp_path / "workflow")
    assert chain["mt_max_resistivity_error"] < 1e-10
    assert chain["layer_max_contrast_error"] < 1e-8
