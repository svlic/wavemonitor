import { useEffect, useState } from "react";
import { Link } from "wouter";
import { apiClient } from "../../api/client";
import type { InstrumentWithMappings } from "../../api/client";

export function InstrumentList() {
  const [instruments, setInstruments] = useState<readonly InstrumentWithMappings[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    loadInstruments(controller.signal);
    return () => controller.abort();
  }, []);

  async function loadInstruments(signal?: AbortSignal) {
    try {
      setLoading(true);
      setError(null);
      const data = await apiClient.getInstruments(signal);
      setInstruments(data);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setError("Failed to load instruments. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(id: number) {
    if (!window.confirm("Are you sure you want to delete this instrument?")) return;

    try {
      await apiClient.deleteInstrument(id);
      setInstruments(instruments.filter((i) => i.id !== id));
    } catch (err) {
      alert("Failed to delete instrument.");
    }
  }

  if (loading) {
    return (
      <div className="panel loading-panel" role="status" aria-live="polite">
        <h2>Instruments</h2>
        <p className="muted-text">Loading instruments...</p>
        <div className="skeleton skeleton-line skeleton-line--short" aria-hidden="true" />
        <div className="skeleton skeleton-block" aria-hidden="true" />
      </div>
    );
  }
  if (error) return <div className="panel error-text">{error}</div>;

  return (
    <div className="panel">
      <div className="header-row">
        <h2>Instruments</h2>
        <Link href="/instruments/new" className="button primary">Add Instrument</Link>
      </div>
      
      {instruments.length === 0 ? (
        <p className="summary">No instruments configured.</p>
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Support</th>
                <th>Resistance</th>
                <th>Near Support Thresh</th>
                <th>Risk Reward Thresh</th>
                <th>Sources</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {instruments.map(inst => (
                <tr key={inst.id}>
                  <td>{inst.name}</td>
                  <td>{inst.enabled ? "Active" : "Disabled"}</td>
                  <td>{inst.support}</td>
                  <td>{inst.resistance}</td>
                  <td>{inst.near_support_threshold}</td>
                  <td>{inst.risk_reward_threshold}</td>
                  <td>{inst.source_mappings.length}</td>
                  <td className="actions">
                    <Link href={`/instruments/${inst.id}/edit`} className="button small">Edit</Link>
                    <button onClick={() => handleDelete(inst.id)} className="button small danger">Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
