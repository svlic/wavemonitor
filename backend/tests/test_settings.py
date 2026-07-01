import pytest

from wavemonitor_backend.settings import Settings


def test_settings_report_telegram_not_ready_when_env_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: optional Telegram credentials are absent from the environment.
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    # When: settings are loaded from environment.
    settings = Settings.from_env()

    # Then: the app remains usable while Telegram sending is disabled.
    assert settings.telegram_ready is False
    assert settings.telegram_bot_token is None
    assert settings.telegram_chat_id is None


def test_settings_report_telegram_ready_only_when_both_env_values_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: Telegram credentials are provided by environment variables only.
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:secret-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100987654321")

    # When: settings are loaded.
    settings = Settings.from_env()

    # Then: readiness is true and secrets are present only on runtime settings.
    assert settings.telegram_ready is True
    assert settings.telegram_bot_token == "123456:secret-token"
    assert settings.telegram_chat_id == "-100987654321"


def test_settings_schema_excludes_raw_telegram_secrets_from_safe_dump(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: runtime settings contain Telegram credentials from env.
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:secret-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100987654321")
    settings = Settings.from_env()

    # When: a public-safe settings view is produced.
    public_dump = settings.public_status()

    # Then: readiness is exposed without raw credential values.
    assert public_dump == {"telegram_ready": True}
    assert "123456:secret-token" not in str(public_dump)
    assert "-100987654321" not in str(public_dump)


def test_settings_load_web_auth_values_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the shared web password settings are provided by environment variables.
    monkeypatch.setenv("WAVEMONITOR_WEB_PASSWORD", "open-sesame")
    monkeypatch.setenv("WAVEMONITOR_SESSION_SECRET", "session-secret")

    # When: settings are loaded from environment.
    settings = Settings.from_env()

    # Then: auth is enabled without exposing the raw values in public status.
    assert settings.auth_enabled is True
    assert settings.web_password == "open-sesame"
    assert settings.session_secret == "session-secret"
    assert settings.public_status() == {"telegram_ready": False, "auth_enabled": True}


def test_settings_auth_disabled_when_password_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: only a session secret is configured.
    monkeypatch.delenv("WAVEMONITOR_WEB_PASSWORD", raising=False)
    monkeypatch.setenv("WAVEMONITOR_SESSION_SECRET", "session-secret")

    # When: settings are loaded from environment.
    settings = Settings.from_env()

    # Then: auth remains disabled until the password exists.
    assert settings.auth_enabled is False
    assert settings.web_password is None
    assert settings.session_secret == "session-secret"
