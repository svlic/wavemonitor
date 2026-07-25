from __future__ import annotations

from os import getenv
from typing import Final, Self

from pydantic import BaseModel, ConfigDict

from wavemonitor_backend.db import database_url_from_env
from wavemonitor_backend.session_secrets import resolve_session_signing_secret

TELEGRAM_BOT_TOKEN_ENV: Final[str] = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV: Final[str] = "TELEGRAM_CHAT_ID"
WEB_PASSWORD_ENV: Final[str] = "WAVEMONITOR_WEB_PASSWORD"
SESSION_SECRET_ENV: Final[str] = "WAVEMONITOR_SESSION_SECRET"


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_name: str = "Stock Data Monitor API"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    web_password: str | None = None
    session_secret: str | None = None

    @classmethod
    def from_env(cls, *, database_url: str | None = None) -> Self:
        web_password = getenv(WEB_PASSWORD_ENV)
        env_session_secret = getenv(SESSION_SECRET_ENV)
        auth_enabled = bool(web_password)
        session_secret = resolve_session_signing_secret(
            auth_enabled=auth_enabled,
            env_session_secret=env_session_secret,
            database_url=database_url or database_url_from_env(),
        )
        return cls(
            telegram_bot_token=getenv(TELEGRAM_BOT_TOKEN_ENV),
            telegram_chat_id=getenv(TELEGRAM_CHAT_ID_ENV),
            web_password=web_password,
            session_secret=session_secret,
        )

    @property
    def telegram_ready(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def auth_enabled(self) -> bool:
        return bool(self.web_password)
