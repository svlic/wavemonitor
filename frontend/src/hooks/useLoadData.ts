import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";

type LoadState = "loading" | "ready" | "error";

export function useLoadData<T>(
  loader: (signal?: AbortSignal) => Promise<T>,
  refreshLoader = loader,
) {
  const [state, setState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [data, setData] = useState<T | null>(null);
  const activeRequest = useRef<AbortController | null>(null);

  const loadData = useCallback(
    async (signal?: AbortSignal, refresh = false, load = loader) => {
      activeRequest.current?.abort();
      const controller = new AbortController();
      activeRequest.current = controller;
      const requestSignal = AbortSignal.any([
        controller.signal,
        AbortSignal.timeout(55_000),
        ...(signal ? [signal] : []),
      ]);
      if (refresh) {
        setRefreshing(true);
      } else {
        setState("loading");
      }
      try {
        const loaded = await load(requestSignal);
        if (requestSignal.aborted) return;
        setData(loaded);
        setState("ready");
        setErrorMessage(null);
      } catch (error) {
        if (controller.signal.aborted || signal?.aborted) return;
        if (error instanceof DOMException && error.name === "AbortError") return;
        setState("error");
        setErrorMessage(
          requestSignal.aborted ? "请求超时，请重试。" :
            error instanceof ApiError ? error.message : "发生未知错误。",
        );
      } finally {
        if (!controller.signal.aborted && !signal?.aborted) setRefreshing(false);
      }
    },
    [loader],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadData(controller.signal);
    return () => {
      controller.abort();
      activeRequest.current?.abort();
    };
  }, [loadData]);

  const refresh = useCallback(() => {
    void loadData(undefined, true, refreshLoader);
  }, [loadData, refreshLoader]);

  const reload = useCallback(() => {
    void loadData(undefined, true);
  }, [loadData]);

  return { state, errorMessage, refreshing, data, refresh, reload };
}
