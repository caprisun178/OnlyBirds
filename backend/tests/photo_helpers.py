"""Builds small in-memory test images with real EXIF — no fixture files
committed, no network. Shared by test_photo_metadata.py, test_uploads.py and
test_identify.py."""

from __future__ import annotations

import io

from PIL import ExifTags, Image

# Raleigh, NC — 35°46'46.56"N, 78°38'17.52"W
RALEIGH_LAT, RALEIGH_LNG = 35.7796, -78.6382
RALEIGH_GPS = {
    1: "N",
    2: (35.0, 46.0, 46.56),
    3: "W",
    4: (78.0, 38.0, 17.52),
}


def make_image(
    fmt: str = "JPEG",
    gps: dict | None = None,
    taken_at: str | None = None,
    modified_at: str | None = None,
    orientation: int | None = None,
    size: tuple[int, int] = (40, 20),
) -> bytes:
    """A `size` image whose left half is red and right half blue, so a
    rotation is detectable from the pixels alone."""
    img = Image.new("RGB", size, "blue")
    img.paste("red", (0, 0, size[0] // 2, size[1]))

    exif = Image.Exif()
    if gps is not None:
        exif[ExifTags.IFD.GPSInfo] = gps
    if taken_at is not None:
        exif[ExifTags.IFD.Exif] = {ExifTags.Base.DateTimeOriginal: taken_at}
    if modified_at is not None:
        exif[ExifTags.Base.DateTime] = modified_at
    if orientation is not None:
        exif[ExifTags.Base.Orientation] = orientation

    out = io.BytesIO()
    kwargs = {"exif": exif.tobytes()} if len(exif) else {}
    img.save(out, format=fmt, **kwargs)
    return out.getvalue()
