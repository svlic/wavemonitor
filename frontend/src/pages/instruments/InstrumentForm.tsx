import { useState } from "react";
import type { CreateInstrumentRequest, InstrumentWithMappings } from "../../api/client";
import { validateSupportResistance, validateThreshold, validateRiskRewardThreshold } from "../../utils/validation";

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
  const [nearSupportThreshold, setNearSupportThreshold] = useState(initialData?.near_support_threshold ?? "");
  const [riskRewardThreshold, setRiskRewardThreshold] = useState(initialData?.risk_reward_threshold ?? "");
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
      setError("Name is required");
      return;
    }

    const srError = validateSupportResistance(support, resistance);
    if (srError) {
      setError(srError);
      return;
    }

    const nstError = validateThreshold(nearSupportThreshold, "Near support threshold");
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
      setError("At least one source mapping is required");
      return;
    }

    for (const m of mappings) {
      if (!m.symbol.trim()) {
        setError("All source mappings must have a symbol");
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
      setError(err instanceof Error ? err.message : "Failed to save instrument");
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
      if (value === "yfinance") updatedMapping.market_type = "equity";
      else if (value === "hyperliquid") updatedMapping.market_type = "perpetual";
      else if (value === "binance") updatedMapping.market_type = "usd_m_futures";
    }
    
    newMappings[index] = updatedMapping;
    setMappings(newMappings);
  };

  return (
    <form onSubmit={handleSubmit} className="panel form-panel">
      <h2>{initialData ? "Edit Instrument" : "New Instrument"}</h2>
      
      {error && <div className="error-banner" role="alert">{error}</div>}

      <div className="form-group">
        <label htmlFor="name">Name</label>
        <input
          id="name"
          type="text"
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="e.g. BTC/USD"
        />
      </div>

      <div className="form-row">
        <div className="form-group">
          <label htmlFor="support">Support Level</label>
          <input
            id="support"
            type="number"
            step="any"
            value={support}
            onChange={e => setSupport(e.target.value)}
          />
        </div>
        <div className="form-group">
          <label htmlFor="resistance">Resistance Level</label>
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
          <label htmlFor="near_support_threshold">Near Support Threshold (0-1)</label>
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
          <label htmlFor="risk_reward_threshold">Risk Reward Threshold (&gt;0)</label>
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
          Enable monitoring
        </label>
      </div>

      <div className="mappings-section">
        <div className="header-row">
          <h3>Source Mappings</h3>
          <button type="button" onClick={addMapping} className="button small">Add Source</button>
        </div>
        
        {mappings.length === 0 && <p className="summary">Add at least one source to monitor this instrument.</p>}
        
        {mappings.map((m, i) => (
          <div key={i} className="mapping-row">
            <div className="form-group">
              <label htmlFor={`provider-${i}`}>Provider</label>
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
              <label htmlFor={`market_type-${i}`}>Market Type</label>
              <select
                id={`market_type-${i}`}
                value={m.market_type}
                onChange={e => updateMapping(i, "market_type", e.target.value)}
              >
                <option value="equity">Equity</option>
                <option value="usd_m_futures">USD-M Futures</option>
                <option value="coin_m_futures">COIN-M Futures</option>
                <option value="perpetual">Perpetual</option>
              </select>
            </div>
            <div className="form-group">
              <label htmlFor={`symbol-${i}`}>Symbol</label>
              <input
                id={`symbol-${i}`}
                type="text"
                value={m.symbol}
                onChange={e => updateMapping(i, "symbol", e.target.value)}
                placeholder="e.g. BTCUSDT"
              />
            </div>
            <div className="form-group checkbox-group mapping-enabled">
              <label>
                <input
                  type="checkbox"
                  checked={m.enabled}
                  onChange={e => updateMapping(i, "enabled", e.target.checked)}
                />
                Active
              </label>
            </div>
            <button type="button" onClick={() => removeMapping(i)} className="button small danger">Remove</button>
          </div>
        ))}
      </div>

      <div className="form-actions">
        <button type="button" onClick={onCancel} className="button" disabled={isSubmitting}>Cancel</button>
        <button type="submit" className="button primary" disabled={isSubmitting}>
          {isSubmitting ? "Saving..." : "Save Instrument"}
        </button>
      </div>
    </form>
  );
}
