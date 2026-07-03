import { useState } from "react";
import type { CreateInstrumentRequest, InstrumentWithMappings } from "../../api/client";
import {
  defaultMarketTypeForProvider,
  marketTypeLabel,
  marketTypesForProvider,
} from "../../utils/marketTypes";
import { validateSupportResistance, validateThreshold, validateRiskRewardThreshold } from "../../utils/validation";
import { SymbolInput } from "./SymbolInput";

type Props = {
  initialData?: InstrumentWithMappings;
  onSubmit: (data: CreateInstrumentRequest) => Promise<void>;
  onCancel: () => void;
};

type MappingForm = {
  provider: string;
  market_type: string;
  symbol: string;
  enabled: boolean;
};

export function InstrumentForm({ initialData, onSubmit, onCancel }: Props) {
  const [name, setName] = useState(initialData?.name ?? "");
  const [enabled, setEnabled] = useState(initialData?.enabled ?? true);
  const [support, setSupport] = useState(initialData?.support ?? "");
  const [resistance, setResistance] = useState(initialData?.resistance ?? "");
  const [nearSupportThreshold, setNearSupportThreshold] = useState(
    initialData?.near_support_threshold ?? "0.02",
  );
  const [riskRewardThreshold, setRiskRewardThreshold] = useState(
    initialData?.risk_reward_threshold ?? "3",
  );
  const [mappings, setMappings] = useState<MappingForm[]>(
    initialData?.source_mappings.map(m => ({
      provider: m.provider,
      market_type: m.market_type,
      symbol: m.symbol,
      enabled: m.enabled,
    })) ?? []
  );
  
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError("名称不能为空");
      return;
    }

    const srError = validateSupportResistance(support, resistance);
    if (srError) {
      setError(srError);
      return;
    }

    const nstError = validateThreshold(nearSupportThreshold, "接近支撑阈值");
    if (nstError) {
      setError(nstError);
      return;
    }

    const rrtError = validateRiskRewardThreshold(riskRewardThreshold);
    if (rrtError) {
      setError(rrtError);
      return;
    }

    if (mappings.length === 0) {
      setError("至少需要一个数据源映射");
      return;
    }

    for (const m of mappings) {
      if (!m.symbol.trim()) {
        setError("所有数据源映射都必须填写 Symbol");
        return;
      }
    }

    setIsSubmitting(true);
    try {
      await onSubmit({
        name,
        enabled,
        support,
        resistance,
        near_support_threshold: nearSupportThreshold,
        risk_reward_threshold: riskRewardThreshold,
        source_mappings: mappings,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存标的失败");
    } finally {
      setIsSubmitting(false);
    }
  };

  const addMapping = () => {
    setMappings([...mappings, { provider: "yfinance", market_type: "equity", symbol: "", enabled: true }]);
  };

  const removeMapping = (index: number) => {
    setMappings(mappings.filter((_, i) => i !== index));
  };

  const updateMapping = <K extends keyof MappingForm>(index: number, field: K, value: MappingForm[K]) => {
    const newMappings = [...mappings];
    const currentMapping = newMappings[index];
    if (!currentMapping) return;

    const updatedMapping = { ...currentMapping, [field]: value };
    
    // Auto-set market_type based on provider if needed
    if (field === "provider") {
      updatedMapping.market_type = defaultMarketTypeForProvider(String(value));
    }
    
    newMappings[index] = updatedMapping;
    setMappings(newMappings);
  };

  return (
    <form onSubmit={handleSubmit} className="panel form-panel">
      <h2>{initialData ? "编辑标的" : "新增标的"}</h2>
      
      {error && <div className="error-banner" role="alert">{error}</div>}

      <div className="form-group">
        <label htmlFor="name">名称</label>
        <input
          id="name"
          type="text"
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="例如 BTC/USD"
        />
      </div>

      <div className="form-row">
        <div className="form-group">
          <label htmlFor="support">支撑位</label>
          <input
            id="support"
            type="number"
            step="any"
            value={support}
            onChange={e => setSupport(e.target.value)}
          />
        </div>
        <div className="form-group">
          <label htmlFor="resistance">阻力位</label>
          <input
            id="resistance"
            type="number"
            step="any"
            value={resistance}
            onChange={e => setResistance(e.target.value)}
          />
        </div>
      </div>
      
      <div className="form-row">
        <div className="form-group">
          <label htmlFor="near_support_threshold">接近支撑阈值 (0-1)</label>
          <input
            id="near_support_threshold"
            type="number"
            step="0.01"
            min="0.01"
            max="0.99"
            value={nearSupportThreshold}
            onChange={e => setNearSupportThreshold(e.target.value)}
          />
        </div>
        <div className="form-group">
          <label htmlFor="risk_reward_threshold">风险回报阈值 (&gt;0)</label>
          <input
            id="risk_reward_threshold"
            type="number"
            step="0.1"
            min="0.1"
            value={riskRewardThreshold}
            onChange={e => setRiskRewardThreshold(e.target.value)}
          />
        </div>
      </div>

      <div className="form-group checkbox-group">
        <label>
          <input
            type="checkbox"
            checked={enabled}
            onChange={e => setEnabled(e.target.checked)}
          />
          启用监控
        </label>
      </div>

      <div className="mappings-section">
        <div className="header-row">
          <h3>数据源映射</h3>
          <button type="button" onClick={addMapping} className="button small">添加来源</button>
        </div>
        
        {mappings.length === 0 && <p className="summary">至少添加一个数据源来监控此标的。</p>}
        
        {mappings.map((m, i) => (
          <div key={i} className="mapping-row">
            <div className="form-group">
              <label htmlFor={`provider-${i}`}>数据源</label>
              <select
                id={`provider-${i}`}
                value={m.provider}
                onChange={e => updateMapping(i, "provider", e.target.value)}
              >
                <option value="yfinance">Yahoo Finance</option>
                <option value="binance">Binance</option>
                <option value="hyperliquid">Hyperliquid</option>
              </select>
            </div>
            <div className="form-group">
              <label htmlFor={`market_type-${i}`}>市场类型</label>
              <select
                id={`market_type-${i}`}
                value={m.market_type}
                onChange={e => updateMapping(i, "market_type", e.target.value)}
              >
                {marketTypesForProvider(m.provider).map(mt => (
                  <option key={mt} value={mt}>
                    {marketTypeLabel(mt)}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label htmlFor={`symbol-${i}`}>Symbol</label>
              <SymbolInput
                id={`symbol-${i}`}
                provider={m.provider}
                marketType={m.market_type}
                value={m.symbol}
                onChange={(value) => updateMapping(i, "symbol", value)}
              />
            </div>
            <div className="form-group checkbox-group mapping-enabled">
              <label>
                <input
                  type="checkbox"
                  checked={m.enabled}
                  onChange={e => updateMapping(i, "enabled", e.target.checked)}
                />
                启用
              </label>
            </div>
            <button type="button" onClick={() => removeMapping(i)} className="button small danger">移除</button>
          </div>
        ))}
      </div>

      <div className="form-actions">
        <button type="button" onClick={onCancel} className="button" disabled={isSubmitting}>取消</button>
        <button type="submit" className="button primary" disabled={isSubmitting}>
          {isSubmitting ? "保存中..." : "保存标的"}
        </button>
      </div>
    </form>
  );
}
