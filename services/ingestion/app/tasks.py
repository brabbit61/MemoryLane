from celery import Celery

from app.config import settings

celery_app = Celery(
    "ingestion",
    broker=settings.celery_broker_url,
    backend=settings.celery_backend_url,
)


def dispatch_enrich_photo(photo_id: str) -> None:
    celery_app.send_task("workers.tasks.enrich_photo", args=[photo_id])
