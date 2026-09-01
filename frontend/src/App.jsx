import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import ChatPanel from './components/ChatPanel';
import AuditLogPanel from './components/AuditLogPanel';
import { sendChatMessage, checkBackendHealth } from './services/api';

export default function App() {
  const [backendConnected, setBackendConnected] = useState(false);
  const [auditOpen, setAuditOpen] = useState(false);
  const [sessionId] = useState(() => `sess_${Math.random().toString(36).substring(2, 9)}`);

  const [messages, setMessages] = useState([
    {
      id: 1,
      sender: 'assistant',
      text: `Hello! I am your AI Checkout Assistant powered by Groq (openai/gpt-oss-120b).\n\nI can help you search products, answer questions, and complete purchases on Razorpay test-mode under code-enforced guardrails.\n\nWhat are you shopping for today?`,
      products: [],
    },
  ]);

  const [auditLogs, setAuditLogs] = useState([
    {
      id: 100,
      timestamp: new Date().toISOString(),
      action: 'system_init',
      sku: 'N/A',
      amount: 0,
      reasoning: 'Guardrail Engine initialized. Merchant hard spend cap limit active at ₹10,000.',
      spend_cap_check: 'PASSED',
      result: 'SUCCESS',
    },
  ]);

  useEffect(() => {
    async function verifyHealth() {
      const health = await checkBackendHealth();
      setBackendConnected(health.online);
    }
    verifyHealth();
  }, []);

  const handleSendMessage = async (userText) => {
    const userMsg = {
      id: Date.now(),
      sender: 'user',
      text: userText,
    };

    setMessages((prev) => [...prev, userMsg]);

    const res = await sendChatMessage(userText, { sessionId });

    if (res.success) {
      const botMsg = {
        id: Date.now() + 1,
        sender: 'assistant',
        text: res.data.reply,
        products: res.data.products || [],
        blocked: res.data.blocked || false,
      };

      setMessages((prev) => [...prev, botMsg]);

      if (res.data.auditEntry) {
        setAuditLogs((prev) => [res.data.auditEntry, ...prev]);
        // Auto-open drawer if an attack/block occurs so user notices
        if (res.data.blocked) {
          setAuditOpen(true);
        }
      }
    }
  };

  const handleAuditLogged = (newEntry) => {
    setAuditLogs((prev) => [newEntry, ...prev]);
  };

  const handleClearLogs = () => {
    setAuditLogs([]);
  };

  const blockedCount = auditLogs.filter((l) => l.result === 'BLOCKED').length;

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Header
        backendConnected={backendConnected}
        spendCap={10000}
        auditOpen={auditOpen}
        onToggleAudit={() => setAuditOpen(!auditOpen)}
        blockedCount={blockedCount}
      />

      <div className="app-layout">
        <ChatPanel
          messages={messages}
          onSendMessage={handleSendMessage}
          onAuditLogged={handleAuditLogged}
        />

        <AuditLogPanel
          open={auditOpen}
          onClose={() => setAuditOpen(false)}
          auditLogs={auditLogs}
          onClearLogs={handleClearLogs}
          spendCap={10000}
        />
      </div>
    </div>
  );
}
