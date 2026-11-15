"""Bookmark photo storage: disk layout, content-based type sniffing, thumbnails.

Security notes: the image type is determined from the bytes (never from the
client's Content-Type or filename), storage names are server-generated, and
the user id (an arbitrary header value) is reduced to a safe path component.
"""

import hashlib
import io
import logging
import os
import re
import shutil
import uuid
import warnings

try:  # Pillow is optional at runtime; without it we serve full images.
    from PIL import Image, ImageOps
    PILLOW_AVAILABLE = True
except ImportError:  # pragma: no cover
    Image = ImageOps = None
    PILLOW_AVAILABLE = False

log = logging.getLogger(__name__)

THUMB_SIZE = 320
THUMB_SUFFIX = ".thumb.jpg"
ALLOWED = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png"), "WEBP": ("image/webp", "webp")}
ALLOWED_MIMES = {m for m, _ in ALLOWED.values()}
_EXT_BY_MIME = {m: e for m, e in ALLOWED.values()}
_warned = False


class UnsupportedImageType(ValueError):
    """Bytes decode as an image (or look like one) of a type we don't accept."""


def _warn_no_pillow():
    global _warned
    if not _warned:
        _warned = True
        log.warning("Pillow unavailable: bookmark photo thumbnails disabled, serving full images")


def _safe_component(value):
    s = str(value)
    if re.fullmatch(r"[a-z0-9_@\-][a-z0-9_@.\-]*", s):
        return s
    return "u-" + hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()[:32]


def photo_dir(data_dir, user_id, bookmark_uuid):
    if not re.fullmatch(r"[0-9a-f]{32}", str(bookmark_uuid)):
        raise ValueError("invalid bookmark uuid")
    return os.path.join(data_dir, "bookmarks", _safe_component(user_id), bookmark_uuid)


def _sniff_magic(data):
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _open_checked(data):
    """Open + verify, returning the image format; bombs/corruption -> ValueError."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            with Image.open(io.BytesIO(data)) as im:
                fmt = im.format
                if fmt not in ALLOWED:
                    raise UnsupportedImageType(f"unsupported image format {fmt}")
                im.verify()
        except UnsupportedImageType:
            raise
        except Exception as e:  # DecompressionBomb*, UnidentifiedImageError, truncated...
            raise ValueError(f"not a valid image: {e.__class__.__name__}") from e
    return fmt


def detect_mime(data):
    """Return the verified MIME type of ``data``; ValueError if not a decodable
    image, UnsupportedImageType if it is an image of another type."""
    if not data:
        raise ValueError("empty file")
    if not PILLOW_AVAILABLE:
        _warn_no_pillow()
        mime = _sniff_magic(data)
        if mime is None:
            raise UnsupportedImageType("unsupported or unrecognised image")
        return mime
    return ALLOWED[_open_checked(data)][0]


def _make_thumb(data):
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im)
            im.thumbnail((THUMB_SIZE, THUMB_SIZE))
            if im.mode in ("RGBA", "LA", "P"):
                rgba = im.convert("RGBA")
                bg = Image.new("RGB", rgba.size, (255, 255, 255))
                bg.paste(rgba, mask=rgba.getchannel("A"))
                im = bg
            else:
                im = im.convert("RGB")
            out = io.BytesIO()
            im.save(out, "JPEG", quality=82)
            return out.getvalue()


def save_photo(data_dir, user_id, bookmark_uuid, file_bytes, mime):
    """Verify and store an image; returns (storage_name, byte_size).

    ``mime`` is the caller's claim and must match the content-detected type.
    Raises ValueError (UnsupportedImageType for wrong types) before writing
    anything; on a write failure partial files are removed.
    """
    detected = detect_mime(file_bytes)
    if detected != mime:
        raise UnsupportedImageType("content does not match declared type")
    thumb = None
    if PILLOW_AVAILABLE:
        try:
            thumb = _make_thumb(file_bytes)
        except Exception as e:
            raise ValueError(f"cannot decode image: {e.__class__.__name__}") from e
    folder = photo_dir(data_dir, user_id, bookmark_uuid)
    os.makedirs(folder, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{_EXT_BY_MIME[detected]}"
    try:
        with open(os.path.join(folder, name), "xb") as f:
            f.write(file_bytes)
        if thumb is not None:
            with open(os.path.join(folder, name + THUMB_SUFFIX), "xb") as f:
                f.write(thumb)
    except Exception:
        remove_photo_files(data_dir, user_id, bookmark_uuid, name)
        raise
    return name, len(file_bytes)


def photo_path(data_dir, user_id, bookmark_uuid, storage_name, thumb=False):
    name = os.path.basename(storage_name) + (THUMB_SUFFIX if thumb else "")
    return os.path.join(photo_dir(data_dir, user_id, bookmark_uuid), name)


def remove_photo_files(data_dir, user_id, bookmark_uuid, storage_name):
    for thumb in (False, True):
        try:
            os.remove(photo_path(data_dir, user_id, bookmark_uuid, storage_name, thumb))
        except FileNotFoundError:
            pass


def remove_bookmark_dir(data_dir, user_id, bookmark_uuid):
    shutil.rmtree(photo_dir(data_dir, user_id, bookmark_uuid), ignore_errors=True)
