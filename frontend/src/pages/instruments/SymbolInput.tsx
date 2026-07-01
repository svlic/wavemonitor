import { useEffect, useId, useRef, useState } from "react";
import type { FocusEvent, SyntheticEvent } from "react";
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
  const listboxId = useId();
  const suppressListRef = useRef(false);
  const [options, setOptions] = useState<readonly SymbolOption[]>([]);
  const [state, setState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const trimmedValue = value.trim();
  const listVisible = options.length > 0;

  useEffect(() => {
    if (trimmedValue.length === 0 || trimmedValue === selectedSymbol) {
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
        if (suppressListRef.current) {
          suppressListRef.current = false;
          setOptions([]);
        } else {
          setOptions(result);
        }
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
  }, [marketType, provider, selectedSymbol, trimmedValue]);

  function selectOption(symbol: string) {
    suppressListRef.current = true;
    setSelectedSymbol(symbol.trim());
    onChange(symbol);
    setOptions([]);
  }

  function handleOptionInteraction(event: SyntheticEvent<HTMLButtonElement>) {
    event.preventDefault();
    event.stopPropagation();
    selectOption(event.currentTarget.dataset.symbol ?? event.currentTarget.textContent ?? "");
  }

  function handleBlur(event: FocusEvent<HTMLDivElement>) {
    if (!event.currentTarget.contains(event.relatedTarget)) {
      setOptions([]);
    }
  }

  return (
    <div
      className={`symbol-combobox${listVisible ? " symbol-combobox--open" : ""}`}
      onBlur={handleBlur}
    >
      <input
        id={id}
        type="text"
        value={value}
        onChange={(event) => {
          suppressListRef.current = false;
          setSelectedSymbol(null);
          onChange(event.target.value);
        }}
        placeholder="例如 BTCUSDT"
        autoComplete="off"
        role="combobox"
        aria-autocomplete="list"
        aria-controls={listboxId}
        aria-expanded={listVisible}
      />
      {state === "loading" && <p className="field-hint" role="status">正在查询 Symbol...</p>}
      {message && <p className={state === "error" ? "field-hint field-hint--error" : "field-hint"}>{message}</p>}
      {listVisible && (
        <ul id={listboxId} className="symbol-options" role="listbox" aria-label="Symbol 候选项">
          {options.map((option) => (
            <li key={`${option.provider}-${option.market_type}-${option.symbol}`} role="presentation">
              <button
                type="button"
                role="option"
                className="symbol-option"
                data-symbol={option.symbol}
                onMouseDown={handleOptionInteraction}
                onPointerDown={handleOptionInteraction}
                onTouchStart={handleOptionInteraction}
                onClick={handleOptionInteraction}
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