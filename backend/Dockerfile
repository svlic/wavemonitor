FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY backend ./backend

RUN pip install --no-cache-dir .

RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "wavemonitor_backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
