# syntax=docker/dockerfile:1.7
# Python dependencies are installed with pip only here (inside the image), not on the host.
# Cloud Run / Cloud Build: docker build --target app-cloudrun .
FROM python:3.12-slim AS base

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt

FROM base AS deps-plain
RUN python -m pip install --upgrade pip && python -m pip install -r backend/requirements.txt

# No BuildKit pip cache mount — Cloud Run / some remote builders handle cache mounts poorly.
FROM deps-plain AS app
COPY backend/ backend/
COPY docs/VERSION docs/VERSION
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM app AS app-cloudrun
