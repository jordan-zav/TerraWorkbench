"""Static candidate discovery, not a proof of mathematical independence.

Scan top-level functions and QGIS processAlgorithm bodies with at least two
statements and eight source lines. Ignore docstrings and optionally normalize
local names; preserve globals, attributes, constants and argument defaults.
"""

import argparse
import ast
from collections import defaultdict
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(node, normalize):
    node = copy.deepcopy(node)
    if (
        node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    ):
        node.body = node.body[1:]
    if len(node.body) < 2 or node.end_lineno - node.lineno < 8:
        return None
    if normalize:
        names = {}
        for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
            names.setdefault(arg.arg, "local_" + str(len(names)))
        for item in ast.walk(node):
            if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store):
                names.setdefault(item.id, "local_" + str(len(names)))
        for item in ast.walk(node):
            if isinstance(item, ast.Name) and item.id in names:
                item.id = names[item.id]
            elif isinstance(item, ast.arg) and item.arg in names:
                item.arg = names[item.arg]
    return ast.dump(ast.Module(body=node.body, type_ignores=[])) + ast.dump(node.args)


def audit(root=ROOT):
    files = sorted(
        set(root.glob("*.py"))
        | set((root / "qgis_plugin").glob("*.py"))
        | set((root / "compat").glob("*.py"))
        | set((root / "algorithms").glob("*.py"))
        | set((root / "ui").glob("*.py"))
        | set((root / "terraworkbench_core").glob("*.py"))
    )
    groups = [defaultdict(list), defaultdict(list)]
    adapters = []
    public = 0
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        if path.parent == root and any(
            isinstance(n, ast.alias) and n.asname == "_implementation"
            for n in ast.walk(tree)
        ):
            adapters.append(str(path.relative_to(root)))
        candidates = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
        public += sum(not n.name.startswith("_") for n in candidates)
        if path.parent.name == "algorithms":
            candidates += [
                n
                for cls in tree.body
                if isinstance(cls, ast.ClassDef)
                for n in cls.body
                if isinstance(n, ast.FunctionDef) and n.name == "processAlgorithm"
            ]
        for node in candidates:
            for normalize, group in enumerate(groups):
                key = fingerprint(node, normalize)
                if key:
                    group[key].append(
                        {
                            "path": str(path.relative_to(root)),
                            "name": node.name,
                            "line": node.lineno,
                        }
                    )
    registry = ast.parse(
        (root / "terraworkbench_core/operations.py").read_text(encoding="utf-8")
    )
    operations = next(
        ast.literal_eval(n.value)
        for n in registry.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_OPERATIONS" for t in n.targets)
    )
    targets = defaultdict(list)
    for key, value in operations.items():
        targets[".".join(value[:2])].append(key)
    return {
        "files": len(files),
        "public_functions": public,
        "registered_operations": len(operations),
        "compatibility_adapters": adapters,
        "exact_candidates": [v for v in groups[0].values() if len(v) > 1],
        "normalized_candidates": [v for v in groups[1].values() if len(v) > 1],
        "repeated_registry_targets": {k: v for k, v in targets.items() if len(v) > 1},
        "limits": "Static candidates only; excludes most class methods and semantic overlap",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    text = json.dumps(audit(), indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
