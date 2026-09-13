import { useState } from "react";
import type { CreateInstrumentRequest, InstrumentWithMappings } from "../../api/client";
import {
  defaultMarketTypeForProvider,
  marketTypeLabel,
  marketTypesForProvider,
} from "../../utils/marketTypes";
import {
  validatePositivePrice,
  validateRiskRewardThreshold,
  validateSupportResistance,
  validateThreshold,
} from "../../utils/validation";
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

type AlertMode = "static" | "fixed_drawdown";

export function InstrumentForm({ initialData, onSubmit, onCancel }: Props) {
  const [name, setName] = useState(initialData?.name ?? "");
  const [enabled, setEnabled] = useState(initialData?.enabled ?? true);
  const [alertMode, setAlertMode] = useState<AlertMode>(initialData?.alert_mode ?? "static");
  const [supports, setSupports] = useState(initialData?.supports.join(", ") ?? "");
  const [resistances, setResistances] = useState(initialData?.resistances.join(", ") ?? "");
  const [highWater, setHighWater] = useState(initialData?.high_water ?? "");
  const [fixedDrawdown, setFixedDrawdown] = useState(initialData?.fixed_drawdown ?? "");
  const [nearSupportThreshold, setNearSupportThreshold] = useState(
    initialData?.near_support_threshold ?? "0.02",
  );
  const [riskRewardThreshold, setRiskRewardThreshold] = useState(
    initialData?.risk_reward_threshold ?? "3",
  );
  const [mappings, setMappings] = useState<MappingForm[]>(
    initialData?.source_mappings.map((m) => ({
      provider: m.provider,
      market_type: m.market_type,
      symbol: m.symbol,
      enabled: m.enabled,
    })) ?? [],
  );

  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const supportLevels = supports.split(/[,，\n]/).map((level) => level.trim()).filter(Boolean);
  const resistanceLevels = resistances.split(/[,，\n]/).map((level) => level.trim()).filter(Boolean);
  const hasDerivedSupport = alertMode === "fixed_drawdown";
  const hasSupport = hasDerivedSupport || supportLevels.length > 0;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError("名称不能为空");
      return;
    }

    if (alertMode === "static") {
      const srError = validateSupportResistance(supportLevels, resistanceLevels);
      if (srError) {
        setError(srError);
        return;
      }
    } else {
      const highWaterError = validatePositivePrice(highWater, "高水位");
      if (highWaterError) {
        setError(highWaterError);
        return;
      }
      const drawdownError = validatePositivePrice(fixedDrawdown, "固定回撤");
      if (drawdownError) {
        setError(drawdownError);
        return;
      }
      const derivedSupport = Number(highWater) - Number(fixedDrawdown);
      if (!Number.isFinite(derivedSupport) || derivedSupport <= 0) {
        setError("高水位减去固定回撤必须为正数");
        return;
      }
      if (resistanceLevels.length > 1) {
        setError("固定回撤模式最多填写一个阻力位");
        return;
      }
      const resistanceError = validateSupportResistance(
        [String(derivedSupport)],
        resistanceLevels,
      );
      if (resistanceError) {
        setError(resistanceError);
        return;
      }
    }

    if (hasSupport) {
      const nstError = validateThreshold(nearSupportThreshold, "接近支撑阈值");
      if (nstError) {
        setError(nstError);
        return;
      }
    }

    if (hasSupport && resistanceLevels.length > 0) {
      const rrtError = validateRiskRewardThreshold(riskRewardThreshold);
      if (rrtError) {
        setError(rrtError);
        return;
      }
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
        alert_mode: alertMode,
        supports: alertMode === "fixed_drawdown" ? [] : supportLevels,
        resistances: resistanceLevels,
        ...(alertMode === "fixed_drawdown"
          ? { high_water: highWater, fixed_drawdown: fixedDrawdown }
          : {}),
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

    if (field === "provider") {
      updatedMapping.market_type = defaultMarketTypeForProvider(String(value));
    }

    newMappings[index] = updatedMapping;
    setMappings(newMappings);
  };

  return (
    <form onSubmit={handleSubmit} className="panel form-panel">
      <p className="eyebrow">配置</p>
      <h2 className="section-title">{initialData ? "编辑标的" : "新增标的"}</h2>

      {error && <div className="error-banner" role="alert">{error}</div>}

      <div className="form-group">
        <label htmlFor="name">名称</label>
        <input
          id="name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="例如 BTC/USD"
        />
      </div>

      <div className="form-group">
        <label htmlFor="alert_mode">告警模式</label>
        <select
          id="alert_mode"
          value={alertMode}
          onChange={(e) => setAlertMode(e.target.value as AlertMode)}
        >
          <option value="static">静态价位</option>
          <option value="fixed_drawdown">固定回撤</option>
        </select>
        <span className="summary">
          {alertMode === "static"
            ? "直接填写支撑/阻力价位"
            : "支撑由高水位减去固定回撤推导"}
        </span>
      </div>

      {alertMode === "static" ? (
        <div className="form-row">
          <div className="form-group">
            <label htmlFor="support">支撑位</label>
            <input
              id="support"
              type="text"
              inputMode="decimal"
              value={supports}
              onChange={(e) => setSupports(e.target.value)}
            />
            <span className="summary">多个数值用逗号分隔</span>
          </div>
          <div className="form-group">
            <label htmlFor="resistance">阻力位</label>
            <input
              id="resistance"
              type="text"
              inputMode="decimal"
              value={resistances}
              onChange={(e) => setResistances(e.target.value)}
            />
            <span className="summary">多个数值用逗号分隔</span>
          </div>
        </div>
      ) : (
        <div className="form-row">
          <div className="form-group">
            <label htmlFor="high_water">高水位</label>
            <input
              id="high_water"
              type="text"
              inputMode="decimal"
              value={highWater}
              onChange={(e) => setHighWater(e.target.value)}
            />
          </div>
          <div className="form-group">
            <label htmlFor="fixed_drawdown">固定回撤</label>
            <input
              id="fixed_drawdown"
              type="text"
              inputMode="decimal"
              value={fixedDrawdown}
              onChange={(e) => setFixedDrawdown(e.target.value)}
            />
            <span className="summary">绝对价格幅度，不是百分比</span>
          </div>
          <div className="form-group">
            <label htmlFor="resistance">阻力位</label>
            <input
              id="resistance"
              type="text"
              inputMode="decimal"
              value={resistances}
              onChange={(e) => setResistances(e.target.value)}
            />
            <span className="summary">可选，最多一个</span>
          </div>
        </div>
      )}

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
            onChange={(e) => setNearSupportThreshold(e.target.value)}
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
            onChange={(e) => setRiskRewardThreshold(e.target.value)}
          />
        </div>
      </div>

      <div className="form-group checkbox-group">
        <label>
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
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
                onChange={(e) => updateMapping(i, "provider", e.target.value)}
              >
                <option value="yfinance">Yahoo Finance</option>
                <option value="binance">Binance</option>
                <option value="hyperliquid">Hyperliquid</option>
              </select>
            </div>
            <div className="form-group">
              <label htmlFor={`market-type-${i}`}>市场类型</label>
              <select
                id={`market-type-${i}`}
                value={m.market_type}
                onChange={(e) => updateMapping(i, "market_type", e.target.value)}
              >
                {marketTypesForProvider(m.provider).map((marketType) => (
                  <option key={marketType} value={marketType}>
                    {marketTypeLabel(marketType)}
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
            <div className="form-group checkbox-group">
              <label>
                <input
                  type="checkbox"
                  checked={m.enabled}
                  onChange={(e) => updateMapping(i, "enabled", e.target.checked)}
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
