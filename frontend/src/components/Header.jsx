import React from 'react';
import { ShieldCheck, Cpu, CreditCard, Lock } from 'lucide-react';

export default function Header({ backendConnected, spendCap = 10000 }) {
  return (
    <header className="app-header">
      <div className="brand-title">
        <div className="brand-icon">
          <CreditCard size={20} />
        </div>
        <div>
          <h1>Razorpay Checkout Agent</h1>
          <span className="brand-badge">Verified Guardrails Engine</span>
        </div>
      </div>

      <div className="header-meta">
        <div className="meta-pill">
          <Cpu size={14} color="#60a5fa" />
          <span>Model: <strong>Groq / openai/gpt-oss-120b</strong></span>
        </div>

        <div className="meta-pill">
          <Lock size={14} color="#f59e0b" />
          <span>Hard Spend Cap: <strong>₹{spendCap.toLocaleString()}</strong></span>
        </div>

        <div className="meta-pill">
          <ShieldCheck size={14} color={backendConnected ? '#10b981' : '#f59e0b'} />
          <div className={`status-dot ${backendConnected ? 'online' : 'sim'}`} />
          <span>{backendConnected ? 'FastAPI Connected' : 'Guardrail Simulator'}</span>
        </div>
      </div>
    </header>
  );
}
