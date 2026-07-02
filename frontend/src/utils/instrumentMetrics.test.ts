import { describe, expect, it } from "vitest";
import {
  computeResistanceDistancePercent,
  computeRiskRewardRatio,
  computeSupportDistancePercent,
} from "./instrumentMetrics";

describe("instrumentMetrics", () => {
  describe("computeSupportDistancePercent", () => {
    it("returns percent above support when price is above support", () => {
      expect(computeSupportDistancePercent("100", "90")).toBeCloseTo(10, 5);
    });

    it("returns null when price is at or below support", () => {
      expect(computeSupportDistancePercent("90", "90")).toBeNull();
      expect(computeSupportDistancePercent("80", "90")).toBeNull();
    });
  });

  describe("computeResistanceDistancePercent", () => {
    it("returns percent below resistance when price is below resistance", () => {
      expect(computeResistanceDistancePercent("100", "110")).toBeCloseTo(10, 5);
    });

    it("returns null when price is at or above resistance", () => {
      expect(computeResistanceDistancePercent("110", "110")).toBeNull();
      expect(computeResistanceDistancePercent("120", "110")).toBeNull();
    });
  });

  describe("computeRiskRewardRatio", () => {
    it("matches backend risk_reward_ratio between support and resistance", () => {
      expect(computeRiskRewardRatio("95", "90", "100")).toBeCloseTo(1, 5);
    });

    it("returns null when price is outside the support-resistance band", () => {
      expect(computeRiskRewardRatio("90", "90", "100")).toBeNull();
      expect(computeRiskRewardRatio("100", "90", "100")).toBeNull();
      expect(computeRiskRewardRatio("105", "90", "100")).toBeNull();
    });
  });
});