import type { AlertDecision, EnabledSource, Env } from "./types";

const special = /[_*\[\]()~`>#+\-=|{}.!]/g;
export function escapeMarkdown(value: string): string { return value.replace(special, "\\$&"); }
export function alertMessage(source: EnabledSource, alert: AlertDecision): string { return ["*WaveMonitor alert*", `*Instrument:* ${escapeMarkdown(source.instrument_name)}`, `*Source:* ${escapeMarkdown(`${source.provider}:${source.market_type}:${source.symbol}`)}`, `*Rule:* ${escapeMarkdown(alert.kind)}`, `*Price:* ${escapeMarkdown(alert.price)}`, `*Support:* ${escapeMarkdown(alert.support)}`, `*Resistance:* ${escapeMarkdown(alert.resistance)}`].join("\n"); }
export async function sendTelegram(env: Env, text: string): Promise<{ status: "sent" | "failed"; messageId: string | null; safeError: string | null } | null> {
  if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID) return null;
  let lastStatus = 502;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text, parse_mode: "MarkdownV2" }) });
      lastStatus = response.status;
      if (response.ok) { const payload = await response.json() as { result?: { message_id?: string | number } }; return { status: "sent", messageId: String(payload.result?.message_id ?? "unknown"), safeError: null }; }
      if (response.status !== 429 && response.status < 500) break;
    } catch { lastStatus = 502; }
  }
  return { status: "failed", messageId: null, safeError: `Telegram delivery failed with HTTP ${lastStatus}.` };
}
