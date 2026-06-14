"""One-shot migration: rename `tenants` → `employers` everywhere.

What this does (idempotent — safe to run on every boot)
--------------------------------------------------------
1. Renames the GLOBAL collection `tenants` → `employers`.
   - Falls back to per-doc copy if `renameCollection` isn't permitted
     (some Atlas tiers restrict it).
2. For every document in the GLOBAL `users` collection that still has
   `employer_id`, renames the field to `employer_id`.
3. For every per-tenant (now: per-employer) database, walks every
   collection and `$rename`s `employer_id` → `employer_id` on each doc.
4. Logs a one-line summary at the end.

Why we keep the DB-name pattern `payroll_t_<hash>` unchanged
-----------------------------------------------------------
The infix `_t_` is purely cosmetic — the hash is derived from the
employer_id value (same UUID), so the resulting DB name is unchanged.
Changing the infix would orphan all existing tenant data because the
DB name lookup would no longer match. So the function name becomes
`employer_db(employer_id)` (clarity) but the DB it returns is the
same physical database.
"""
from __future__ import annotations

import logging

from ..db import db, employer_db, employer_db_name

logger = logging.getLogger(__name__)


async def rename_tenants_to_employers() -> None:
    # ---------- Step 1: rename the global collection ----------
    try:
        existing = await db.list_collection_names()
        if "tenants" in existing and "employers" not in existing:
            try:
                # Fastest path — atomic, preserves indexes.
                await db.employers.rename("employers")
                logger.info("Renamed global collection tenants → employers (atomic).")
            except Exception as e:
                # Fall back to copy + drop. Some Atlas plans restrict
                # renameCollection across DBs / sharded clusters.
                logger.warning("Atomic rename failed (%s); falling back to copy.", e)
                async for doc in db.employers.find({}):
                    try:
                        await db.employers.insert_one(doc)
                    except Exception as e2:
                        logger.warning("Copy %s failed: %s", doc.get("_id"), e2)
                await db.employers.drop()
                logger.info("Copied + dropped tenants → employers.")
        elif "tenants" in existing and "employers" in existing:
            # Both exist — merge tenants into employers, then drop tenants.
            async for doc in db.employers.find({}):
                if await db.employers.find_one({"_id": doc["_id"]}) is None:
                    await db.employers.insert_one(doc)
            await db.employers.drop()
            logger.info("Merged residual tenants into employers and dropped legacy collection.")
    except Exception as e:
        logger.warning("Collection rename step skipped: %s", e)

    # Ensure indexes on the new collection name. Idempotent.
    try:
        await db.employers.create_index("name")
        await db.employers.create_index("signup_code", unique=True, sparse=True)
    except Exception as e:
        logger.warning("Could not ensure employers indexes: %s", e)

    # ---------- Step 2: rename field on global users ----------
    # Use the literal field name "tenant_id" as the source. This is the
    # LEGACY field; after a successful run no doc will match anymore so the
    # update is a cheap no-op on subsequent boots.
    LEGACY_FIELD = "tenant" + "_id"  # split to survive any future bulk-renames
    try:
        r = await db.users.update_many(
            {LEGACY_FIELD: {"$exists": True}},
            {"$rename": {LEGACY_FIELD: "employer_id"}},
        )
        if r.modified_count:
            logger.info("Renamed %s → employer_id on %d users.", LEGACY_FIELD, r.modified_count)
    except Exception as e:
        logger.warning("Could not rename users.%s: %s", LEGACY_FIELD, e)

    # ---------- Step 3: rename field on every per-employer collection ----------
    total = 0
    async for emp in db.employers.find({}, {"_id": 1}):
        emp_id = emp["_id"]
        try:
            edb = employer_db(emp_id)
            for coll_name in await edb.list_collection_names():
                try:
                    # Skip if the legacy field doesn't exist anywhere — avoids
                    # Mongo's "source and target must differ" complaint on
                    # already-migrated databases.
                    has_legacy = await edb[coll_name].find_one(
                        {LEGACY_FIELD: {"$exists": True}}, {"_id": 1}
                    )
                    if not has_legacy:
                        continue
                    r = await edb[coll_name].update_many(
                        {LEGACY_FIELD: {"$exists": True}},
                        {"$rename": {LEGACY_FIELD: "employer_id"}},
                    )
                    total += r.modified_count
                except Exception as e:
                    logger.warning(
                        "Field rename on %s/%s failed: %s",
                        employer_db_name(emp_id), coll_name, e,
                    )
        except Exception as e:
            logger.warning("Per-employer field rename failed for %s: %s", emp_id, e)
    if total:
        logger.info("Renamed employer_id → employer_id on %d per-employer documents.", total)
