"""File compression — lossless image re-encode + PDF object-stream rewrite.

Mirrors the Node app's sharp + pdf-lib pipeline but in Python (Pillow + pikepdf).
"""
from __future__ import annotations

import io
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


MAX_IMAGE_DIM = 1920          # downscale larger images
IMAGE_OUTPUT_QUALITY = 85     # JPEG quality — visually lossless at 85
ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
ALLOWED_PDF_MIMES = {"application/pdf"}


def compress_image(content: bytes, content_type: str) -> Tuple[bytes, str]:
    """Re-encode JPEG/PNG/WEBP with max 1920px side. Returns (bytes, mime).

    Falls back to original bytes if Pillow can't decode (corrupt / unsupported).
    """
    try:
        from PIL import Image  # local import to keep import-time fast

        with Image.open(io.BytesIO(content)) as im:
            im.load()
            # EXIF-aware rotation so phone photos don't end up sideways.
            try:
                from PIL import ImageOps
                im = ImageOps.exif_transpose(im)
            except Exception:
                pass

            # Convert to RGB for JPEG output (drops alpha channel from PNGs).
            target_format = "JPEG"
            target_mime = "image/jpeg"
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGB")

            # Downscale only if larger than MAX_IMAGE_DIM on either side.
            w, h = im.size
            if max(w, h) > MAX_IMAGE_DIM:
                scale = MAX_IMAGE_DIM / float(max(w, h))
                im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

            buf = io.BytesIO()
            im.save(buf, format=target_format, quality=IMAGE_OUTPUT_QUALITY, optimize=True, progressive=True)
            out = buf.getvalue()
            # Only return compressed if it actually saved bytes.
            if len(out) < len(content):
                return out, target_mime
    except Exception as e:
        logger.warning("Image compression failed (%s) — keeping original: %s", content_type, e)
    return content, content_type


def compress_pdf(content: bytes) -> bytes:
    """Rewrite PDF using object streams + linearize. Lossless, often 20-40% smaller."""
    try:
        import pikepdf

        with pikepdf.open(io.BytesIO(content)) as pdf:
            buf = io.BytesIO()
            pdf.save(
                buf,
                object_stream_mode=pikepdf.ObjectStreamMode.generate,
                compress_streams=True,
                stream_decode_level=pikepdf.StreamDecodeLevel.generalized,
            )
            out = buf.getvalue()
            if len(out) < len(content):
                return out
    except Exception as e:
        logger.warning("PDF compression failed — keeping original: %s", e)
    return content


def smart_compress(content: bytes, content_type: str) -> Tuple[bytes, str]:
    """Dispatch by MIME — image → image pipeline, pdf → pdf pipeline, else pass-through."""
    if content_type in ALLOWED_IMAGE_MIMES:
        return compress_image(content, content_type)
    if content_type in ALLOWED_PDF_MIMES:
        return compress_pdf(content), content_type
    return content, content_type


def sniff_magic(content: bytes) -> str:
    """Best-effort magic-byte detection — defends against malicious mime spoofing."""
    if not content or len(content) < 8:
        return "application/octet-stream"
    head = content[:12]
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    return "application/octet-stream"


def is_allowed_mime(mime: str) -> bool:
    return mime in ALLOWED_IMAGE_MIMES or mime in ALLOWED_PDF_MIMES
