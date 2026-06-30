import { describe, expect, it } from "vitest";
import { validateThreshold, validateSupportResistance } from "../../src/utils/validation";

describe("validation", () => {
  describe("validateThreshold", () => {
    it("returns error for empty value", () => {
      expect(validateThreshold("")).toBe("Threshold is required");
    });

    it("returns error for non-number", () => {
      expect(validateThreshold("abc")).toBe("Threshold must be a number");
    });

    it("returns error for out of bounds values", () => {
      expect(validateThreshold("0")).toBe("Threshold must be between 0 and 1 (exclusive)");
      expect(validateThreshold("-0.1")).toBe("Threshold must be between 0 and 1 (exclusive)");
      expect(validateThreshold("1")).toBe("Threshold must be between 0 and 1 (exclusive)");
      expect(validateThreshold("1.5")).toBe("Threshold must be between 0 and 1 (exclusive)");
    });

    it("returns null for valid values", () => {
      expect(validateThreshold("0.02")).toBeNull();
      expect(validateThreshold("0.5")).toBeNull();
      expect(validateThreshold("0.99")).toBeNull();
    });
  });

  describe("validateSupportResistance", () => {
    it("returns error for empty values", () => {
      expect(validateSupportResistance("", "100")).toBe("Both support and resistance are required");
      expect(validateSupportResistance("100", "")).toBe("Both support and resistance are required");
    });

    it("returns error for non-numbers", () => {
      expect(validateSupportResistance("abc", "100")).toBe("Support and resistance must be numbers");
      expect(validateSupportResistance("100", "def")).toBe("Support and resistance must be numbers");
    });

    it("returns error for non-positive values", () => {
      expect(validateSupportResistance("0", "100")).toBe("Support and resistance must be positive");
      expect(validateSupportResistance("-10", "100")).toBe("Support and resistance must be positive");
      expect(validateSupportResistance("100", "0")).toBe("Support and resistance must be positive");
    });

    it("returns error when support >= resistance", () => {
      expect(validateSupportResistance("100", "100")).toBe("Support must be strictly less than resistance");
      expect(validateSupportResistance("110", "100")).toBe("Support must be strictly less than resistance");
    });

    it("returns null for valid values", () => {
      expect(validateSupportResistance("90", "110")).toBeNull();
      expect(validateSupportResistance("100.5", "100.6")).toBeNull();
    });
  });
});
