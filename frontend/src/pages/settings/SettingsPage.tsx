import { useEffect, useState } from "react";
import { apiClient, ApiError } from "../../api/client";

type LoadState = "loading" | "ready" | "error";

export function SettingsPage() {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [telegramEnabled, setTelegramEnabled] = useState(false);
  const [telegramBotToken, setTelegramBotToken] = useState("");
  const [telegramChatId, setTelegramChatId] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    apiClient.getSettings(controller.signal).then((settings) => {
      setTelegramEnabled(settings.telegram_enabled);
      setLoadState("ready");
    }).catch((loadError) => {
      if (loadError instanceof DOMException && loadError.name === "AbortError") return;
      setError(loadError instanceof ApiError ? loadError.message : "配置加载失败。");
      setLoadState("error");
    });
    return () => controller.abort();
  }, []);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setMessage(null);
    setError(null);
    if (newPassword && newPassword.length < 8) {
      setError("新密码至少需要 8 个字符。");
      return;
    }
    if (newPassword !== passwordConfirmation) {
      setError("两次输入的新密码不一致。");
      return;
    }
    if (telegramEnabled && Boolean(telegramBotToken.trim()) !== Boolean(telegramChatId.trim())) {
      setError("更新 Telegram 凭据时，Bot Token 与 Chat ID 必须同时填写。");
      return;
    }
    setSubmitting(true);
    try {
      const settings = await apiClient.updateSettings({
        new_password: newPassword,
        telegram_enabled: telegramEnabled,
        telegram_bot_token: telegramBotToken.trim(),
        telegram_chat_id: telegramChatId.trim(),
      });
      setTelegramEnabled(settings.telegram_enabled);
      setNewPassword("");
      setPasswordConfirmation("");
      setTelegramBotToken("");
      setTelegramChatId("");
      setMessage("配置已保存。");
    } catch (updateError) {
      setError(updateError instanceof ApiError ? updateError.message : "保存失败，请重试。");
    } finally {
      setSubmitting(false);
    }
  };

  if (loadState === "loading") {
    return <section className="panel loading-panel" role="status">正在加载配置...</section>;
  }
  if (loadState === "error") {
    return <section className="panel"><div className="error-banner" role="alert">{error}</div></section>;
  }

  return (
    <form className="settings-layout" onSubmit={handleSubmit}>
      {error && <div className="error-banner" role="alert">{error}</div>}
      {message && <p className="success-text" role="status">{message}</p>}
      <section className="panel settings-card" aria-labelledby="password-settings-title">
        <h2 id="password-settings-title" className="panel-title">访问密码</h2>
        <p className="muted-text panel-title-sub">留空表示不修改。修改后其他浏览器中的旧会话将失效。</p>
        <div className="form-row">
          <div className="form-group">
            <label htmlFor="settings-password">新密码</label>
            <input id="settings-password" type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} autoComplete="new-password" minLength={8} />
          </div>
          <div className="form-group">
            <label htmlFor="settings-password-confirmation">确认新密码</label>
            <input id="settings-password-confirmation" type="password" value={passwordConfirmation} onChange={(event) => setPasswordConfirmation(event.target.value)} autoComplete="new-password" minLength={8} />
          </div>
        </div>
      </section>
      <section className="panel settings-card" aria-labelledby="telegram-settings-title">
        <h2 id="telegram-settings-title" className="panel-title">Telegram 告警</h2>
        <p className="muted-text panel-title-sub">已保存的 Token 不会回显。保持输入框为空即可沿用现有凭据。</p>
        <div className="checkbox-group">
          <label htmlFor="telegram-enabled">
            <input id="telegram-enabled" type="checkbox" checked={telegramEnabled} onChange={(event) => setTelegramEnabled(event.target.checked)} />
            启用 Telegram 推送
          </label>
        </div>
        {telegramEnabled && (
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="settings-telegram-token">新 Bot Token（可留空）</label>
              <input id="settings-telegram-token" type="password" value={telegramBotToken} onChange={(event) => setTelegramBotToken(event.target.value)} autoComplete="off" />
            </div>
            <div className="form-group">
              <label htmlFor="settings-telegram-chat-id">新 Chat ID（可留空）</label>
              <input id="settings-telegram-chat-id" type="text" value={telegramChatId} onChange={(event) => setTelegramChatId(event.target.value)} autoComplete="off" />
            </div>
          </div>
        )}
      </section>
      <div className="settings-actions">
        <button type="submit" className="button primary" disabled={submitting}>{submitting ? "保存中..." : "保存配置"}</button>
      </div>
    </form>
  );
}
