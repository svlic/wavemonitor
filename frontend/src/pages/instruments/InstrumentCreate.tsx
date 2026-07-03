import { useLocation } from "wouter";
import { InstrumentForm } from "./InstrumentForm";
import { apiClient } from "../../api/client";
import { bumpInstrumentRevision } from "../../state/instrumentRevision";
import type { CreateInstrumentRequest } from "../../api/client";

export function InstrumentCreate() {
  const [, setLocation] = useLocation();

  const handleSubmit = async (data: CreateInstrumentRequest) => {
    await apiClient.createInstrument(data);
    bumpInstrumentRevision();
    setLocation("/instruments");
  };

  return (
    <InstrumentForm
      onSubmit={handleSubmit}
      onCancel={() => setLocation("/instruments")}
    />
  );
}
