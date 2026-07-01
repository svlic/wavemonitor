import { useEffect, useState } from "react";
import { apiClient, ApiError } from "../../api/client";
import type { SymbolOption } from "../../api/client";

type Props = {
  id: string;
  provider: string;
  marketType: string;
  value: string;
  onChange: (value: string) => void;
};

export function SymbolInput({ id, provider, marketType, value, onChange }: Props) {
  const [options, setOptions] = useState<readonly SymbolOption[]>([]);
  const [state, setState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const trimmedValue = value.trim();

  useEffect(() => {
    if (trimmedValue.length === 0) {
      setOptions([]);
      setState("idle");
      setMessage(null);
      return;
    }

    const controller = new AbortController();
    setState("loading");
    setMessage(null);

    async function query() {
      try {
        const result = await apiClient.querySymbols(provider, marketType, trimmedValue, controller.signal);
        setOptions(result);
        setState("ready");
        setMessage(result.length === 0 ? "没有匹配的 Symbol，可继续手动输入。" : null);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setOptions([]);
        setState("error");
        setMessage(error instanceof ApiError ? error.message : "Symbol 查询失败，可继续手动输入。");
      }
    }

    query();
    return () => controller.abort();
  }, [marketType, provider, trimmedValue]);

  return (
    <div className="symbol-combobox">
      <input
        id={id}
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="例如 BTCUSDT"
        autoComplete="off"
        aria-controls={`${id}-options`}
        aria-expanded={options.length > 0}
      />
      {state === "loading" && <p className="field-hint" role="status">正在查询 Symbol...</p>}
      {message && <p className={state === "error" ? "field-hint field-hint--error" : "field-hint"}>{message}</p>}
      {options.length > 0 && (
        <ul id={`${id}-options`} className="symbol-options" role="listbox" aria-label="Symbol 候选项">
          {options.map((option) => (
            <li key={`${option.provider}-${option.market_type}-${option.symbol}`}>
              <button
                type="button"
                role="option"
                className="symbol-option"
                onClick={() => onChange(option.symbol)}
              >
                {option.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
