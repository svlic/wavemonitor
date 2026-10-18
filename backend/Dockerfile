# syntax=docker/dockerfile:1
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
# Keep dependency installation cached when only application code changes.
RUN --mount=type=cache,target=/root/.cache/pip \
    python -c 'import pathlib, tomllib; pathlib.Path("/tmp/requirements.txt").write_text("\n".join(tomllib.loads(pathlib.Path("pyproject.toml").read_text())["project"]["dependencies"]) + "\n")' \
    && pip install --disable-pip-version-check -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY backend/src ./backend/src
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --disable-pip-version-check --no-deps . \
    && pip check

RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "wavemonitor_backend.app:get_application", "--factory", "--host", "0.0.0.0", "--port", "8000"]
