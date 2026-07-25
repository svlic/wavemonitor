import { afterEach, describe, expect, it, vi } from "vitest";
import { DISPLAY_TIME_ZONE, formatDateTime } from "../src/utils/format";

describe("formatDateTime", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("formats UTC instants in Asia/Shanghai (UTC+8)", () => {
    expect(DISPLAY_TIME_ZONE).toBe("Asia/Shanghai");
    expect(formatDateTime("2026-06-30T12:00:00Z")).toBe("2026/06/30 20:00:00 UTC+8");
  });

  it("treats timezone-less API timestamps as UTC when the browser is in UTC+8", () => {
    vi.stubEnv("TZ", "Asia/Shanghai");

    expect(formatDateTime("2026-06-30T12:00:00")).toBe("2026/06/30 20:00:00 UTC+8");
  });

  it("preserves explicit offsets before converting to UTC+8", () => {
    expect(formatDateTime("2026-06-30T12:00:00+02:00")).toBe("2026/06/30 18:00:00 UTC+8");
  });

  it("returns original string when iso is invalid", () => {
    expect(formatDateTime("not-a-date")).toBe("not-a-date");
  });
});