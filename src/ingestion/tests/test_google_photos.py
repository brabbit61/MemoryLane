from datetime import UTC

from app.services.google_photos import parse_picked_item


def test_parse_picked_item_full_payload() -> None:
    item = {
        "id": "AGNCw_abc",
        "createTime": "2024-08-15T19:23:45Z",
        "type": "PHOTO",
        "mediaFile": {
            "baseUrl": "https://lh3.googleusercontent.com/abc",
            "mimeType": "image/jpeg",
            "filename": "IMG_1234.jpg",
            "mediaFileMetadata": {
                "width": "4032",  # API returns strings for width/height
                "height": "3024",
                "cameraMake": "Apple",
                "cameraModel": "iPhone 14",
                "photoMetadata": {
                    "focalLength": 4.25,
                    "apertureFNumber": 1.78,
                    "isoEquivalent": 100,
                    "exposureTime": "0.04s",
                },
            },
        },
    }

    parsed = parse_picked_item(item)
    assert parsed is not None
    assert parsed.external_id == "AGNCw_abc"
    assert parsed.base_url == "https://lh3.googleusercontent.com/abc"
    assert parsed.item_type == "PHOTO"
    assert parsed.mime_type == "image/jpeg"
    assert parsed.filename == "IMG_1234.jpg"
    assert parsed.width == 4032
    assert parsed.height == 3024
    assert parsed.taken_at is not None
    assert parsed.taken_at.year == 2024
    assert parsed.taken_at.month == 8
    assert parsed.taken_at.tzinfo == UTC
    assert parsed.exif_data == {
        "source": "picker_api",
        "camera_make": "Apple",
        "camera_model": "iPhone 14",
        "focal_length": 4.25,
        "aperture_f_number": 1.78,
        "iso_equivalent": 100,
        "exposure_time": "0.04s",
    }


def test_parse_picked_item_minimal_payload() -> None:
    """Only id + baseUrl + mimeType provided; everything else is optional."""
    item = {
        "id": "x",
        "mediaFile": {
            "baseUrl": "https://lh3.googleusercontent.com/x",
            "mimeType": "image/jpeg",
        },
    }

    parsed = parse_picked_item(item)
    assert parsed is not None
    assert parsed.external_id == "x"
    assert parsed.item_type == "PHOTO"  # default when type field is absent
    assert parsed.filename is None
    assert parsed.width is None
    assert parsed.height is None
    assert parsed.taken_at is None
    assert parsed.exif_data == {"source": "picker_api"}


def test_parse_picked_item_returns_none_when_id_missing() -> None:
    item: dict[str, object] = {
        "mediaFile": {"baseUrl": "https://lh3.googleusercontent.com/x"},
    }
    assert parse_picked_item(item) is None


def test_parse_picked_item_returns_none_when_base_url_missing() -> None:
    item = {"id": "x", "mediaFile": {"mimeType": "image/jpeg"}}
    assert parse_picked_item(item) is None


def test_parse_picked_item_returns_none_when_media_file_missing() -> None:
    item: dict[str, object] = {"id": "x"}
    assert parse_picked_item(item) is None


def test_parse_picked_item_keeps_video_type_for_caller_to_filter() -> None:
    """Parser returns the row; sync.py decides whether to skip videos."""
    item = {
        "id": "v",
        "type": "VIDEO",
        "mediaFile": {"baseUrl": "https://lh3.googleusercontent.com/v", "mimeType": "video/mp4"},
    }

    parsed = parse_picked_item(item)
    assert parsed is not None
    assert parsed.item_type == "VIDEO"


def test_parse_picked_item_tolerates_unparseable_create_time() -> None:
    item = {
        "id": "x",
        "createTime": "not-a-date",
        "mediaFile": {"baseUrl": "https://lh3.googleusercontent.com/x", "mimeType": "image/jpeg"},
    }

    parsed = parse_picked_item(item)
    assert parsed is not None
    assert parsed.taken_at is None
