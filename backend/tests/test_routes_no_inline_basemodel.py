"""Guard test: routes/ must NOT define any `class ... (BaseModel)` inline.

Runs the same AST scan as `app/scripts/check_routes_no_basemodel.py` so the
guard fails the pytest suite (and therefore any CI run) the moment someone
re-introduces an inline schema inside a route module.
"""
from app.scripts.check_routes_no_basemodel import find_violations


def test_no_inline_basemodels_in_routes():
    violations = find_violations()
    msg_lines = [
        "Inline Pydantic models are not allowed inside app/routes/.",
        "Move each into app/schemas/<domain>.py and import it.",
        "Offenders:",
    ]
    msg_lines += [
        f"  • app/routes/{fname}:{lineno}  class {cls}(BaseModel)"
        for fname, lineno, cls in violations
    ]
    assert not violations, "\n".join(msg_lines)
