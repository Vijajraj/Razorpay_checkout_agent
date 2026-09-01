import React from 'react';
import { ShieldCheck, ShieldAlert, FileText, CheckCircle2, XCircle, Download, Trash2 } from 'lucide-react';

export default function AuditLogPanel({ auditLogs, onClearLogs, spendCap = 10000 }) {
  const totalOrdersAmount = auditLogs
    .filter((log) => log.action === 'create_order' && log.result === 'SUCCESS')
    .reduce((sum, log) => sum + (log.amount || 0), 0);

  const totalBlockedAttacks = auditLogs.filter((log) => log.result === 'BLOCKED').length;

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
    <div className="audit-section">
      <div className="audit-header">
        <div className="audit-title">
          <ShieldCheck size={18} color="#3b82f6" />
          <span>Live Guardrail & Audit Log</span>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={handleExportJSON}
            className="preset-btn"
            title="Export JSON Audit Log"
            style={{ fontSize: '11px', padding: '4px 8px' }}
          >
            <Download size={12} /> Export
          </button>
          <button
            onClick={onClearLogs}
            className="preset-btn"
            title="Clear Logs"
            style={{ fontSize: '11px', padding: '4px 8px' }}
          >
            <Trash2 size={12} /> Clear
          </button>
        </div>
      </div>

      <div className="metrics-row">
        <div className="metric-card">
          <span className="metric-label">Spent / Cap Limit</span>
          <span className="metric-val green">
            ₹{totalOrdersAmount.toLocaleString()} / ₹{spendCap.toLocaleString()}
          </span>
        </div>

        <div className="metric-card">
          <span className="metric-label">Attacks Blocked</span>
          <span className={`metric-val ${totalBlockedAttacks > 0 ? 'red' : 'green'}`}>
            {totalBlockedAttacks} Threats
          </span>
        </div>

        <div className="metric-card">
          <span className="metric-label">Guardrail Engine</span>
          <span className="metric-val green" style={{ fontSize: '13px', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <CheckCircle2 size={14} color="#10b981" /> 100% Enforced
          </span>
        </div>
      </div>

      <div className="audit-feed">
        {auditLogs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px 20px', color: '#9ca3af', fontSize: '13px' }}>
            <FileText size={32} color="#374151" style={{ marginBottom: '10px' }} />
            <p>No audit events logged yet.</p>
            <p style={{ fontSize: '11px', marginTop: '4px' }}>Interact with the agent or trigger a Red-Team preset to view live enforcement logs.</p>
          </div>
        ) : (
          auditLogs.map((log) => (
            <div
              key={log.id}
              className={`audit-item ${log.result === 'BLOCKED' ? 'blocked' : 'passed'}`}
            >
              <div className="audit-item-top">
                <span className={`audit-action ${log.action === 'create_order' ? 'create_order' : log.result === 'BLOCKED' ? 'guardrail_block' : 'catalog_lookup'}`}>
                  {log.action}
                </span>

                <span className={`audit-badge ${log.result === 'BLOCKED' ? 'blocked' : 'passed'}`}>
                  {log.result === 'BLOCKED' ? 'BLOCKED' : 'PASSED'}
                </span>
              </div>

              {log.sku && log.sku !== 'N/A' && (
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', fontWeight: 600 }}>
                  <span>SKU: {log.sku}</span>
                  {log.amount > 0 && <span>₹{log.amount.toLocaleString()}</span>}
                </div>
              )}

              <div className="audit-reason">
                <strong>Reasoning:</strong> {log.reasoning}
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '10px', color: log.result === 'BLOCKED' ? '#ef4444' : '#10b981', fontWeight: 600 }}>
                  Cap Check: {log.spend_cap_check}
                </span>
                <span className="audit-time">
                  {new Date(log.timestamp).toLocaleTimeString()}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
