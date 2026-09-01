import React, { useState } from 'react';
import { Shield, Settings, Bot, X, Cpu, Lock, CheckCircle2, Sun, Moon } from 'lucide-react';

export default function Header({
  theme,
  onToggleTheme,
  backendConnected,
  spendCap = 10000,
  auditOpen,
  onToggleAudit,
  blockedCount = 0,
}) {
  const [showSettings, setShowSettings] = useState(false);

  return (
    <>
      <header className="app-header">
        <div className="brand-title">
          <div className="brand-icon">
            <Bot size={18} />
          </div>
          <h1>Razorpay Agent</h1>
        </div>

        <div className="header-controls">
          {/* Light / Dark Mode Toggle Button */}
          <button
            className="icon-btn"
            onClick={onToggleTheme}
            title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`}
          >
            {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
          </button>

          {/* Audit Log Drawer Toggle */}
          <button
            className={`icon-btn ${auditOpen ? 'active' : ''}`}
            onClick={onToggleAudit}
            title="Toggle Audit Log Drawer"
          >
            <Shield size={15} />
            <span>Audit Log</span>
            {blockedCount > 0 && (
              <span
                style={{
                  background: '#ef4444',
                  color: 'white',
                  borderRadius: '10px',
                  padding: '1px 6px',
                  fontSize: '10px',
                  fontWeight: 700,
                }}
              >
                {blockedCount}
              </span>
            )}
          </button>

          {/* Settings Icon */}
          <button
            className="icon-btn"
            onClick={() => setShowSettings(true)}
            title="Agent Configuration Settings"
          >
            <Settings size={15} />
          </button>
        </div>
      </header>

      {/* Settings Modal */}
      {showSettings && (
        <div className="modal-overlay" onClick={() => setShowSettings(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 style={{ fontSize: '15px', fontWeight: 600 }}>Agent Configuration</h3>
              <button
                className="icon-btn"
                style={{ border: 'none', padding: '4px' }}
                onClick={() => setShowSettings(false)}
              >
                <X size={16} />
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <div className="settings-row">
                <span style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Cpu size={14} /> LLM Provider
                </span>
                <strong style={{ fontFamily: 'monospace' }}>Groq / openai/gpt-oss-120b</strong>
              </div>

              <div className="settings-row">
                <span style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Lock size={14} /> Hard Spend Cap
                </span>
                <strong>₹{spendCap.toLocaleString()}</strong>
              </div>

              <div className="settings-row">
                <span style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <CheckCircle2 size={14} /> Guardrail Engine
                </span>
                <span style={{ color: 'var(--accent-success)', fontWeight: 600 }}>Active (Code Enforced)</span>
              </div>

              <div className="settings-row">
                <span style={{ color: 'var(--text-muted)' }}>Backend API Status</span>
                <span>{backendConnected ? 'FastAPI Connected' : 'Standalone Simulator'}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
