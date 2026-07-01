import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import { InstrumentForm } from "./InstrumentForm";
import { apiClient } from "../../api/client";
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
    
    load();
    return () => controller.abort();
  }, [id]);

  const handleSubmit = async (data: CreateInstrumentRequest) => {
    await apiClient.updateInstrument(id, data);
    setLocation("/instruments");
  };

  if (loading) return <div className="panel">正在加载标的...</div>;
  if (error || !instrument) return <div className="panel error-text">{error || "未找到标的"}</div>;

  return (
    <InstrumentForm
      initialData={instrument}
      onSubmit={handleSubmit}
      onCancel={() => setLocation("/instruments")}
    />
  );
}
