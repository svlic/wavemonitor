import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import { InstrumentForm } from "./InstrumentForm";
import { apiClient } from "../../api/client";
import { bumpInstrumentRevision } from "../../state/instrumentRevision";
import type { InstrumentWithMappings, CreateInstrumentRequest } from "../../api/client";

type Props = {
  id: string;
};

export function InstrumentEdit({ id }: Props) {
  const [, setLocation] = useLocation();
  const [instrument, setInstrument] = useState<InstrumentWithMappings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      try {
        const data = await apiClient.getInstrument(id, controller.signal);
        setInstrument(data);
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError("标的加载失败。");
      } finally {
        setLoading(false);
      }
    }

    void load();
    return () => controller.abort();
  }, [id]);

  const handleSubmit = async (data: CreateInstrumentRequest) => {
    await apiClient.updateInstrument(id, data);
    bumpInstrumentRevision();
    setLocation("/instruments");
  };

  if (loading) {
    return (
      <div className="panel loading-panel" role="status" aria-live="polite">
        <p className="muted-text">正在加载标的...</p>
        <div className="skeleton skeleton-line skeleton-line--medium" aria-hidden="true" />
        <div className="skeleton skeleton-block" aria-hidden="true" />
      </div>
    );
  }

  if (error || !instrument) {
    return (
      <section className="panel">
        <div className="error-banner" role="alert">
          <p className="error-text">{error ?? "未找到标的"}</p>
        </div>
        <button type="button" className="button" onClick={() => setLocation("/instruments")}>
          返回列表
        </button>
      </section>
    );
  }

  return (
    <InstrumentForm
      initialData={instrument}
      onSubmit={handleSubmit}
      onCancel={() => setLocation("/instruments")}
    />
  );
}