import { describe, expect, it } from "vitest";
import { DISPLAY_TIME_ZONE, formatDateTime } from "../src/utils/format";

describe("formatDateTime", () => {
  it("formats UTC instants in Asia/Shanghai (UTC+8)", () => {
    expect(DISPLAY_TIME_ZONE).toBe("Asia/Shanghai");
    expect(formatDateTime("2026-06-30T12:00:00Z")).toMatch(/2026/);
    expect(formatDateTime("2026-06-30T12:00:00Z")).toMatch(/20:00:00/);
  });

  it("returns original string when iso is invalid", () => {
    expect(formatDateTime("not-a-date")).toBe("not-a-date");
  });
});