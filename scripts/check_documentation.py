"""Validate local Markdown/HTML targets across the public documentation tree."""

import json
from pathlib import Path
import re
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def check():
    from scripts.public_files import read_manifest

    errors = []
    count = 0
    manifest = set(read_manifest(ROOT))
    paths = {ROOT / relative for relative in manifest if relative.endswith(".md")}
    for path in sorted(paths):
        content = path.read_text(encoding="utf-8")
        if any(character in content for character in (chr(96), chr(180), chr(12), chr(65533))):
            errors.append(f"{path.relative_to(ROOT).as_posix()}: forbidden document character")
        targets = re.findall(r"!?\[[^\]\n]*\]\(([^)\n]+)\)", content)
        targets += re.findall(r'(?:src|href)="([^"]+)"', content)
        for target in targets:
            target = target.strip().strip("<>")
            if target.startswith(("https:", "http:", "mailto:", "#", "data:")):
                continue
            target = unquote(target.split("#")[0])
            local = (path.parent / target).resolve()
            count += 1
            permitted = ROOT in local.parents and (
                local.relative_to(ROOT).as_posix() in manifest
                or any(p.startswith(local.relative_to(ROOT).as_posix().rstrip("/") + "/") for p in manifest)
            )
            if not local.exists() or not permitted:
                errors.append(f"{path.relative_to(ROOT).as_posix()}: {target}")
    migrations = json.loads(
        (ROOT / "docs/path_migrations.json").read_text(encoding="utf-8")
    )
    for old, new in migrations.items():
        if new not in manifest or not (ROOT / new).exists():
            errors.append(f"Migration {old}: missing {new}")
    return {"documents": len(paths), "links": count, "errors": errors}


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    report = check()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(bool(report["errors"]))
