import { renderHook, act } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { usePollingRefresh } from "./usePollingRefresh";

describe("usePollingRefresh", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("invokes callback on interval", () => {
    vi.useFakeTimers();
    const onTick = vi.fn();

    renderHook(() => usePollingRefresh(onTick, 120_000));

    expect(onTick).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(120_000);
    });

    expect(onTick).toHaveBeenCalledTimes(1);
  });
});