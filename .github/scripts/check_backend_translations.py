#!/usr/bin/env python3
"""Check backend user-facing strings are wrapped for translation.

This is a lightweight guard for plugin backend code. It intentionally checks a
small set of high-value patterns used in this repository:
- Settings metadata values for "name" and "description"
- Settings choice labels (second tuple item in each choice pair)
- Plugin TITLE / DESCRIPTION class constants
- supplier.PartImportError("...") messages
- dict values assigned to "error_status"
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "supplier_scout"
EXCLUDED = {
    "test_core_query_helpers.py",
    "test_db_upsert_supplier_part.py",
    "test_mouser_adapter.py",
    "__init__.py",
}


def is_wrapped_with_gettext(node: ast.AST) -> bool:
    """Return True when node is _("text") call."""
    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Name):
        return False
    if node.func.id != "_":
        return False
    if not node.args:
        return False
    return isinstance(node.args[0], ast.Constant) and isinstance(
        node.args[0].value, str
    )


def constant_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def is_supplier_part_import_error(node: ast.Call) -> bool:
    if call_name(node) != "PartImportError":
        return False
    if isinstance(node.func, ast.Attribute):
        return node.func.attr == "PartImportError"
    return True


def check_file(path: Path) -> list[str]:
    issues: list[str] = []
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    class Visitor(ast.NodeVisitor):
        def visit_Assign(self, node: ast.Assign) -> None:
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {
                    "TITLE",
                    "DESCRIPTION",
                }:
                    if constant_str(node.value) is not None:
                        issues.append(
                            f"{path}: TITLE/DESCRIPTION must be wrapped in _(): line {node.lineno}"
                        )
            self.generic_visit(node)

        def visit_Dict(self, node: ast.Dict) -> None:
            keys = node.keys
            values = node.values
            for key_node, value_node in zip(keys, values):
                key = constant_str(key_node)
                if key in {"name", "description", "error_status"}:
                    if constant_str(value_node):
                        if key == "error_status" and constant_str(value_node) == "OK":
                            continue
                        issues.append(
                            f"{path}: key '{key}' has raw string (wrap in _()): line {value_node.lineno}"
                        )

                if key == "choices" and isinstance(value_node, (ast.List, ast.Tuple)):
                    for choice in value_node.elts:
                        if not isinstance(choice, (ast.Tuple, ast.List)):
                            continue
                        if len(choice.elts) < 2:
                            continue
                        label = choice.elts[1]
                        if constant_str(label):
                            issues.append(
                                f"{path}: choice label has raw string (wrap in _()): line {label.lineno}"
                            )
            self.generic_visit(node)

        def visit_Raise(self, node: ast.Raise) -> None:
            exc = node.exc
            if isinstance(exc, ast.Call) and is_supplier_part_import_error(exc):
                if exc.args and constant_str(exc.args[0]):
                    issues.append(
                        f"{path}: PartImportError message must be wrapped in _(): line {exc.lineno}"
                    )
            self.generic_visit(node)

    Visitor().visit(tree)
    return issues


def main() -> int:
    files = sorted(SRC_DIR.glob("*.py"))
    files = [p for p in files if p.name not in EXCLUDED]

    all_issues: list[str] = []
    for file_path in files:
        all_issues.extend(check_file(file_path))

    if all_issues:
        print("Backend translation check failed:\n")
        for issue in all_issues:
            print(f"- {issue}")
        print("\nWrap user-facing backend strings with gettext_lazy alias _().")
        return 1

    print("Backend translation check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
