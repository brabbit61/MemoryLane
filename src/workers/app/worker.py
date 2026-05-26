from celery import Celery

from app.config import settings

celery_app = Celery(
    "workers",
    broker=settings.celery_broker_url,
    backend=settings.celery_backend_url,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={"workers.tasks.enrich_photo": {"queue": "enrichment"}},
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)
