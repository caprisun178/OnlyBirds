"""Photo EXIF metadata — read where/when a photo was taken, and strip it
before the photo is stored. See `docs/features/photo-metadata.md`.

Pure file-format parsing, no network — lives in `dao/` for the same reason
`bioclip_classifier.py` does: it's raw byte handling services shouldn't
touch directly.

**Why strip at all:** `POST /uploads/photo` stores into a *public* bucket,
so anything left in the file — most importantly the GPS position, often the
uploader's home or garden — is readable by anyone with the observation's
`photo_url`.
"""

from __future__ import annotations

import io
from datetime import datetime

import pillow_heif
from PIL import ExifTags, Image, ImageOps

# Lets Pillow open iPhone HEIC/HEIF files everywhere in the process —
# including bioclip_classifier's Image.open — once this module is imported.
pillow_heif.register_heif_opener()

# Decoded format -> format the stored copy is written as.
_OUTPUT_FORMAT = {
    "JPEG": "JPEG",
    "MPO": "JPEG",
    "HEIF": "JPEG",
    "PNG": "PNG",
    "WEBP": "WEBP",
    "GIF": "GIF",
}
_FORMAT_TO_CONTENT_TYPE = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}

# GPS IFD tag numbers (EXIF spec) — Pillow's ExifTags.GPS enum names them,
# but plain ints keep the lookups below readable next to the spec.
_GPS_LAT_REF, _GPS_LAT, _GPS_LNG_REF, _GPS_LNG = 1, 2, 3, 4

_EXIF_DATETIME_FORMAT = "%Y:%m:%d %H:%M:%S"


class UnreadableImage(ValueError):
    """The bytes aren't an image Pillow can open and re-save."""


def read(image_bytes: bytes) -> dict | None:
    """`{lat, lng, taken_at}` from the photo's EXIF, each `None` when
    missing or unusable — or `None` overall when nothing usable was found.
    Never raises: a photo with broken or absent metadata just has none, it
    isn't an error (manual entry is always the fallback).

    `taken_at` is EXIF `DateTimeOriginal` only, returned as a naive
    datetime — the photo's local wall-clock time, which is what the user
    would type into the When & Where field anyway. Deliberately *not* the
    base `DateTime` tag: that's the last-modified time, so an edited photo
    would report its edit date.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            exif = img.getexif()
            gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
            exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)
    except Exception:
        return None

    lat = _coordinate(gps.get(_GPS_LAT), gps.get(_GPS_LAT_REF), limit=90)
    lng = _coordinate(gps.get(_GPS_LNG), gps.get(_GPS_LNG_REF), limit=180)
    if lat is None or lng is None or (lat == 0 and lng == 0):
        # 0,0 is a common bad-default value, not a real sighting in the Gulf of Guinea.
        lat = lng = None

    taken_at = _parse_exif_datetime(exif_ifd.get(ExifTags.Base.DateTimeOriginal))

    if lat is None and taken_at is None:
        return None
    return {"lat": lat, "lng": lng, "taken_at": taken_at}


def strip(image_bytes: bytes, max_edge: int | None = None) -> tuple[bytes, str]:
    """Re-saves the image without EXIF/XMP metadata and returns
    `(bytes, content_type)` — the content type of what was actually
    written, from the decoded format rather than whatever the client
    claimed. Raises `UnreadableImage` if Pillow can't open it.

    Orientation is applied to the pixels first (`exif_transpose`), since the
    orientation tag goes away with the rest of the EXIF — skipping that
    would store phone photos sideways (same bug class as
    `docs/features/bird-id.md` §1).

    `max_edge`, when given, shrinks the image so its longer side is at most
    that many pixels (never enlarges). Uploads pass one so a 25 MB camera
    original isn't stored at full resolution (docs/features/bulk-import.md).

    Camera JPEGs that Pillow opens as MPO (a JPEG with an extra embedded
    preview frame) and iPhone HEIC files are stored as plain JPEG: browsers
    other than Safari can't display HEIC, and only MPO's main frame matters.

    GIFs and animated WebP/PNG pass through untouched: GIFs carry no EXIF,
    and re-saving an animation here would keep only its first frame.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except Exception as exc:
        raise UnreadableImage("Couldn't read that image.") from exc

    out_fmt = _OUTPUT_FORMAT.get(img.format)
    if out_fmt is None:
        raise UnreadableImage(f"Unsupported image format '{img.format}'.")
    content_type = _FORMAT_TO_CONTENT_TYPE[out_fmt]
    if img.format == "GIF" or (img.format != "MPO" and getattr(img, "is_animated", False)):
        return image_bytes, content_type

    icc_profile = img.info.get("icc_profile")
    img = ImageOps.exif_transpose(img)  # also leaves just MPO's main frame
    # Pillow falls back to `img.info` for some metadata (e.g. XMP) when
    # saving — clear it so nothing rides along, keeping only the colour
    # profile (not identifying, and dropping it would shift colours).
    img.info = {}
    if max_edge and max(img.size) > max_edge:
        img.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)

    save_kwargs: dict = {}
    if icc_profile:
        save_kwargs["icc_profile"] = icc_profile
    if out_fmt == "JPEG":
        if img.mode not in ("RGB", "L", "CMYK"):
            img = img.convert("RGB")
        save_kwargs["quality"] = 90
    elif out_fmt == "WEBP":
        save_kwargs["quality"] = 90

    out = io.BytesIO()
    img.save(out, format=out_fmt, **save_kwargs)
    return out.getvalue(), content_type


def _coordinate(dms, ref, limit: float) -> float | None:
    """EXIF degrees/minutes/seconds rationals + an N/S/E/W ref -> signed
    decimal degrees, or `None` if anything is missing or out of range."""
    if not dms or not ref or len(dms) != 3:
        return None
    try:
        degrees, minutes, seconds = (float(part) for part in dms)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    value = degrees + minutes / 60 + seconds / 3600
    ref = ref.decode() if isinstance(ref, bytes) else str(ref)
    if ref.strip().upper() in ("S", "W"):
        value = -value
    if value != value or abs(value) > limit:  # NaN (a 0/0 rational) or out of range
        return None
    return round(value, 6)


def _parse_exif_datetime(raw) -> datetime | None:
    if not raw:
        return None
    raw = raw.decode() if isinstance(raw, bytes) else str(raw)
    try:
        return datetime.strptime(raw.strip("\x00 ")[:19], _EXIF_DATETIME_FORMAT)
    except ValueError:
        return None  # e.g. the "0000:00:00 00:00:00" some cameras write when unset
