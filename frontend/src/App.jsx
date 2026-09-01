import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import ChatPanel from './components/ChatPanel';
import AuditLogPanel from './components/AuditLogPanel';
import { sendChatMessage, checkBackendHealth } from './services/api';

export default function App() {
  const [backendConnected, setBackendConnected] = useState(false);
  const [sessionId] = useState(() => `sess_${Math.random().toString(36).substring(2, 9)}`);
  
  const [messages, setMessages] = useState([
    {
      id: 1,
      sender: 'assistant',
      text: `Hello! 👋 I am your Conversational Checkout Agent powered by **Groq (openai/gpt-oss-120b)** and integrated with **Razorpay test-mode**.\n\nI can help you search our catalog (running shoes, smartwatches, headphones, backpacks) and complete purchases with verified spend-cap guardrails.\n\nHow can I help you today?`,
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
      reasoning: 'Guardrail Engine initialized. Hard spend cap limit set to ₹10,000.',
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
      }
    }
  };

  const handleAuditLogged = (newEntry) => {
    setAuditLogs((prev) => [newEntry, ...prev]);
  };

  const handleClearLogs = () => {
    setAuditLogs([]);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <Header backendConnected={backendConnected} spendCap={10000} />

      <main className="main-container">
        <ChatPanel
          messages={messages}
          onSendMessage={handleSendMessage}
          onAuditLogged={handleAuditLogged}
        />

        <AuditLogPanel
          auditLogs={auditLogs}
          onClearLogs={handleClearLogs}
          spendCap={10000}
        />
      </main>
    </div>
  );
}
