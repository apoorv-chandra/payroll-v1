"""Feature-permission routes.

  - GET  /api/me/features                                — what the logged-in user can access
  - GET  /api/features                                   — public catalog (active features)
  - PUT  /api/admin/employers/{id}/features              — super-admin grants modules to employer
  - PUT  /api/employees/{employee_user_id}/features      — employer grants modules to employees
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from ..schemas.features import FeatureCodesPayload

from ..db import db
from ..deps import get_current_user, require_role, require_employer_or_admin
from ..services.audit import audit
from ..services.features import (
    effective_features_for_user,
    sanitise_feature_codes,
)
from ..utils import now_utc

router = APIRouter(tags=["features"])


# ---------- Public catalog + self lookup ----------
@router.get("/features")
async def list_active_features():
    """Active feature catalog. Used by the login launchpad UI."""
    out = []
    async for f in db.features.find({"is_active": True}).sort("code", 1):
        f["id"] = f["_id"]
        out.append({k: v for k, v in f.items() if k != "_id"})
    return out


@router.get("/me/features")
async def my_effective_features(user: dict = Depends(get_current_user)):
    """Effective features = what THIS user can use right now.

    Frontend uses this to decide which tabs/routes to render and where to
    land after login.
    """
    codes = await effective_features_for_user(user)
    # Hydrate with display metadata so the frontend doesn't need a second call.
    items = []
    async for f in db.features.find({"code": {"$in": codes}, "is_active": True}):
        path_map = f.get("default_landing_path_by_role") or {}
        items.append({
            "code": f["code"],
            "name": f["name"],
            "description": f.get("description", ""),
            "icon": f.get("icon", ""),
            "landing_path": path_map.get(user.get("role", "")) or path_map.get("employee") or "/",
        })
    items.sort(key=lambda x: x["code"])
    return {"role": user.get("role"), "features": items}


# ---------- Super-admin: grant modules to an employer ----------
@router.put("/admin/employers/{employer_id}/features")
async def set_employer_features(
    employer_id: str,
    payload: FeatureCodesPayload,
    user: dict = Depends(require_role("super_admin")),
):
    tenant = await db.employers.find_one({"_id": employer_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Employer not found")

    codes = sanitise_feature_codes(payload.codes)
    await db.employers.update_one(
        {"_id": employer_id},
        {"$set": {"enabled_features": codes, "updated_at": now_utc()}},
    )
    # The employer-admin user is the owner of this tenant — they should ALWAYS
    # see every module the tenant has access to. Auto-widen their own row.
    await db.users.update_many(
        {"employer_id": employer_id, "role": "employer"},
        {"$set": {"feature_permissions": list(codes)}},
    )
    # For regular employees: cascade REVOKE only (trim to the new tenant set).
    # We never auto-grant new modules to employees; that stays an employer
    # decision via PUT /api/employees/{id}/features.
    await db.users.update_many(
        {"employer_id": employer_id, "role": {"$nin": ["super_admin", "employer"]}},
        [{"$set": {
            "feature_permissions": {
                "$setIntersection": [
                    {"$ifNull": ["$feature_permissions", []]},
                    codes,
                ]
            }
        }}],
    )
    await audit(employer_id, user["_id"], "tenant.features.set", employer_id, {"codes": codes})
    return {"employer_id": employer_id, "enabled_features": codes}


# ---------- Employer: grant modules to one of their employees ----------
@router.put("/employees/{employee_user_id}/features")
async def set_employee_features(
    employee_user_id: str,
    payload: FeatureCodesPayload,
    user: dict = Depends(require_employer_or_admin),
):
    target = await db.users.find_one({"_id": employee_user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.get("role") == "super_admin":
        raise HTTPException(status_code=400, detail="Cannot edit super admin features")

    # Employer can only grant within their own employer (tenant). Super admin
    # can edit any user.
    if user["role"] == "employer" and target.get("employer_id") != user.get("employer_id"):
        raise HTTPException(status_code=403, detail="Forbidden: cross-employer access")

    employer_id = target.get("employer_id")
    if not employer_id:
        raise HTTPException(status_code=400, detail="User has no employer")

    tenant = await db.employers.find_one({"_id": employer_id}, {"enabled_features": 1})
    employer_enabled = set((tenant or {}).get("enabled_features") or [])

    requested = sanitise_feature_codes(payload.codes)
    # Cannot grant a feature the employer doesn't have.
    invalid = [c for c in requested if c not in employer_enabled]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot grant features not enabled for your account: {invalid}",
        )

    await db.users.update_one(
        {"_id": employee_user_id},
        {"$set": {"feature_permissions": requested, "updated_at": now_utc()}},
    )
    await audit(employer_id, user["_id"], "employee.features.set", employee_user_id, {"codes": requested})
    return {"user_id": employee_user_id, "feature_permissions": requested}

