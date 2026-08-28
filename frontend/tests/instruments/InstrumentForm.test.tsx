import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { InstrumentForm } from "../../src/pages/instruments/InstrumentForm";

const resistanceOnlyInstrument = {
  id: 1,
  name: "Resistance only",
  enabled: true,
  alert_mode: "static" as const,
  supports: [],
  resistances: ["120"],
  high_water: null,
  fixed_drawdown: null,
  near_support_threshold: null,
  risk_reward_threshold: null,
  source_mappings: [
    {
      id: 1,
      provider: "yfinance",
      market_type: "equity",
      symbol: "AAPL",
      enabled: true,
    },
  ],
};

describe("InstrumentForm", () => {
  it("submits resistance-only instruments without rule thresholds", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <InstrumentForm
        initialData={resistanceOnlyInstrument}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText("接近支撑阈值 (0-1)"), {
      target: { value: "" },
    });
    fireEvent.change(screen.getByLabelText("风险回报阈值 (>0)"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存标的" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("submits an edit after support is cleared even when stale thresholds remain", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <InstrumentForm
        initialData={{
          ...resistanceOnlyInstrument,
          supports: ["100"],
          near_support_threshold: "0.02",
          risk_reward_threshold: "3",
        }}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText("支撑位"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "保存标的" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce());
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        supports: [],
        resistances: ["120"],
        near_support_threshold: "0.02",
        risk_reward_threshold: "3",
      }),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("requires the near-support threshold when support exists", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <InstrumentForm
        initialData={{
          ...resistanceOnlyInstrument,
          supports: ["100"],
          resistances: [],
          near_support_threshold: null,
        }}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText("接近支撑阈值 (0-1)"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存标的" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("接近支撑阈值不能为空");
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
