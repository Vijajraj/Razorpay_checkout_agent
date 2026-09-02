import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import ChatPanel from './components/ChatPanel';
import PurchaseSummaryPanel from './components/PurchaseSummaryPanel';
import AuditLogPanel from './components/AuditLogPanel';
import { sendChatMessage, checkBackendHealth } from './services/api';
import catalogData from './data/catalog.json';

export default function App() {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('theme_pref') || 'dark';
  });

  const [backendConnected, setBackendConnected] = useState(false);
  const [auditOpen, setAuditOpen] = useState(false);
  const [sessionId] = useState(() => `sess_${Math.random().toString(36).substring(2, 9)}`);

  // Selected product & checkout state for Right Column Purchase Summary Panel
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [selectedQty, setSelectedQty] = useState(1);
  const [activeStep, setActiveStep] = useState(1); // 1: SEARCH, 2: SELECT, 3: VERIFY, 4: ORDER, 5: PAY

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme_pref', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  const [messages, setMessages] = useState([
    {
      id: 1,
      sender: 'assistant',
      text: `Hello! How can I help you today? Feel free to ask about products in our catalog or start a purchase.`,
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
      reasoning: 'Guardrail Engine & Neon DB initialized. Spend cap limit active at ₹10,000.',
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

  // Handle user selecting a product card via "Buy Now" button
  const handleSelectProduct = (product, initialQty = 1) => {
    setSelectedProduct(product);
    setSelectedQty(initialQty);
    setActiveStep(3); // STOCK VERIFIED

    const selectMsg = {
      id: Date.now(),
      sender: 'assistant',
      text: `Selected **${product.name}** (\`${product.sku}\`). Specify quantity or click **Continue to Shipping** in the Purchase Summary panel to complete your order.`,
      agentActivity: `Product selected: ${product.name} (SKU: ${product.sku}) • ${product.stock} available in stock`,
    };

    setMessages((prev) => [...prev, selectMsg]);
  };

  const handleResetSelection = () => {
    setSelectedProduct(null);
    setSelectedQty(1);
    setActiveStep(1);
  };

  const handleSendMessage = async (userText) => {
    const userMsg = {
      id: Date.now(),
      sender: 'user',
      text: userText,
    };

    setMessages((prev) => [...prev, userMsg]);
    const lowerText = userText.toLowerCase();

    // Check for natural language selection e.g. "buy the second one", "buy 2 of the first one"
    if ((lowerText.includes('second') || lowerText.includes('first') || lowerText.includes('third') || lowerText.includes('buy the')) && messages.length > 0) {
      const lastMsgWithProducts = [...messages].reverse().find((m) => m.products && m.products.length > 0);
      if (lastMsgWithProducts) {
        let index = 0;
        if (lowerText.includes('second')) index = 1;
        else if (lowerText.includes('third')) index = 2;

        if (lastMsgWithProducts.products[index]) {
          const item = lastMsgWithProducts.products[index];
          let qty = 1;
          const matchNum = lowerText.match(/(\d+)/);
          if (matchNum) qty = Math.max(1, parseInt(matchNum[1]));

          handleSelectProduct(item, qty);
          return;
        }
      }
    }

    setActiveStep(1); // SEARCH
    const res = await sendChatMessage(userText, { sessionId });

    if (res.success) {
      const returnedProducts = res.data.products || [];
      const botMsg = {
        id: Date.now() + 1,
        sender: 'assistant',
        text: res.data.reply,
        products: returnedProducts,
        blocked: res.data.blocked || false,
        agentActivity: returnedProducts.length > 0
          ? `Searched catalog: Found ${returnedProducts.length} matching products`
          : res.data.blocked
          ? `Guardrail enforcement blocked action`
          : null,
      };

      setMessages((prev) => [...prev, botMsg]);

      if (returnedProducts.length > 0) {
        setActiveStep(2); // SELECT
      }

      if (res.data.auditEntry) {
        setAuditLogs((prev) => [res.data.auditEntry, ...prev]);
        if (res.data.blocked) {
          setAuditOpen(true);
        }
      }
    }
  };

  const handleAuditLogged = (newEntry) => {
    setAuditLogs((prev) => [newEntry, ...prev]);
  };

  const handleOrderSuccess = (orderData) => {
    setActiveStep(5); // PAID
    if (orderData?.auditEntry) {
      setAuditLogs((prev) => [orderData.auditEntry, ...prev]);
    }
  };

  const handleClearLogs = () => {
    setAuditLogs([]);
  };

  const blockedCount = auditLogs.filter((l) => l.result === 'BLOCKED').length;

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Header
        theme={theme}
        onToggleTheme={toggleTheme}
        backendConnected={backendConnected}
        spendCap={10000}
        auditOpen={auditOpen}
        onToggleAudit={() => setAuditOpen(!auditOpen)}
        blockedCount={blockedCount}
      />

      <div className="app-main-layout">
        {/* Left / Center Column: Conversation & Product Discovery */}
        <div className="chat-discovery-column">
          <ChatPanel
            messages={messages}
            activeStep={activeStep}
            onSendMessage={handleSendMessage}
            onSelectProduct={handleSelectProduct}
            onAuditLogged={handleAuditLogged}
          />
        </div>

        {/* Right Column: Persistent Purchase Summary Panel */}
        <div className="purchase-summary-column">
          <PurchaseSummaryPanel
            selectedProduct={selectedProduct}
            quantity={selectedQty}
            onQtyChange={setSelectedQty}
            onResetSelection={handleResetSelection}
            onOrderSuccess={handleOrderSuccess}
          />
        </div>
      </div>

      <AuditLogPanel
        open={auditOpen}
        onClose={() => setAuditOpen(false)}
        auditLogs={auditLogs}
        onClearLogs={handleClearLogs}
        spendCap={10000}
      />
    </div>
  );
}
