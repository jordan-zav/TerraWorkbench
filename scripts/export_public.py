"""Export only approved public files to a NEW folder and validate the result.

Never commits, publishes, downloads survey data or changes the private checkout.
The development-only source entry is projected out of the copied benchmark
catalogue. All other source files are copied byte-for-byte.
"""

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from zipfile import ZipFile

try:
    from scripts.public_files import content_findings, forbidden_path, read_manifest
except ModuleNotFoundError:
    from public_files import content_findings, forbidden_path, read_manifest

ROOT = Path(__file__).resolve().parents[1]


def check_imports(root, files):
    errors = []
    known = set(files)
    local = {"scripts", "terraworkbench_core", "ui", "qgis_plugin", "compat", "algorithms", "embedded_qpip", "examples"}
    for relative in files:
        if not relative.endswith(".py"):
            continue
        try:
            tree = ast.parse((root / relative).read_text(encoding="utf-8-sig"))
        except SyntaxError as error:
            errors.append(f"{relative}: {error}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    parent = relative.split("/")[:-1]
                    module = "/".join(parent[:len(parent) - node.level + 1] + (node.module or "").split(".")).rstrip("/")
                elif node.module and node.module.split(".")[0] in local:
                    module = node.module.replace(".", "/")
                else:
                    continue
                if not module:
                    continue
                if module == "scripts":
                    modules = [module + "/" + alias.name for alias in node.names]
                else:
                    modules = [module]
                for name in modules:
                    if name + ".py" not in known and name + "/__init__.py" not in known:
                        errors.append(f"{relative}:{node.lineno}: unresolved local import {name}")
    return errors


def export(output, *, root=ROOT):
    root = Path(root).resolve()
    output = Path(output).resolve()
    if output.exists() or output == root or root in output.parents:
        raise ValueError("Choose a new output directory outside the source checkout")
    files = read_manifest(root)
    output.mkdir(parents=True, exist_ok=False)
    projection = []
    for relative in files:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, target)
        if relative == "scripts/public_processing_sources.json":
            record = json.loads(target.read_text(encoding="utf-8"))
            removed = [key for key, value in record.items() if value.get("distribution") == "development-only; never export"]
            for key in removed:
                del record[key]
            if removed:
                target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                projection.append({"path": relative, "removed_development_entries": removed})
    return files, projection


def validate(output, files, report_dir):
    output, report_dir = Path(output), Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=False)
    report = {"output": str(output), "steps": [], "privacy_findings": [], "import_errors": check_imports(output, files)}
    before_hashes = {relative: hashlib.sha256((output / relative).read_bytes()).hexdigest()
                     for relative in files}
    for relative in files:
        if forbidden_path(relative):
            report["privacy_findings"].append(relative)
        report["privacy_findings"].extend(content_findings(relative, (output / relative).read_bytes()))
    report["copied_files_exactly_manifest"] = sorted(p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()) == sorted(files)
    env = os.environ.copy()
    env.update(PYTHONPATH=str(output), PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX=str(report_dir / "pycache"),
               NUMBA_CACHE_DIR=str(report_dir / "numba-cache"), MPLCONFIGDIR=str(report_dir / "matplotlib"),
               RUFF_CACHE_DIR=str(report_dir / "ruff-cache"), TEMP=str(report_dir), TMP=str(report_dir),
               OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", MKL_NUM_THREADS="2", NUMBA_NUM_THREADS="2")

    def save():
        (report_dir / "export_result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def run(name, args):
        start = time.monotonic()
        with (report_dir / (name + ".log")).open("w", encoding="utf-8") as stream:
            code = subprocess.run([sys.executable, *args], cwd=output, env=env, stdout=stream, stderr=subprocess.STDOUT).returncode
        report["steps"].append({"name": name, "exit_code": code, "seconds": round(time.monotonic() - start, 3), "log": name + ".log"})
        save()
        return code == 0

    save()
    if report["privacy_findings"] or report["import_errors"] or not report["copied_files_exactly_manifest"]:
        report["ok"] = False
        save()
        return report
    # Keep every result, even if a previous check fails.
    run("links", ["scripts/check_documentation.py"])
    run("manual", ["scripts/check_manual.py"])
    run("ruff", ["-m", "ruff", "check", "."])
    run("package_check", ["scripts/package_plugin.py", "--check-only"])
    run("package_build", ["scripts/package_plugin.py"])
    run("public_tests", ["-m", "pytest", "-q", "-o", "cache_dir=" + str(report_dir / "pytest-cache"), "--junitxml=" + str(report_dir / "public_tests.xml")])
    archives = list((output / "dist").glob("TerraWorkbench-*.zip"))
    report["archives"] = []
    for archive in archives:
        with ZipFile(archive) as bundle:
            names = bundle.namelist()
            violations = []
            for name in names:
                relative = name.removeprefix("TerraWorkbench/")
                if relative not in files or forbidden_path(relative):
                    violations.append(name)
                violations.extend(content_findings(name, bundle.read(name)))
            report["archives"].append({"name": archive.name, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "entries": len(names), "violations": violations})
    report["source_files_changed_by_validation"] = [
        relative for relative in files
        if not (output / relative).is_file()
        or hashlib.sha256((output / relative).read_bytes()).hexdigest() != before_hashes[relative]
    ]
    allowed_products = {archive.relative_to(output).as_posix() for archive in archives}
    report["unexpected_generated_files"] = sorted(
        path.relative_to(output).as_posix() for path in output.rglob("*")
        if path.is_file() and path.relative_to(output).as_posix() not in set(files) | allowed_products
    )
    report["ok"] = (all(step["exit_code"] == 0 for step in report["steps"])
                    and len(archives) == 1 and all(not a["violations"] for a in report["archives"])
                    and not report["source_files_changed_by_validation"]
                    and not report["unexpected_generated_files"])
    save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report-dir", type=Path)
    args = parser.parse_args()
    files, projection = export(args.output)
    report_dir = args.report_dir or args.output.with_name(args.output.name + "-validation")
    result = validate(args.output.resolve(), files, report_dir.resolve())
    result["catalogue_projection"] = projection
    result["manifest_sha256"] = hashlib.sha256((ROOT / "public_manifest.txt").read_bytes()).hexdigest()
    result["source_git_head"] = subprocess.run(
        ["git", "--no-optional-locks", "rev-parse", "HEAD"], cwd=ROOT,
        capture_output=True, text=True,
    ).stdout.strip() or None
    result["copy_sha256"] = {
        relative: {
            "source": hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(),
            "exported": hashlib.sha256((args.output / relative).read_bytes()).hexdigest(),
        } for relative in files
    }
    (report_dir / "export_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
