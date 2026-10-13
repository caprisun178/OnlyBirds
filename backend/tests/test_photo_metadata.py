import io
from datetime import datetime

import pytest
from PIL import ExifTags, Image

from app.dao import photo_metadata
from tests.photo_helpers import RALEIGH_GPS, RALEIGH_LAT, RALEIGH_LNG, make_image


def test_read_returns_gps_and_capture_time():
    meta = photo_metadata.read(make_image(gps=RALEIGH_GPS, taken_at="2026:09:14 07:42:10"))
    assert meta["lat"] == pytest.approx(RALEIGH_LAT, abs=1e-4)
    assert meta["lng"] == pytest.approx(RALEIGH_LNG, abs=1e-4)  # "W" -> negative
    assert meta["taken_at"] == datetime(2026, 9, 14, 7, 42, 10)


def test_read_applies_south_and_east_signs():
    gps = {1: "S", 2: (33.0, 51.0, 54.0), 3: "E", 4: (151.0, 12.0, 36.0)}  # Sydney
    meta = photo_metadata.read(make_image(gps=gps))
    assert meta["lat"] == pytest.approx(-33.865, abs=1e-3)
    assert meta["lng"] == pytest.approx(151.21, abs=1e-3)
    assert meta["taken_at"] is None


def test_read_treats_zero_zero_as_missing():
    gps = {1: "N", 2: (0.0, 0.0, 0.0), 3: "E", 4: (0.0, 0.0, 0.0)}
    assert photo_metadata.read(make_image(gps=gps)) is None


def test_read_rejects_out_of_range_coordinates():
    gps = {1: "N", 2: (95.0, 0.0, 0.0), 3: "E", 4: (10.0, 0.0, 0.0)}
    assert photo_metadata.read(make_image(gps=gps)) is None


def test_read_ignores_last_modified_time():
    # Base `DateTime` is when the file was last edited, not when the bird
    # was seen — using it would date an edited photo to its edit day.
    assert photo_metadata.read(make_image(modified_at="2026:10:01 12:00:00")) is None


def test_read_ignores_unset_camera_timestamp():
    assert photo_metadata.read(make_image(taken_at="0000:00:00 00:00:00")) is None


def test_read_with_no_exif_or_non_image_returns_none():
    assert photo_metadata.read(make_image()) is None
    assert photo_metadata.read(b"not an image") is None


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_strip_removes_all_metadata(fmt):
    original = make_image(fmt=fmt, gps=RALEIGH_GPS, taken_at="2026:09:14 07:42:10")
    assert photo_metadata.read(original) is not None  # sanity: it was there

    clean, content_type = photo_metadata.strip(original)

    assert content_type == f"image/{fmt.lower()}"
    assert photo_metadata.read(clean) is None
    with Image.open(io.BytesIO(clean)) as img:
        assert len(img.getexif()) == 0
        assert "exif" not in img.info


def test_strip_bakes_in_orientation():
    # Orientation 6 = "rotate 90° clockwise to display". Once the tag is
    # gone, the pixels themselves must already be rotated, or phone photos
    # would be stored sideways.
    original = make_image(orientation=6, size=(40, 20))
    clean, _ = photo_metadata.strip(original)
    with Image.open(io.BytesIO(clean)) as img:
        assert img.size == (20, 40)
        assert ExifTags.Base.Orientation not in img.getexif()
        # Red was the left half; rotated clockwise it becomes the top half.
        top, bottom = img.convert("RGB").getpixel((10, 5)), img.convert("RGB").getpixel((10, 35))
        assert top[0] > 200 and top[2] < 60
        assert bottom[2] > 200 and bottom[0] < 60


def test_strip_reports_actual_format_not_claimed_one():
    # The content type comes from the decoded bytes, so a mislabelled file
    # is stored with an honest type/extension.
    _, content_type = photo_metadata.strip(make_image(fmt="PNG"))
    assert content_type == "image/png"


def test_strip_passes_gif_through_unchanged():
    gif = make_image(fmt="GIF")
    assert photo_metadata.strip(gif) == (gif, "image/gif")


def test_strip_rejects_non_image():
    with pytest.raises(photo_metadata.UnreadableImage):
        photo_metadata.strip(b"not an image")
