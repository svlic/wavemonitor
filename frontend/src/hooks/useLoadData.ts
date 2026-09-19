import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api/client";

type LoadState = "loading" | "ready" | "error";

export function useLoadData<T>(loader: (signal?: AbortSignal) => Promise<T>) {
  const [state, setState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [data, setData] = useState<T | null>(null);

  const loadData = useCallback(
    async (signal?: AbortSignal, refresh = false) => {
      if (refresh) {
        setRefreshing(true);
      } else {
        setState("loading");
      }
      try {
        const loaded = await loader(signal);
        if (signal?.aborted) return;
        setData(loaded);
        setState("ready");
        setErrorMessage(null);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setState("error");
        setErrorMessage(error instanceof ApiError ? error.message : "发生未知错误。");
      } finally {
        if (!signal?.aborted) setRefreshing(false);
      }
    },
    [loader],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadData(controller.signal);
    return () => controller.abort();
  }, [loadData]);

  const refresh = useCallback(() => {
    void loadData(undefined, true);
  }, [loadData]);

  return { state, errorMessage, refreshing, data, refresh };
}
