import type { InstrumentWithMappings, LatestPrice } from "../../api/client";
import { formatDateTime, formatOptionalLevel, formatSourceLabel } from "../../utils/format";
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

type InstrumentPriceBucket = {
  readonly instrumentId: number;
  readonly rows: readonly LatestPrice[];
};

type SourceMapping = InstrumentWithMappings["source_mappings"][number];

type SourcePriceRow = {
  readonly price: LatestPrice;
  readonly source: SourceMapping;
};

type InstrumentPriceGroup = {
  readonly instrument: InstrumentWithMappings;
  readonly rows: readonly SourcePriceRow[];
};

function groupPricesByInstrument(prices: readonly LatestPrice[]): readonly InstrumentPriceBucket[] {
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

  return order.map((instrumentId) => ({
    instrumentId,
    rows: buckets.get(instrumentId) ?? [],
  }));
}

type SourcePriceCardProps = {
  readonly price: LatestPrice;
  readonly source: SourceMapping;
  readonly support: string | undefined;
  readonly resistance: string | undefined;
};

function SourcePriceCard({ price, source, support, resistance }: SourcePriceCardProps) {
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
          {formatSourceLabel(source.provider, source.market_type, source.symbol)}
        </h4>
        <time className="price-source-card__time muted-text" dateTime={price.last_observed_at}>
          {formatDateTime(price.last_observed_at)}
        </time>
      </header>
      <dl className="price-source-card__fields">
        <div className="price-field price-field--hero">
          <dt className="price-field__label">价格</dt>
          <dd className="price-field__value price-field__value--primary">{price.last_price}</dd>
        </div>
        <div className="price-source-card__metrics">
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
  const groups: InstrumentPriceGroup[] = [];

  for (const bucket of groupPricesByInstrument(prices)) {
    const instrument = instrumentById.get(bucket.instrumentId);
    if (instrument === undefined || !instrument.enabled) {
      continue;
    }

    const sourceById = new Map(instrument.source_mappings.map((source) => [source.id, source]));
    const rows = bucket.rows.flatMap((price) => {
      const source = sourceById.get(price.source_mapping_id);
      return source === undefined || !source.enabled ? [] : [{ price, source }];
    });
    if (rows.length > 0) {
      groups.push({ instrument, rows });
    }
  }

  if (groups.length === 0) {
    return <p className="empty-state">暂无价格数据。</p>;
  }

  return (
    <div className="price-monitor">
      {groups.map((group) => {
        const { instrument } = group;
        const support = instrument.support;
        const resistance = instrument.resistance;

        return (
          <section
            key={instrument.id}
            className="price-monitor__instrument"
            aria-labelledby={`price-instrument-${instrument.id}`}
          >
            <header className="price-monitor__header">
              <div className="price-monitor__title-row">
                <h3 id={`price-instrument-${instrument.id}`} className="price-monitor__title">
                  {instrument.name}
                </h3>
              </div>
              <div className="price-monitor__levels">
                <span className="level-chip level-chip--support">
                  <span className="level-chip__label">支撑</span>
                  <span className="level-chip__value">{formatOptionalLevel(instrument.support)}</span>
                </span>
                <span className="level-chip level-chip--resistance">
                  <span className="level-chip__label">阻力</span>
                  <span className="level-chip__value">{formatOptionalLevel(instrument.resistance)}</span>
                </span>
              </div>
            </header>
            <div className="price-monitor__sources">
              {group.rows.map((row) => (
                <SourcePriceCard
                  key={row.price.source_mapping_id}
                  price={row.price}
                  source={row.source}
                  support={support ?? undefined}
                  resistance={resistance ?? undefined}
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}