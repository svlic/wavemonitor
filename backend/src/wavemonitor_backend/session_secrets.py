from __future__ import annotations

import secrets
from contextlib import suppress
from pathlib import Path
from urllib.parse import unquote, urlparse

SESSION_SECRET_FILENAME: str = "session_secret"
SESSION_SECRET_BYTES: int = 32


def session_secret_path_for_database_url(database_url: str) -> Path:
    """Return the filesystem path where an auto-generated session secret is stored."""
    if database_url.startswith("sqlite"):
        parsed = urlparse(database_url)
        if parsed.path in {"", "/"}:
            return Path.cwd() / SESSION_SECRET_FILENAME
        raw_path = unquote(parsed.path)
        if raw_path.startswith("//"):
            raw_path = "/" + raw_path.lstrip("/")
        if parsed.netloc in {"", "localhost"} and raw_path.startswith("/"):
            db_path = Path(raw_path)
        elif parsed.netloc:
            db_path = Path(parsed.netloc) / raw_path.lstrip("/")
        else:
            db_path = Path(raw_path)
        if db_path.is_absolute():
            return db_path.parent / SESSION_SECRET_FILENAME
        return Path.cwd() / db_path.parent / SESSION_SECRET_FILENAME
    return Path("/data") / SESSION_SECRET_FILENAME


def load_or_create_persisted_session_secret(path: Path) -> str:
    """Load an existing secret from disk or create one with restrictive permissions."""
    if path.is_file():
        secret = path.read_text(encoding="utf-8").strip()
        if secret:
            return secret
    path.parent.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_urlsafe(SESSION_SECRET_BYTES)
    path.write_text(f"{secret}\n", encoding="utf-8")
    with suppress(OSError):
        path.chmod(0o600)
    return secret


def resolve_session_signing_secret(
    *,
    auth_enabled: bool,
    env_session_secret: str | None,
    database_url: str,
) -> str | None:
    """Resolve cookie signing secret: env override, else persisted auto-secret when auth is on."""
    if env_session_secret:
        return env_session_secret
    if not auth_enabled:
        return None
    path = session_secret_path_for_database_url(database_url)
    return load_or_create_persisted_session_secret(path)
