from __future__ import annotations

from os import getenv
from typing import Final, Self

from pydantic import BaseModel, ConfigDict

TELEGRAM_BOT_TOKEN_ENV: Final[str] = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV: Final[str] = "TELEGRAM_CHAT_ID"


class TelegramPublicStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    telegram_ready: bool


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_name: str = "Stock Data Monitor API"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    @classmethod
    def from_env(cls) -> Self:
        return cls(
            telegram_bot_token=getenv(TELEGRAM_BOT_TOKEN_ENV),
            telegram_chat_id=getenv(TELEGRAM_CHAT_ID_ENV),
        )

    @property
    def telegram_ready(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    def public_status(self) -> dict[str, bool]:
        return TelegramPublicStatus(telegram_ready=self.telegram_ready).model_dump()
