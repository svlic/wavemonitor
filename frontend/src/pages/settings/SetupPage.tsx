import { useState } from "react";
import { apiClient, ApiError } from "../../api/client";

type SetupPageProps = {
  onConfigured: () => void;
};

export function SetupPage({ onConfigured }: SetupPageProps) {
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [telegramBotToken, setTelegramBotToken] = useState("");
  const [telegramChatId, setTelegramChatId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError("访问密码至少需要 8 个字符。");
      return;
    }
    if (password !== passwordConfirmation) {
      setError("两次输入的访问密码不一致。");
      return;
    }
    if (Boolean(telegramBotToken.trim()) !== Boolean(telegramChatId.trim())) {
      setError("Telegram Bot Token 与 Chat ID 必须同时填写或同时留空。");
      return;
    }
    setSubmitting(true);
    try {
      await apiClient.setup({
        password,
        telegram_bot_token: telegramBotToken.trim(),
        telegram_chat_id: telegramChatId.trim(),
      });
      onConfigured();
    } catch (setupError) {
      setError(setupError instanceof ApiError ? setupError.message : "初始化失败，请重试。");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="setup-layout">
      <form className="panel setup-panel" onSubmit={handleSubmit}>
        <p className="eyebrow">WaveMonitor</p>
        <h1>初始化配置</h1>
        <p className="summary">设置管理密码，并可选配置 Telegram 告警。保存后这些敏感信息不会在界面中回显。</p>
        {error && <div className="error-banner" role="alert">{error}</div>}
        <section className="settings-section" aria-labelledby="setup-password-title">
          <h2 id="setup-password-title" className="section-title">访问保护</h2>
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="setup-password">访问密码</label>
              <input id="setup-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" required minLength={8} />
            </div>
            <div className="form-group">
              <label htmlFor="setup-password-confirmation">确认访问密码</label>
              <input id="setup-password-confirmation" type="password" value={passwordConfirmation} onChange={(event) => setPasswordConfirmation(event.target.value)} autoComplete="new-password" required minLength={8} />
            </div>
          </div>
        </section>
        <section className="settings-section" aria-labelledby="setup-telegram-title">
          <h2 id="setup-telegram-title" className="section-title">Telegram 告警（可选）</h2>
          <p className="field-hint settings-section__hint">两项同时留空可稍后在系统设置中配置。</p>
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="setup-telegram-token">Bot Token</label>
              <input id="setup-telegram-token" type="password" value={telegramBotToken} onChange={(event) => setTelegramBotToken(event.target.value)} autoComplete="off" />
            </div>
            <div className="form-group">
              <label htmlFor="setup-telegram-chat-id">Chat ID</label>
              <input id="setup-telegram-chat-id" type="text" value={telegramChatId} onChange={(event) => setTelegramChatId(event.target.value)} autoComplete="off" />
            </div>
          </div>
        </section>
        <button type="submit" className="button primary" disabled={submitting}>
          {submitting ? "保存中..." : "保存并进入"}
        </button>
      </form>
    </main>
  );
}
