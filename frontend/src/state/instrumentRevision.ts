type Listener = () => void;

let revision = 0;
const listeners = new Set<Listener>();

export function getInstrumentRevision(): number {
  return revision;
}

export function bumpInstrumentRevision(): void {
  revision += 1;
  for (const listener of listeners) {
    listener();
  }
}

export function subscribeInstrumentRevision(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}