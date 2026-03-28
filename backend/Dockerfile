# Single image for web, Celery worker, and Celery beat (override CMD per Render service).
FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# collectstatic requires SECRET_KEY and ALLOWED_HOSTS; runtime env on Render replaces these.
ARG COLLECTSTATIC_SECRET=build-only-secret-not-used-at-runtime
ARG COLLECTSTATIC_ALLOWED_HOSTS=localhost
ENV DJANGO_SECRET_KEY=${COLLECTSTATIC_SECRET} \
    ALLOWED_HOSTS=${COLLECTSTATIC_ALLOWED_HOSTS}

RUN python manage.py collectstatic --noinput

EXPOSE 8000

# Scale horizontally: more web instances behind Render load balancer; tune workers/RAM.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "120"]
