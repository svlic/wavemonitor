import { useEffect } from "react";

const DEFAULT_INTERVAL_MS = 120_000;

export function usePollingRefresh(
  onTick: () => void,
  intervalMs: number = DEFAULT_INTERVAL_MS,
): void {
  useEffect(() => {
    const id = window.setInterval(onTick, intervalMs);
    return () => window.clearInterval(id);
  }, [onTick, intervalMs]);
}