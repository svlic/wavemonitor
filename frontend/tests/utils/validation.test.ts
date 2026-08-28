import { describe, expect, it } from "vitest";
import { validateThreshold, validateSupportResistance } from "../../src/utils/validation";

describe("validation", () => {
  describe("validateThreshold", () => {
    it("returns error for empty value", () => {
      expect(validateThreshold("")).toBe("阈值不能为空");
    });

    it("returns error for non-number", () => {
      expect(validateThreshold("abc")).toBe("阈值必须是数字");
    });

    it("returns error for out of bounds values", () => {
      expect(validateThreshold("0")).toBe("阈值必须介于 0 和 1 之间（不含边界）");
      expect(validateThreshold("-0.1")).toBe("阈值必须介于 0 和 1 之间（不含边界）");
      expect(validateThreshold("1")).toBe("阈值必须介于 0 和 1 之间（不含边界）");
      expect(validateThreshold("1.5")).toBe("阈值必须介于 0 和 1 之间（不含边界）");
    });

    it("returns null for valid values", () => {
      expect(validateThreshold("0.02")).toBeNull();
      expect(validateThreshold("0.5")).toBeNull();
      expect(validateThreshold("0.99")).toBeNull();
    });
  });

  describe("validateSupportResistance", () => {
    it("returns error when both levels are empty", () => {
      expect(validateSupportResistance([], [])).toBe("支撑位和阻力位至少填写一项");
    });

    it("returns null when only one level is set", () => {
      expect(validateSupportResistance([], ["100"])).toBeNull();
      expect(validateSupportResistance(["50"], [])).toBeNull();
    });

    it("returns error for non-numbers on filled fields", () => {
      expect(validateSupportResistance(["abc"], ["100"])).toBe("支撑位必须是数字");
      expect(validateSupportResistance(["100"], ["def"])).toBe("阻力位必须是数字");
    });

    it("returns error for non-positive values on filled fields", () => {
      expect(validateSupportResistance(["0"], ["100"])).toBe("支撑位必须为正数");
      expect(validateSupportResistance(["-10"], ["100"])).toBe("支撑位必须为正数");
      expect(validateSupportResistance(["100"], ["0"])).toBe("阻力位必须为正数");
    });

    it("returns error when support >= resistance", () => {
      expect(validateSupportResistance(["100"], ["100"])).toBe("支撑位必须严格小于阻力位");
      expect(validateSupportResistance(["90", "110"], ["105", "130"])).toBe("所有支撑位必须严格小于所有阻力位");
    });

    it("returns null for valid values", () => {
      expect(validateSupportResistance(["90"], ["110"])).toBeNull();
      expect(validateSupportResistance(["80", "100.5"], ["100.6", "120"])).toBeNull();
    });
  });
});
