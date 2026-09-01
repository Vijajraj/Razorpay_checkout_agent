import React from 'react';
import { ShieldCheck, X, Download, Trash2, ShieldAlert } from 'lucide-react';

export default function AuditLogPanel({ open, onClose, auditLogs, onClearLogs, spendCap = 10000 }) {
  const totalSpent = auditLogs
    .filter((log) => log.action === 'create_order' && log.result === 'SUCCESS')
    .reduce((sum, log) => sum + (log.amount || 0), 0);

  const blockedCount = auditLogs.filter((log) => log.result === 'BLOCKED').length;

  const handleExportJSON = () => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(auditLogs, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute('download', `audit_log_${Date.now()}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  return (
    <aside className={`audit-drawer ${open ? 'open' : ''}`}>
      <div className="drawer-header">
        <div className="drawer-title">
          <ShieldCheck size={16} color="#6366f1" />
          <span>Guardrail & Audit Log</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <button onClick={handleExportJSON} className="icon-btn" title="Export JSON" style={{ padding: '4px 8px', fontSize: '11px' }}>
            <Download size={13} />
          </button>
          <button onClick={onClearLogs} className="icon-btn" title="Clear Logs" style={{ padding: '4px 8px', fontSize: '11px' }}>
            <Trash2 size={13} />
          </button>
          <button onClick={onClose} className="icon-btn" style={{ padding: '4px' }}>
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="drawer-metrics">
        <div className="stat-box">
          <span className="label">Spent / Spend Cap</span>
          <span className="val">₹{totalSpent.toLocaleString()} / ₹{spendCap.toLocaleString()}</span>
        </div>

        <div className="stat-box">
          <span className="label">Blocked Threats</span>
          <span className="val" style={{ color: blockedCount > 0 ? '#ef4444' : '#10b981' }}>
            {blockedCount} Atttempts
          </span>
        </div>
      </div>

      <div className="drawer-feed">
        {auditLogs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px 10px', color: 'var(--text-dim)', fontSize: '12px' }}>
            No audit logs captured yet. Try testing a quick-action prompt.
          </div>
        ) : (
          auditLogs.map((log) => (
            <div
              key={log.id}
              className={`timeline-item ${log.result === 'BLOCKED' ? 'blocked' : 'passed'}`}
            >
              <div className="timeline-top">
                <span className="timeline-action">{log.action}</span>
                <span className={`timeline-badge ${log.result === 'BLOCKED' ? 'blocked' : 'passed'}`}>
                  {log.result === 'BLOCKED' ? 'BLOCKED' : 'PASSED'}
                </span>
              </div>

              <div className="timeline-reason">
                {log.reasoning}
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-dim)', marginTop: '2px' }}>
                <span>Cap Check: {log.spend_cap_check}</span>
                <span>{new Date(log.timestamp).toLocaleTimeString()}</span>
              </div>
            </div>
          ))
        )}
      </div>
    </aside>
  );
}
