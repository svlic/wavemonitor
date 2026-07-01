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
      setError("标的列表加载失败，请重试。");
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(id: number) {
    if (!window.confirm("确定要删除这个标的吗？")) return;

    try {
      await apiClient.deleteInstrument(id);
      setInstruments(instruments.filter((i) => i.id !== id));
    } catch (err) {
      alert("删除标的失败。");
    }
  }

  if (loading) {
    return (
      <div className="panel loading-panel" role="status" aria-live="polite">
        <h2>标的管理</h2>
        <p className="muted-text">正在加载标的...</p>
        <div className="skeleton skeleton-line skeleton-line--short" aria-hidden="true" />
        <div className="skeleton skeleton-block" aria-hidden="true" />
      </div>
    );
  }
  if (error) return <div className="panel error-text">{error}</div>;

  return (
    <div className="panel">
      <div className="header-row">
        <h2>标的管理</h2>
        <Link href="/instruments/new" className="button primary">新增标的</Link>
      </div>
      
      {instruments.length === 0 ? (
        <p className="summary">尚未配置标的。</p>
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>名称</th>
                <th>状态</th>
                <th>支撑位</th>
                <th>阻力位</th>
                <th>接近支撑阈值</th>
                <th>风险回报阈值</th>
                <th>来源数</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {instruments.map(inst => (
                <tr key={inst.id}>
                  <td>{inst.name}</td>
                  <td>{inst.enabled ? "启用" : "停用"}</td>
                  <td>{inst.support}</td>
                  <td>{inst.resistance}</td>
                  <td>{inst.near_support_threshold}</td>
                  <td>{inst.risk_reward_threshold}</td>
                  <td>{inst.source_mappings.length}</td>
                  <td className="actions">
                    <Link href={`/instruments/${inst.id}/edit`} className="button small">编辑</Link>
                    <button onClick={() => handleDelete(inst.id)} className="button small danger">删除</button>
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
