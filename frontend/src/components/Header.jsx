import React, { useState } from 'react';
import { ShoppingBag, Moon, Sun, ShieldCheck, Settings, CheckCircle2, PanelLeft, Library } from 'lucide-react';

export default function Header({
  theme,
  onToggleTheme,
  backendConnected,
  spendCap = 10000,
  auditOpen,
  onToggleAudit,
  catalogOpen,
  onToggleCatalog,
  blockedCount = 0,
  onClearChatHistory,
  sidebarCollapsed = false,
  onToggleSidebar,
}) {
  const [showSettings, setShowSettings] = useState(false);

  return (
    <header className="app-header">
      <div className="brand-title">
        {onToggleSidebar && (
          <button
            className={`icon-btn sidebar-toggle-header ${!sidebarCollapsed ? 'active' : ''}`}
            onClick={onToggleSidebar}
            title="Toggle Saved Chats Sidebar"
            style={{ marginRight: '6px' }}
          >
            <PanelLeft size={16} />
          </button>
        )}
        <div className="brand-icon">
          <img src="/agent-logo.png" alt="Agent Logo" className="brand-logo-img" />
        </div>
        <h1>Razorpay Agentic Store</h1>

        {/* Compact Agent Status Badge */}
        <div className="agent-status-pill">
          <span className="status-dot green"></span>
          <span>Agent Online</span>
        </div>
      </div>

      <div className="header-controls">
        <button
          className={`icon-btn ${catalogOpen ? 'active' : ''}`}
          onClick={onToggleCatalog}
          title="Open Catalog Browser"
        >
          <Library size={16} />
          <span>Browse Catalog</span>
        </button>

        <button
          className={`icon-btn ${auditOpen ? 'active' : ''}`}
          onClick={onToggleAudit}
          title="Open Audit Log Drawer"
        >
          <ShieldCheck size={16} />
          <span>Audit Trail</span>
          {blockedCount > 0 && (
            <span className="badge-count blocked">{blockedCount}</span>
          )}
        </button>

        <button
          className="icon-btn"
          onClick={onToggleTheme}
          title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`}
        >
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
        </button>

        <button
          className="icon-btn"
          onClick={() => setShowSettings(true)}
          title="Agent Configuration Settings"
        >
          <Settings size={16} />
        </button>
      </div>

      {/* Settings Modal */}
      {showSettings && (
        <div className="modal-overlay" onClick={() => setShowSettings(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 style={{ fontSize: '15px', fontWeight: 600 }}>Agent Configuration</h3>
              <button className="icon-btn" onClick={() => setShowSettings(false)}>✕</button>
            </div>

            <div className="settings-row">
              <span>LLM Engine:</span>
              <strong>Groq (`openai/gpt-oss-120b`)</strong>
            </div>

            <div className="settings-row">
              <span>Payment Gateway:</span>
              <strong>Razorpay Test-Mode SDK</strong>
            </div>

            <div className="settings-row">
              <span>Hard Spend Cap:</span>
              <strong>₹{spendCap.toLocaleString()}</strong>
            </div>

            <div className="settings-row">
              <span>Database Storage:</span>
              <strong>Neon Postgres DB</strong>
            </div>

            <div className="settings-row">
              <span>Backend Connection:</span>
              <span style={{ color: backendConnected ? 'var(--accent-success)' : 'var(--accent-blocked)', fontWeight: 600 }}>
                {backendConnected ? 'FastAPI Active' : 'Reconnecting'}
              </span>
            </div>

            {onClearChatHistory && (
              <div className="settings-row" style={{ marginTop: '14px', paddingTop: '12px', borderTop: '1px solid var(--border-subtle)' }}>
                <span>Chat History Privacy:</span>
                <button
                  type="button"
                  className="secondary-btn"
                  style={{ padding: '4px 10px', fontSize: '11.5px', color: 'var(--accent-blocked)' }}
                  onClick={() => {
                    onClearChatHistory();
                    setShowSettings(false);
                  }}
                >
                  Clear Stored History
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
