import type { InstrumentWithMappings, LatestPrice } from "../../api/client";
import { formatDateTime, formatSourceLabel } from "../../utils/format";
import {
  computeResistanceDistancePercent,
  computeRiskRewardRatio,
  computeSupportDistancePercent,
  formatMetricPercent,
  formatRiskReward,
} from "../../utils/instrumentMetrics";

type PriceMonitorPanelProps = {
  readonly prices: readonly LatestPrice[];
  readonly instruments: readonly InstrumentWithMappings[];
};

type InstrumentPriceGroup = {
  readonly instrumentId: number;
  readonly instrumentName: string;
  readonly rows: readonly LatestPrice[];
};

function groupPricesByInstrument(prices: readonly LatestPrice[]): readonly InstrumentPriceGroup[] {
  const order: number[] = [];
  const buckets = new Map<number, LatestPrice[]>();

  for (const price of prices) {
    const existing = buckets.get(price.instrument_id);
    if (existing === undefined) {
      order.push(price.instrument_id);
      buckets.set(price.instrument_id, [price]);
    } else {
      existing.push(price);
    }
  }

  return order.map((instrumentId) => {
    const rows = buckets.get(instrumentId) ?? [];
    return {
      instrumentId,
      instrumentName: rows[0]?.instrument_name ?? String(instrumentId),
      rows,
    };
  });
}

type SourcePriceCardProps = {
  readonly price: LatestPrice;
  readonly support: string | undefined;
  readonly resistance: string | undefined;
};

function SourcePriceCard({ price, support, resistance }: SourcePriceCardProps) {
  const supportPct =
    support !== undefined ? computeSupportDistancePercent(price.last_price, support) : null;
  const resistancePct =
    resistance !== undefined
      ? computeResistanceDistancePercent(price.last_price, resistance)
      : null;
  const riskReward =
    support !== undefined && resistance !== undefined
      ? computeRiskRewardRatio(price.last_price, support, resistance)
      : null;

  return (
    <article className="price-source-card">
      <header className="price-source-card__head">
        <h4 className="price-source-card__source">
          {formatSourceLabel(price.provider, price.market_type, price.symbol)}
        </h4>
        <time className="price-source-card__time muted-text" dateTime={price.last_observed_at}>
          {formatDateTime(price.last_observed_at)}
        </time>
      </header>
      <dl className="price-source-card__fields">
        <div className="price-field">
          <dt className="price-field__label">价格</dt>
          <dd className="price-field__value price-field__value--primary">{price.last_price}</dd>
        </div>
        <div className="price-field">
          <dt className="price-field__label">距支撑</dt>
          <dd className="price-field__value">{formatMetricPercent(supportPct)}</dd>
        </div>
        <div className="price-field">
          <dt className="price-field__label">距阻力</dt>
          <dd className="price-field__value">{formatMetricPercent(resistancePct)}</dd>
        </div>
        <div className="price-field">
          <dt className="price-field__label">盈亏比</dt>
          <dd className="price-field__value">{formatRiskReward(riskReward)}</dd>
        </div>
      </dl>
    </article>
  );
}

export function PriceMonitorPanel({ prices, instruments }: PriceMonitorPanelProps) {
  if (prices.length === 0) {
    return <p className="empty-state">暂无价格数据。</p>;
  }

  const instrumentById = new Map(instruments.map((item) => [item.id, item]));
  const groups = groupPricesByInstrument(prices);

  return (
    <div className="price-monitor">
      {groups.map((group) => {
        const instrument = instrumentById.get(group.instrumentId);
        const support = instrument?.support;
        const resistance = instrument?.resistance;

        return (
          <section
            key={group.instrumentId}
            className="price-monitor__instrument"
            aria-labelledby={`price-instrument-${group.instrumentId}`}
          >
            <header className="price-monitor__header">
              <div className="price-monitor__title-row">
                <h3 id={`price-instrument-${group.instrumentId}`} className="price-monitor__title">
                  {group.instrumentName}
                </h3>
              </div>
              {instrument !== undefined && (
                <div className="price-monitor__levels">
                  <span className="level-chip level-chip--support">
                    <span className="level-chip__label">支撑</span>
                    <span className="level-chip__value">{instrument.support}</span>
                  </span>
                  <span className="level-chip level-chip--resistance">
                    <span className="level-chip__label">阻力</span>
                    <span className="level-chip__value">{instrument.resistance}</span>
                  </span>
                </div>
              )}
            </header>
            <div className="price-monitor__sources">
              {group.rows.map((price) => (
                <SourcePriceCard
                  key={price.source_mapping_id}
                  price={price}
                  support={support}
                  resistance={resistance}
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}