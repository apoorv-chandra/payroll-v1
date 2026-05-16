"""One-shot migration to move per-tenant collections from the legacy shared DB
into per-tenant databases. Safe to run repeatedly — it only moves docs that
still live in the legacy DB.

Triggered on app startup AFTER `ensure_indexes` and `seed_*`.
"""
from __future__ import annotations

import logging

from ..db import db, tenant_db, ensure_tenant_indexes, PER_TENANT_COLLECTIONS

logger = logging.getLogger(__name__)


async def migrate_per_tenant_collections() -> None:
    # First make sure every tenant's per-tenant DB has its indexes.
    async for t in db.tenants.find({}):
        try:
            await ensure_tenant_indexes(t["_id"])
        except Exception as e:    # noqa: BLE001
            logger.warning("ensure_tenant_indexes failed for %s: %s", t.get("name"), e)

    # Then move legacy docs out of the shared DB.
    moved_total = 0
    for coll_name in PER_TENANT_COLLECTIONS:
        try:
            count_before = await db[coll_name].count_documents({})
        except Exception:
            continue
        if count_before == 0:
            continue

        async for doc in db[coll_name].find({}):
            tid = doc.get("tenant_id")
            if not tid:
                # Orphan record — leave it; super admin can investigate.
                continue
            tdb = tenant_db(tid)
            # Insert if not already there (idempotent on _id).
            existing = await tdb[coll_name].find_one({"_id": doc["_id"]})
            if existing is None:
                try:
                    await tdb[coll_name].insert_one(doc)
                except Exception as e:    # noqa: BLE001
                    logger.warning("Migrate %s/%s failed: %s", coll_name, doc.get("_id"), e)
                    continue
            await db[coll_name].delete_one({"_id": doc["_id"]})
            moved_total += 1

        # If everything in this collection has been migrated, drop the
        # collection from the global DB so it's clear nothing is left there.
        remaining = await db[coll_name].count_documents({})
        if remaining == 0:
            try:
                await db.drop_collection(coll_name)
                logger.info("Dropped legacy global collection %s", coll_name)
            except Exception:
                pass

    if moved_total:
        logger.info("Migrated %s legacy documents into per-tenant databases.", moved_total)
