"""GridFS async wrapper — file storage backed by MongoDB.

We use per-tenant GridFS buckets so a tenant's files never bleed into another
tenant's namespace.

Bucket name convention: f"{bucket_prefix}_{tenant_id_hash}" handled by the
Motor library — each call uses the tenant's database object which already
points at the isolated DB.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorGridFSBucket

from ..db import employer_db

logger = logging.getLogger(__name__)


# We use a SINGLE bucket per tenant for all student documents.
BUCKET_NAME = "student_files"


def _bucket(employer_id: str) -> AsyncIOMotorGridFSBucket:
    """Bucket lookup. Cheap to create — Motor caches the underlying db handle."""
    return AsyncIOMotorGridFSBucket(employer_db(employer_id), bucket_name=BUCKET_NAME)


async def upload(
    employer_id: str,
    *,
    filename: str,
    content: bytes,
    content_type: str,
    metadata: dict | None = None,
) -> str:
    """Store bytes and return the file id (string)."""
    fs = _bucket(employer_id)
    file_id = await fs.upload_from_stream(
        filename=filename,
        source=content,
        metadata={**(metadata or {}), "content_type": content_type},
    )
    return str(file_id)


async def open_download(employer_id: str, file_id: str):
    """Open a GridFS stream for reading. Caller must `await stream.close()`."""
    fs = _bucket(employer_id)
    try:
        return await fs.open_download_stream(ObjectId(file_id))
    except Exception:
        return None


async def get_metadata(employer_id: str, file_id: str) -> Optional[dict]:
    fs = _bucket(employer_id)
    try:
        cursor = fs.find({"_id": ObjectId(file_id)})
        async for f in cursor:
            return {
                "id": str(f._id),
                "filename": f.filename,
                "length": f.length,
                "upload_date": f.upload_date,
                "content_type": (f.metadata or {}).get("content_type"),
                "metadata": f.metadata or {},
            }
    except Exception:
        pass
    return None


async def delete(employer_id: str, file_id: str) -> bool:
    fs = _bucket(employer_id)
    try:
        await fs.delete(ObjectId(file_id))
        return True
    except Exception as e:
        logger.warning("GridFS delete failed for %s: %s", file_id, e)
        return False


async def stream_chunks(
    employer_id: str, file_id: str, chunk_size: int = 64 * 1024
) -> AsyncIterator[bytes]:
    """Async generator yielding chunks — suitable for FastAPI StreamingResponse."""
    stream = await open_download(employer_id, file_id)
    if stream is None:
        return
    try:
        while True:
            chunk = await stream.readchunk()
            if not chunk:
                break
            yield chunk
    finally:
        try:
            await stream.close()
        except Exception:
            pass
