"""Static check: routes/ must never re-introduce inline Pydantic models.

Rationale
---------
Routes should accept request payloads via `app/schemas/*` and use `app/models/*`
as the source of truth for Mongo document shapes. Defining a fresh
`class … (BaseModel)` inside a route module re-introduces the maintenance
problem the Feb-2026 refactor cleaned up (scattered shape definitions,
inconsistent validation, harder to keep an OpenAPI/mobile contract aligned).

This script walks `app/routes/*.py`, parses each with `ast`, and reports any
class whose bases include `BaseModel`. Returns exit-code 1 on violation so it
fits into pre-commit / CI pipelines.

Run manually:
    python -m app.scripts.check_routes_no_basemodel

Used by the pytest test in `tests/test_routes_no_inline_basemodel.py`.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROUTES_DIR = Path(__file__).resolve().parents[1] / "routes"


def _is_basemodel(base: ast.expr) -> bool:
    """True if `base` references `BaseModel` (either `BaseModel` or `pydantic.BaseModel`)."""
    if isinstance(base, ast.Name) and base.id == "BaseModel":
        return True
    if isinstance(base, ast.Attribute) and base.attr == "BaseModel":
        return True
    return False


def find_violations(routes_dir: Path = ROUTES_DIR) -> list[tuple[str, int, str]]:
    """Return list of (relative_path, lineno, class_name) for each inline BaseModel."""
    violations: list[tuple[str, int, str]] = []
    for path in sorted(routes_dir.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as e:
            violations.append((path.name, e.lineno or 0, f"<syntax error: {e.msg}>"))
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(_is_basemodel(b) for b in node.bases):
                violations.append((path.name, node.lineno, node.name))
    return violations


def main() -> int:
    violations = find_violations()
    if not violations:
        print(f"OK — no inline Pydantic models found in {ROUTES_DIR}")
        return 0
    print("FAIL — inline Pydantic models are not allowed inside app/routes/.")
    print("       Move each model into app/schemas/<domain>.py and import it.\n")
    for fname, lineno, cls in violations:
        print(f"  • app/routes/{fname}:{lineno}  class {cls}(BaseModel)")
    print("\nWhy: routes should stay thin. See app/schemas/ for the canonical home.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
