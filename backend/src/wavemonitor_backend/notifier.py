from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from json import dumps, loads
from typing import Final, Protocol, TypeAlias, assert_never
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from wavemonitor_backend.models import AlertKind
from wavemonitor_backend.settings import Settings


class MessageKind(StrEnum):
    TEST = "test"
    ALERT = "alert"


@dataclass(frozen=True, slots=True)
class TelegramAlert:
    instrument: str
    source: str
    rule: AlertKind
    price: Decimal
    support: Decimal
    resistance: Decimal


@dataclass(frozen=True, slots=True)
class TelegramSendSuccess:
    message_id: str


@dataclass(frozen=True, slots=True)
class TelegramHttpFailure:
    status_code: int
    description: str


TelegramSendResult: TypeAlias = TelegramSendSuccess | TelegramHttpFailure

TELEGRAM_SEND_MAX_ATTEMPTS: Final[int] = 3
TELEGRAM_RETRY_BASE_DELAY_SECONDS: Final[float] = 0.25


def _telegram_failure_is_retryable(result: TelegramHttpFailure) -> bool:
    if result.status_code == 429:
        return True
    return result.status_code >= 500


class TelegramTransport(Protocol):
    def post_json(self, url: str, payload: dict[str, str]) -> TelegramSendResult: ...


class UrllibTelegramTransport:
    def post_json(self, url: str, payload: dict[str, str]) -> TelegramSendResult:
        body = dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=10) as response:
                raw_response = response.read().decode("utf-8")
        except HTTPError as exc:
            return TelegramHttpFailure(status_code=exc.code, description="Telegram HTTP error")
        except URLError as exc:
            return TelegramHttpFailure(status_code=502, description=exc.reason)
        payload_data = loads(raw_response)
        result = payload_data.get("result", {}) if isinstance(payload_data, dict) else {}
        message_id = result.get("message_id") if isinstance(result, dict) else None
        return TelegramSendSuccess(message_id=str(message_id or "unknown"))


class TelegramNotifier:
    def __init__(self, settings: Settings, transport: TelegramTransport | None = None) -> None:
        self._settings = settings
        self._transport = transport or UrllibTelegramTransport()

    @property
    def ready(self) -> bool:
        return self._settings.telegram_ready

    def send_text(self, text: str) -> TelegramSendResult | None:
        if not self.ready:
            return None
        token = self._settings.telegram_bot_token
        chat_id = self._settings.telegram_chat_id
        if token is None or chat_id is None:
            return None
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        last_result: TelegramSendResult | None = None
        for attempt in range(TELEGRAM_SEND_MAX_ATTEMPTS):
            last_result = self._transport.post_json(url, payload)
            if isinstance(last_result, TelegramSendSuccess):
                return last_result
            if not _telegram_failure_is_retryable(last_result):
                return last_result
            if attempt < TELEGRAM_SEND_MAX_ATTEMPTS - 1:
                time.sleep(TELEGRAM_RETRY_BASE_DELAY_SECONDS * (2**attempt))
        return last_result


def format_telegram_alert(alert: TelegramAlert) -> str:
    return "\n".join(
        (
            "WaveMonitor alert",
            f"Instrument: {alert.instrument}",
            f"Source: {alert.source}",
            f"Rule: {alert.rule.value}",
            f"Price: {alert.price}",
            f"Support: {alert.support}",
            f"Resistance: {alert.resistance}",
        )
    )


def message_for_kind(kind: MessageKind, alert: TelegramAlert | None) -> str:
    match kind:
        case MessageKind.TEST:
            if alert is None:
                return "WaveMonitor Telegram test message."
            return format_telegram_alert(alert)
        case MessageKind.ALERT:
            if alert is None:
                return "WaveMonitor Telegram test message."
            return format_telegram_alert(alert)
        case _ as unreachable:
            assert_never(unreachable)


def sanitize_telegram_failure(result: TelegramHttpFailure) -> str:
    return f"Telegram delivery failed with HTTP {result.status_code}."
