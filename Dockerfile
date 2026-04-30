# syntax=docker/dockerfile:1.7
# Python dependencies are installed with pip only here (inside the image), not on the host.
FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN --mount=type=cache,id=quantumpath-pip-cache,target=/root/.cache/pip,sharing=locked python -m pip install --upgrade pip && python -m pip install -r backend/requirements.txt

COPY backend/ backend/
COPY docs/VERSION docs/VERSION

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
