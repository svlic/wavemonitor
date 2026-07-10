import { useEffect, useState } from "react";
import { Link } from "wouter";
import { apiClient } from "../../api/client";
import { bumpInstrumentRevision } from "../../state/instrumentRevision";
import type { InstrumentWithMappings } from "../../api/client";
import { formatDecimal, formatOptionalLevel } from "../../utils/format";

export function InstrumentList() {
  const [instruments, setInstruments] = useState<readonly InstrumentWithMappings[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [togglingId, setTogglingId] = useState<number | null>(null);
  const [toggleError, setToggleError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void loadInstruments(controller.signal);
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

  async function toggleMonitoring(id: number, enabled: boolean) {
    setTogglingId(id);
    setToggleError(null);
    try {
      const updated = await apiClient.patchInstrumentEnabled(id, enabled);
      setInstruments((current) => current.map((i) => (i.id === id ? updated : i)));
      bumpInstrumentRevision();
    } catch {
      setToggleError(enabled ? "恢复监控失败，请稍后重试。" : "暂停监控失败，请稍后重试。");
    } finally {
      setTogglingId(null);
    }
  }

  async function confirmDelete(id: number) {
    setDeletingId(id);
    setDeleteError(null);
    try {
      await apiClient.deleteInstrument(id);
      setInstruments((current) => current.filter((i) => i.id !== id));
      setPendingDeleteId(null);
      bumpInstrumentRevision();
    } catch {
      setDeleteError("删除标的失败，请稍后重试。");
    } finally {
      setDeletingId(null);
    }
  }

  if (loading) {
    return (
      <div className="panel loading-panel" role="status" aria-live="polite">
        <p className="muted-text">正在加载标的...</p>
        <div className="skeleton skeleton-line skeleton-line--short" aria-hidden="true" />
        <div className="skeleton skeleton-block" aria-hidden="true" />
      </div>
    );
  }

  if (error) {
    return (
      <section className="panel">
        <div className="error-banner" role="alert">
          <p className="error-text">{error}</p>
        </div>
        <button type="button" className="button primary" onClick={() => void loadInstruments()}>
          重新加载
        </button>
      </section>
    );
  }

  return (
    <div className="panel">
      <div className="header-row">
        <div>
          <h2 className="section-title">已配置标的</h2>
          <p className="summary">
            {instruments.length === 0
              ? "创建第一个标的以开始轮询与告警。"
              : `共 ${instruments.length} 个标的，${instruments.filter((i) => i.enabled).length} 个监控中，${instruments.filter((i) => !i.enabled).length} 个已暂停。`}
          </p>
        </div>
        <Link href="/instruments/new" className="button primary">
          新增标的
        </Link>
      </div>

      {(deleteError ?? toggleError) && (
        <div className="error-banner" role="alert">
          <p className="error-text">{deleteError ?? toggleError}</p>
        </div>
      )}

      {instruments.length === 0 ? (
        <div className="empty-state empty-state--action">
          <p>尚未配置标的。</p>
          <Link href="/instruments/new" className="button primary">
            创建第一个标的
          </Link>
        </div>
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
              {instruments.map((inst) => (
                <tr key={inst.id}>
                  <td>{inst.name}</td>
                  <td>
                    <span className={`status-pill ${inst.enabled ? "status-pill--ready" : "status-pill--idle"}`}>
                      {inst.enabled ? "监控中" : "已暂停"}
                    </span>
                  </td>
                  <td className="price-cell">{formatOptionalLevel(inst.support)}</td>
                  <td className="price-cell">{formatOptionalLevel(inst.resistance)}</td>
                  <td>{formatDecimal(inst.near_support_threshold)}</td>
                  <td>{formatDecimal(inst.risk_reward_threshold)}</td>
                  <td>{inst.source_mappings.length}</td>
                  <td className="actions">
                    {inst.enabled ? (
                      <button
                        type="button"
                        className="button small"
                        disabled={togglingId === inst.id || pendingDeleteId === inst.id}
                        onClick={() => void toggleMonitoring(inst.id, false)}
                      >
                        {togglingId === inst.id ? "处理中..." : "暂停"}
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="button small primary"
                        disabled={togglingId === inst.id || pendingDeleteId === inst.id}
                        onClick={() => void toggleMonitoring(inst.id, true)}
                      >
                        {togglingId === inst.id ? "处理中..." : "恢复"}
                      </button>
                    )}
                    <Link href={`/instruments/${inst.id}/edit`} className="button small">
                      编辑
                    </Link>
                    {pendingDeleteId === inst.id ? (
                      <div className="inline-confirm">
                        <span className="inline-confirm__label">确认删除？</span>
                        <button
                          type="button"
                          className="button small danger"
                          disabled={deletingId === inst.id}
                          onClick={() => void confirmDelete(inst.id)}
                        >
                          {deletingId === inst.id ? "删除中..." : "确认"}
                        </button>
                        <button
                          type="button"
                          className="button small"
                          disabled={deletingId === inst.id}
                          onClick={() => {
                            setPendingDeleteId(null);
                            setDeleteError(null);
                          }}
                        >
                          取消
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          setPendingDeleteId(inst.id);
                          setDeleteError(null);
                        }}
                        className="button small danger"
                      >
                        删除
                      </button>
                    )}
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