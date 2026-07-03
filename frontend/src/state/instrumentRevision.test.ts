import { describe, expect, it, vi } from "vitest";
import {
  bumpInstrumentRevision,
  getInstrumentRevision,
  subscribeInstrumentRevision,
} from "./instrumentRevision";

describe("instrumentRevision", () => {
  it("notifies subscribers when revision bumps", () => {
    const listener = vi.fn();
    const start = getInstrumentRevision();
    const unsubscribe = subscribeInstrumentRevision(listener);

    bumpInstrumentRevision();

    expect(getInstrumentRevision()).toBe(start + 1);
    expect(listener).toHaveBeenCalledTimes(1);

    unsubscribe();
    bumpInstrumentRevision();
    expect(listener).toHaveBeenCalledTimes(1);
  });
});