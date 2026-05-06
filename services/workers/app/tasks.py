import contextlib
import io
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import boto3
from PIL import Image
from sqlalchemy import update

from app.clip_model import encode_image
from app.config import settings
from app.db import get_db_session
from app.models import Photo, PhotoEmbedding
from app.worker import celery_app

logger = logging.getLogger(__name__)


def _s3_client() -> Any:
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )


def _extract_exif(image: Image.Image) -> dict[str, object]:
    exif: dict[str, object] = {}
    try:
        raw = image.getexif()
        if raw:
            exif["width"] = image.width
            exif["height"] = image.height

            # DateTimeOriginal tag = 36867
            if 36867 in raw:
                with contextlib.suppress(ValueError):
                    exif["taken_at"] = (
                        datetime.strptime(str(raw[36867]), "%Y:%m:%d %H:%M:%S")
                        .replace(tzinfo=UTC)
                        .isoformat()
                    )

            # GPS IFD tag = 34853
            gps_ifd = raw.get_ifd(0x8825)
            if gps_ifd:
                lat = _dms_to_decimal(gps_ifd.get(2), gps_ifd.get(1))
                lon = _dms_to_decimal(gps_ifd.get(4), gps_ifd.get(3))
                if lat is not None:
                    exif["latitude"] = lat
                if lon is not None:
                    exif["longitude"] = lon
    except Exception:
        logger.debug("EXIF extraction failed", exc_info=True)
    return exif


def _dms_to_decimal(
    dms: object,
    ref: object,
) -> float | None:
    if not dms or not isinstance(dms, (list, tuple)) or len(dms) < 3:
        return None
    try:
        degrees = float(dms[0])
        minutes = float(dms[1])
        seconds = float(dms[2])
        value = degrees + minutes / 60 + seconds / 3600
        if str(ref) in ("S", "W"):
            value = -value
        return value
    except (TypeError, ValueError):
        return None


def _generate_thumbnails(
    image: Image.Image,
    s3_key_base: str,
    s3: Any,
) -> None:
    for size in (256, 1024):
        thumb = image.copy()
        thumb.thumbnail((size, size), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        thumb.save(buf, format="JPEG")
        thumb_key = s3_key_base.replace("originals/", f"thumbnails/{size}/", 1)
        s3.put_object(
            Bucket=settings.s3_bucket_photos,
            Key=thumb_key,
            Body=buf.getvalue(),
            ContentType="image/jpeg",
        )


def _enrich(photo_id: str) -> None:
    with get_db_session() as db:
        photo = db.get(Photo, uuid.UUID(photo_id))
        if photo is None:
            return

        s3 = _s3_client()
        resp = s3.get_object(Bucket=settings.s3_bucket_photos, Key=photo.s3_key)
        photo_bytes = resp["Body"].read()

        image = Image.open(io.BytesIO(photo_bytes)).convert("RGB")

        _generate_thumbnails(image, photo.s3_key, s3)

        exif = _extract_exif(image)

        embedding_vec = encode_image(image)

        existing_emb = db.query(PhotoEmbedding).filter(PhotoEmbedding.photo_id == photo.id).first()
        if existing_emb is None:
            emb = PhotoEmbedding(
                tenant_id=photo.tenant_id,
                user_id=photo.user_id,
                photo_id=photo.id,
                embedding=embedding_vec,
            )
            db.add(emb)
        else:
            existing_emb.embedding = embedding_vec

        update_vals: dict[str, object] = {
            "status": "enriched",
            "updated_at": datetime.now(tz=UTC),
            "width": exif.get("width", photo.width),
            "height": exif.get("height", photo.height),
        }
        if "taken_at" in exif:
            update_vals["taken_at"] = datetime.fromisoformat(str(exif["taken_at"]))
        if "latitude" in exif:
            update_vals["latitude"] = exif["latitude"]
        if "longitude" in exif:
            update_vals["longitude"] = exif["longitude"]

        db.execute(update(Photo).where(Photo.id == photo.id).values(**update_vals))
        db.commit()


@celery_app.task(bind=True, name="workers.tasks.enrich_photo", max_retries=3)  # type: ignore[untyped-decorator]
def enrich_photo(self: Any, photo_id: str) -> None:
    try:
        _enrich(photo_id)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60) from exc
