from celery import shared_task


@shared_task
def ping_worker():
    """Cheap task to verify Celery workers are consuming (remove or replace later)."""
    return "pong"
