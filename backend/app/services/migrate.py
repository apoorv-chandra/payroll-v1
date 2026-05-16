"""One-shot migration to:
  1. Move per-tenant collections from the legacy SHARED DB into per-tenant DBs.
  2. Re-home data from old LONG-name tenant DBs (32-char hex suffix) into the
     new SHORT-name tenant DBs (24-char blake2s suffix). Atlas caps DB names
     at 38 bytes; the old scheme exceeded that.

Safe to run repeatedly — every step checks for existence before copying.
"""
from __future__ import annotations

import logging

from ..config import settings
from ..db import (
    PER_TENANT_COLLECTIONS,
    db,
    ensure_tenant_indexes,
    get_client,
    tenant_db,
    tenant_db_name,
)

logger = logging.getLogger(__name__)


def _legacy_long_name(tenant_id: str) -> str:
    """The pre-v8.1 naming convention (UUID with dashes stripped)."""
    return f"{settings.DB_NAME}_t_{tenant_id.replace('-', '')}"


async def _move_collections_from(src_db, dst_db, label: str) -> int:
    """Copy + delete each known per-tenant collection from src to dst.
    Returns total docs moved."""
    moved = 0
    for coll in PER_TENANT_COLLECTIONS:
        try:
            count = await src_db[coll].count_documents({})
        except Exception:
            continue
        if count == 0:
            continue
        async for doc in src_db[coll].find({}):
            existing = await dst_db[coll].find_one({"_id": doc["_id"]})
            if existing is None:
                try:
                    await dst_db[coll].insert_one(doc)
                except Exception as e:    # noqa: BLE001
                    logger.warning("Migrate %s/%s/%s failed: %s", label, coll, doc.get("_id"), e)
                    continue
            await src_db[coll].delete_one({"_id": doc["_id"]})
            moved += 1
        # Drop empty source collection so it's clear nothing remains.
        if await src_db[coll].count_documents({}) == 0:
            try:
                await src_db.drop_collection(coll)
            except Exception:
                pass
    return moved


async def migrate_per_tenant_collections() -> None:
    client = get_client()
    existing_dbs = set(await client.list_database_names())

    async for t in db.tenants.find({}):
        tid = t["_id"]
        try:
            await ensure_tenant_indexes(tid)
        except Exception as e:    # noqa: BLE001
            logger.warning("ensure_tenant_indexes failed for %s: %s", t.get("name"), e)

        new_db = tenant_db(tid)
        new_name = tenant_db_name(tid)

        # 1. Move data from the LEGACY LONG-NAME tenant DB into the new short-name DB.
        legacy_name = _legacy_long_name(tid)
        if legacy_name != new_name and legacy_name in existing_dbs:
            legacy_db = client[legacy_name]
            moved = await _move_collections_from(legacy_db, new_db, label=legacy_name)
            if moved:
                logger.info("Migrated %d docs %s → %s", moved, legacy_name, new_name)
            try:
                await client.drop_database(legacy_name)
                logger.info("Dropped legacy long-name DB %s", legacy_name)
            except Exception as e:    # noqa: BLE001
                logger.warning("Could not drop legacy DB %s: %s", legacy_name, e)

    # 2. Move any data still sitting in the GLOBAL DB into the right tenant DB.
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
                continue
            tdb = tenant_db(tid)
            existing = await tdb[coll_name].find_one({"_id": doc["_id"]})
            if existing is None:
                try:
                    await tdb[coll_name].insert_one(doc)
                except Exception as e:    # noqa: BLE001
                    logger.warning("Migrate global/%s/%s failed: %s", coll_name, doc.get("_id"), e)
                    continue
            await db[coll_name].delete_one({"_id": doc["_id"]})
            moved_total += 1
        if await db[coll_name].count_documents({}) == 0:
            try:
                await db.drop_collection(coll_name)
                logger.info("Dropped legacy global collection %s", coll_name)
            except Exception:
                pass

    if moved_total:
        logger.info("Migrated %s legacy global documents into per-tenant databases.", moved_total)

    # 3. Scrub orphan long-name tenant DBs (data was already migrated by step 1
    #    when the tenant existed; what remains here are DBs whose tenant
    #    record was deleted before the migration was first run).
    legacy_orphans = [
        d for d in await client.list_database_names()
        if d.startswith(f"{settings.DB_NAME}_t_") and len(d) - len(settings.DB_NAME) - 3 == 32
    ]
    for orphan in legacy_orphans:
        try:
            await client.drop_database(orphan)
            logger.info("Dropped orphan legacy long-name DB %s", orphan)
        except Exception as e:    # noqa: BLE001
            logger.warning("Could not drop orphan DB %s: %s", orphan, e)
