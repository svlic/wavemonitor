import type { InstrumentWithMappings, LatestPrice } from "../../api/client";
import { formatDateTime, formatDecimal, formatOptionalLevel, formatSourceLabel } from "../../utils/format";
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

function SourcePriceRow({ price, source, support, resistance }: SourcePriceCardProps) {
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
  const sourceLabel = formatSourceLabel(source.provider, source.market_type, source.symbol);

  return (
    <tr className="price-source-row">
      <th scope="row" className="price-source-row__source">
        <span className="price-source-row__source-label">{sourceLabel}</span>
        <time className="price-source-row__time muted-text" dateTime={price.last_observed_at}>
          {formatDateTime(price.last_observed_at)}
        </time>
      </th>
      <td className="price-source-row__price">{formatDecimal(price.last_price)}</td>
      <td className="price-source-row__metric">{formatMetricPercent(supportPct)}</td>
      <td className="price-source-row__metric">{formatMetricPercent(resistancePct)}</td>
      <td className="price-source-row__metric">{formatRiskReward(riskReward)}</td>
    </tr>
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

  groups.sort((left, right) => left.instrument.name.localeCompare(right.instrument.name));

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
            <header className="price-monitor__header price-monitor__header--compact">
              <h3 id={`price-instrument-${instrument.id}`} className="price-monitor__title">
                {instrument.name}
              </h3>
              <p className="price-monitor__levels-inline muted-text">
                <span>
                  支撑{" "}
                  <span className="price-monitor__level-value">{formatOptionalLevel(instrument.support)}</span>
                </span>
                <span className="price-monitor__levels-sep" aria-hidden="true">
                  ·
                </span>
                <span>
                  阻力{" "}
                  <span className="price-monitor__level-value">{formatOptionalLevel(instrument.resistance)}</span>
                </span>
              </p>
            </header>
            <div className="price-monitor__table-wrap">
              <table className="price-monitor__table">
                <thead>
                  <tr>
                    <th scope="col">来源</th>
                    <th scope="col">价格</th>
                    <th scope="col">距支撑</th>
                    <th scope="col">距阻力</th>
                    <th scope="col">盈亏比</th>
                  </tr>
                </thead>
                <tbody>
                  {group.rows.map((row) => (
                    <SourcePriceRow
                      key={row.price.source_mapping_id}
                      price={row.price}
                      source={row.source}
                      support={support ?? undefined}
                      resistance={resistance ?? undefined}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}
    </div>
  );
}