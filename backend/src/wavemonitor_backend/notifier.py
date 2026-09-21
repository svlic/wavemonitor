from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from json import dumps, loads
from typing import Final, Protocol, TypeAlias, assert_never
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from wavemonitor_backend.models import AlertKind
from wavemonitor_backend.rules import risk_reward_ratio
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
    threshold: Decimal | None = None
    metric: Decimal | None = None
    triggered_at: datetime | None = None


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
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "MarkdownV2"}
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


DISPLAY_TIME_ZONE: Final[ZoneInfo] = ZoneInfo("Asia/Shanghai")
ZERO: Final[Decimal] = Decimal("0")
HUNDRED: Final[Decimal] = Decimal("100")
TWO_PLACES: Final[Decimal] = Decimal("0.01")

ALERT_KIND_LABELS: Final[dict[AlertKind, str]] = {
    AlertKind.NEAR_SUPPORT: "接近支撑",
    AlertKind.RISK_REWARD: "风险回报达标",
    AlertKind.RESISTANCE_BREAKOUT: "突破阻力",
    AlertKind.SUPPORT_BREACH: "跌破支撑",
}

PROVIDER_LABELS: Final[dict[str, str]] = {
    "yfinance": "Yahoo Finance",
    "binance": "Binance",
    "hyperliquid": "Hyperliquid",
}

MARKET_TYPE_LABELS: Final[dict[str, str]] = {
    "equity": "股票",
    "usd_m_futures": "USD-M 合约",
    "coin_m_futures": "COIN-M 合约",
    "perpetual": "永续合约",
}


def escape_telegram_markdown_v2(text: str) -> str:
    """Escape user-controlled text for Telegram MarkdownV2 (outside code/pre blocks)."""
    special = r"_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{ch}" if ch in special else ch for ch in text)


def format_telegram_alert(alert: TelegramAlert) -> str:
    rule_label = ALERT_KIND_LABELS[alert.rule]
    lines = [
        _bold("WaveMonitor 告警"),
        _bold(rule_label),
        escape_telegram_markdown_v2(alert.instrument),
        escape_telegram_markdown_v2(_source_label(alert.source)),
        "",
        escape_telegram_markdown_v2(_alert_summary(alert)),
        "",
        _labeled("现价", _format_price(alert.price)),
    ]
    if _show_support(alert):
        lines.append(_labeled("支撑", _level_with_distance(alert.price, alert.support, below=True)))
    if _show_resistance(alert):
        lines.append(
            _labeled("阻力", _level_with_distance(alert.price, alert.resistance, below=False))
        )
    risk_reward = _displayed_risk_reward(alert)
    if risk_reward is not None:
        lines.append(_labeled("风险回报", _format_decimal(risk_reward)))
    if alert.rule is AlertKind.RISK_REWARD and alert.threshold is not None:
        lines.append(_labeled("阈值", _format_decimal(alert.threshold)))
    if alert.triggered_at is not None:
        lines.append(_labeled("时间", _format_triggered_at(alert.triggered_at)))
    return "\n".join(lines)


def _bold(text: str) -> str:
    return f"*{escape_telegram_markdown_v2(text)}*"


def _labeled(label: str, value: str) -> str:
    return f"{_bold(label)} {escape_telegram_markdown_v2(value)}"


def _source_label(source: str) -> str:
    provider, separator, remainder = source.partition(":")
    if separator == "":
        return source
    market_type, market_separator, symbol = remainder.partition(":")
    if market_separator == "":
        return source
    provider_label = PROVIDER_LABELS.get(provider, provider)
    market_label = MARKET_TYPE_LABELS.get(market_type, market_type)
    return f"{provider_label} · {market_label} · {symbol}"


def _alert_summary(alert: TelegramAlert) -> str:
    price = _format_price(alert.price)
    support = _format_price(alert.support)
    resistance = _format_price(alert.resistance)
    match alert.rule:
        case AlertKind.NEAR_SUPPORT:
            distance = _distance_detail(alert.price, alert.support, below=True)
            threshold = (
                f"，接近阈值 {_format_percent(alert.threshold * HUNDRED)}"
                if alert.threshold is not None
                else ""
            )
            if distance is None:
                return f"现价 {price} 已贴近支撑 {support}{threshold}。"
            return f"现价 {price} 已贴近支撑 {support}，{distance}{threshold}。"
        case AlertKind.RISK_REWARD:
            ratio = (
                alert.metric
                if alert.metric is not None
                else risk_reward_ratio(
                    price=alert.price, support=alert.support, resistance=alert.resistance
                )
            )
            ratio_text = _format_decimal(ratio) if ratio is not None else "已达标"
            if alert.threshold is not None:
                return (
                    f"现价 {price} 的风险回报已达 {ratio_text}，"
                    f"阈值 {_format_decimal(alert.threshold)}。"
                )
            return f"现价 {price} 的风险回报已达 {ratio_text}。"
        case AlertKind.RESISTANCE_BREAKOUT:
            overshoot = _format_price(alert.price - alert.resistance)
            return f"现价 {price} 已上破阻力 {resistance}，高出 {overshoot}。"
        case AlertKind.SUPPORT_BREACH:
            undershoot = _format_price(alert.support - alert.price)
            return f"现价 {price} 已跌破支撑 {support}，低出 {undershoot}。"
        case _ as unreachable:
            assert_never(unreachable)


def _show_support(alert: TelegramAlert) -> bool:
    if alert.rule in {AlertKind.NEAR_SUPPORT, AlertKind.SUPPORT_BREACH, AlertKind.RISK_REWARD}:
        return True
    return alert.support != alert.price


def _show_resistance(alert: TelegramAlert) -> bool:
    if alert.rule in {AlertKind.RESISTANCE_BREAKOUT, AlertKind.RISK_REWARD}:
        return True
    return alert.resistance != alert.price


def _level_with_distance(price: Decimal, level: Decimal, *, below: bool) -> str:
    formatted = _format_price(level)
    detail = _distance_detail(price, level, below=below)
    if detail is None:
        return formatted
    return f"{formatted}（{detail}）"


def _distance_detail(price: Decimal, level: Decimal, *, below: bool) -> str | None:
    delta = (price - level) if below else (level - price)
    if delta <= ZERO:
        return None
    percent = (delta / price) * HUNDRED if price > ZERO else None
    if percent is None:
        return f"相差 {_format_price(delta)}"
    return f"相差 {_format_price(delta)} / {_format_percent(percent)}"


def _displayed_risk_reward(alert: TelegramAlert) -> Decimal | None:
    if alert.rule is AlertKind.RISK_REWARD and alert.metric is not None:
        return alert.metric
    return risk_reward_ratio(price=alert.price, support=alert.support, resistance=alert.resistance)


def _format_price(value: Decimal) -> str:
    normalized = format(value.normalize(), "f")
    if "." not in normalized:
        return f"{normalized}.00"
    decimals = len(normalized.split(".", 1)[1])
    if decimals < 2:
        return format(value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP), "f")
    return normalized


def _format_decimal(value: Decimal, places: int = 2) -> str:
    quantum = Decimal(10) ** -places
    return format(value.quantize(quantum, rounding=ROUND_HALF_UP), "f")


def _format_percent(value: Decimal) -> str:
    return f"{_format_decimal(value)}%"


def _format_triggered_at(value: datetime) -> str:
    stamped = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    local = stamped.astimezone(DISPLAY_TIME_ZONE)
    return local.strftime("%Y-%m-%d %H:%M:%S UTC+8")


def message_for_kind(kind: MessageKind, alert: TelegramAlert | None) -> str:
    match kind:
        case MessageKind.TEST | MessageKind.ALERT:
            if alert is None:
                return escape_telegram_markdown_v2("WaveMonitor Telegram test message.")
            return format_telegram_alert(alert)
        case _ as unreachable:
            assert_never(unreachable)


def sanitize_telegram_failure(result: TelegramHttpFailure) -> str:
    return f"Telegram delivery failed with HTTP {result.status_code}."
