"""Domain document models — the canonical shape of every entity stored in Mongo.

Each module under this package defines a single Pydantic model representing a
collection's document. These are the **source of truth** for schema. Routes
should accept inbound payloads via `app/schemas/*` request models and write
outbound responses via the `model_dump()` of these docs.

Convention
----------
  • All IDs are UUID-strings (`gen_id()`). No ObjectIds.
  • All datetimes are tz-aware UTC (`datetime.now(timezone.utc)`).
  • Per-employer scoping is via `employer_id` (legacy field name `tenant_id`
    has been migrated away — see services/rename_to_employers.py).
  • Soft-delete via nullable `deleted_at`.
"""
