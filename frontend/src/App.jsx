import React, { useState, useEffect, useCallback } from 'react';
import Header from './components/Header';
import ChatSidebar from './components/ChatSidebar';
import ChatPanel from './components/ChatPanel';
import PurchaseSummaryPanel from './components/PurchaseSummaryPanel';
import AuditLogPanel from './components/AuditLogPanel';
import CatalogPanel from './components/CatalogPanel';
import {
  sendChatMessage,
  checkBackendHealth,
  getCatalog,
  sendChatConsent,
  getChatHistory,
  deleteChatHistory,
  getChatSessions,
} from './services/api';

function isCatalogBrowsePrompt(text) {
  const normalized = text.toLowerCase();
  const patterns = [
    'what are the things',
    "what's in",
    'what is in',
    'what do you have',
    'show me everything',
    'all products',
    'browse catalog',
    'browse catalogue',
  ];
  return (normalized.includes('catalog') || normalized.includes('catalogue')) && patterns.some((pattern) => normalized.includes(pattern));
}

export default function App() {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('theme_pref') || 'dark';
  });

  const [backendConnected, setBackendConnected] = useState(false);
  const [auditOpen, setAuditOpen] = useState(false);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [catalogProducts, setCatalogProducts] = useState([]);

  // Dynamic active session ID & saved sessions list (persisted across reloads)
  const [sessionId, setSessionId] = useState(() => {
    return localStorage.getItem('active_session_id') || `sess_${Math.random().toString(36).substring(2, 9)}`;
  });
  const [sessions, setSessions] = useState([]);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => window.innerWidth < 768);

  const [selectedProduct, setSelectedProduct] = useState(null);
  const [selectedQty, setSelectedQty] = useState(1);
  const [activeStep, setActiveStep] = useState(1); // 1: SEARCH, 2: SELECT, 3: VERIFY, 4: ORDER, 5: PAY
  const [mobileSummaryOpen, setMobileSummaryOpen] = useState(false);

  // Privacy Consent & Chat History State
  const [showConsentPrompt, setShowConsentPrompt] = useState(false);
  const [consentGiven, setConsentGiven] = useState(() => {
    return localStorage.getItem('chat_consent_pref') === 'true' ? true : null;
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme_pref', theme);
  }, [theme]);

  useEffect(() => {
    if (sessionId) {
      localStorage.setItem('active_session_id', sessionId);
    }
  }, [sessionId]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  const DEFAULT_WELCOME_MESSAGE = {
    id: 1,
    sender: 'assistant',
    text: `Hello! How can I help you today? Feel free to ask about products in our catalog or start a purchase.`,
    products: [],
  };

  const [messages, setMessages] = useState([DEFAULT_WELCOME_MESSAGE]);

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

  const refreshSessionsList = useCallback(async () => {
    const res = await getChatSessions();
    if (res && res.sessions) {
      setSessions(res.sessions);
    }
  }, []);

  const openCatalogPanel = useCallback(async () => {
    setCatalogOpen(true);
    const products = await getCatalog();
    setCatalogProducts(products);
  }, []);

  useEffect(() => {
    async function verifyHealthAndLoad() {
      const health = await checkBackendHealth();
      setBackendConnected(health.online);

      await refreshSessionsList();
      const products = await getCatalog();
      setCatalogProducts(products);

      const savedConsentPref = localStorage.getItem('chat_consent_pref');

      // Check if stored chat history exists for active sessionId
      const historyRes = await getChatHistory(sessionId);
      if (historyRes && historyRes.messages && historyRes.messages.length > 0) {
        const loaded = historyRes.messages.map((m, idx) => ({
          id: m.id || idx + 10,
          sender: m.role === 'user' ? 'user' : 'assistant',
          text: m.content,
        }));
        setMessages(loaded);
        setConsentGiven(true);
        setShowConsentPrompt(false);
      } else if (savedConsentPref === 'true') {
        // Auto-enable consent for new sessions if user already granted global consent
        await sendChatConsent(sessionId, true);
        setConsentGiven(true);
        setShowConsentPrompt(false);
      }
    }
    verifyHealthAndLoad();
  }, [sessionId, refreshSessionsList]);

  // Handle switching to a past session from the sidebar
  const handleSelectSession = async (sid) => {
    if (sid === sessionId) return;
    setSessionId(sid);
    localStorage.setItem('active_session_id', sid);
    setSelectedProduct(null);
    setSelectedQty(1);
    setActiveStep(1);

    const historyRes = await getChatHistory(sid);
    if (historyRes && historyRes.messages && historyRes.messages.length > 0) {
      const loaded = historyRes.messages.map((m, idx) => ({
        id: m.id || idx + 10,
        sender: m.role === 'user' ? 'user' : 'assistant',
        text: m.content,
      }));
      setMessages(loaded);
      setConsentGiven(true);
      setShowConsentPrompt(false);
    } else {
      setMessages([DEFAULT_WELCOME_MESSAGE]);
    }
  };

  // Handle starting a fresh session (+ New Chat)
  const handleNewChat = async () => {
    const newId = `sess_${Math.random().toString(36).substring(2, 9)}`;
    setSessionId(newId);
    localStorage.setItem('active_session_id', newId);
    setMessages([DEFAULT_WELCOME_MESSAGE]);
    setSelectedProduct(null);
    setSelectedQty(1);
    setActiveStep(1);

    const savedConsentPref = localStorage.getItem('chat_consent_pref');
    if (savedConsentPref === 'true') {
      await sendChatConsent(newId, true);
      setConsentGiven(true);
      setShowConsentPrompt(false);
    } else {
      setConsentGiven(null);
      setShowConsentPrompt(false);
    }
  };

  // Handle deleting a session
  const handleDeleteSession = async (sid) => {
    await deleteChatHistory(sid);
    await refreshSessionsList();

    if (sid === sessionId) {
      handleNewChat();
    }
  };

  // Handle user selecting a product card via "Buy Now" button
  const handleSelectProduct = (product, initialQty = 1) => {
    setSelectedProduct(product);
    setSelectedQty(initialQty);
    setActiveStep(2); // Step 2: Product Selected
    setMobileSummaryOpen(true);

    const selectMsg = {
      id: Date.now(),
      sender: 'assistant',
      text: `${product.name} selected.`,
      agentActivity: `Product selected: ${product.name}`,
    };

    setMessages((prev) => [...prev, selectMsg]);
  };

  const handleResetSelection = () => {
    setSelectedProduct(null);
    setSelectedQty(1);
    setActiveStep(1);
    setMobileSummaryOpen(false);
  };

  const handleSendMessage = async (userText) => {
    const userMsg = {
      id: Date.now(),
      sender: 'user',
      text: userText,
    };

    setMessages((prev) => [...prev, userMsg]);
    const lowerText = userText.toLowerCase().trim();

    if (isCatalogBrowsePrompt(userText)) {
      await openCatalogPanel();
      setMessages((prev) => [...prev, {
        id: Date.now() + 1,
        sender: 'assistant',
        text: "You can browse everything in the catalog panel on the left - or tell me what you're looking for and I'll help you find it.",
        products: [],
      }]);
      return;
    }

    // Handle quantity update from chat if product is selected
    if (selectedProduct) {
      const qtyMatch = lowerText.match(/^(?:buy\s+|qty\s+|quantity\s+)?(\d+)$/i) || lowerText.match(/(?:buy|set|make\s+it)\s+(\d+)/i);
      if (qtyMatch) {
        const newQty = Math.max(1, Math.min(selectedProduct.stock, parseInt(qtyMatch[1], 10)));
        setSelectedQty(newQty);
        const qtyMsg = {
          id: Date.now() + 1,
          sender: 'assistant',
          text: `Quantity updated to ${newQty}.`,
        };
        setMessages((prev) => [...prev, qtyMsg]);
        return;
      }
    }

    // Check for natural language selection e.g. "buy the second one"
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

    const res = await sendChatMessage(userText, { sessionId });
    const responseData = res?.data;

    if (res?.success && responseData) {
      if (responseData.needs_consent && consentGiven === null) {
        setShowConsentPrompt(true);
      }

      const returnedProducts = Array.isArray(responseData.products) ? responseData.products : [];
      const comparisonProducts = Array.isArray(responseData.comparison) ? responseData.comparison : [];
      const botMsg = {
        id: Date.now() + 1,
        sender: 'assistant',
        text: typeof responseData.reply === 'string' && responseData.reply.trim()
          ? responseData.reply
          : "I'm having a little trouble processing that right now - mind trying again in a moment?",
        products: returnedProducts,
        comparison: comparisonProducts,
        blocked: responseData.blocked || false,
        error: responseData.type === 'error',
        agentActivity: comparisonProducts.length > 0
          ? `Compared ${comparisonProducts.length} catalog products`
          : returnedProducts.length > 0
          ? `Searched catalog: Found ${returnedProducts.length} matching products`
          : responseData.blocked
          ? `Guardrail enforcement blocked action`
          : responseData.type === 'error'
          ? 'Chat request needs a retry'
          : null,
      };

      setMessages((prev) => [...prev, botMsg]);

      if (returnedProducts.length > 0) {
        setActiveStep(1); // Step 1: Product Searched
      }

      if (responseData.auditEntry) {
        setAuditLogs((prev) => [responseData.auditEntry, ...prev]);
        if (responseData.blocked) {
          setAuditOpen(true);
        }
      }

      // Refresh saved sessions list
      refreshSessionsList();
    } else {
      setMessages((prev) => [...prev, {
        id: Date.now() + 1,
        sender: 'assistant',
        text: "I'm having a little trouble processing that right now - mind trying again in a moment?",
        products: [],
        error: true,
        agentActivity: 'Chat request needs a retry',
      }]);
    }
  };

  const handleConsentChoice = async (consent) => {
    setShowConsentPrompt(false);
    setConsentGiven(consent);
    if (consent) {
      localStorage.setItem('chat_consent_pref', 'true');
    } else {
      localStorage.setItem('chat_consent_pref', 'false');
    }
    await sendChatConsent(sessionId, consent);
    refreshSessionsList();
  };

  const handleClearChatHistory = async () => {
    await deleteChatHistory(sessionId);
    localStorage.removeItem('chat_consent_pref');
    setMessages([DEFAULT_WELCOME_MESSAGE]);
    setConsentGiven(null);
    setShowConsentPrompt(false);
    refreshSessionsList();
  };

  const handleAuditLogged = (newEntry) => {
    setAuditLogs((prev) => [newEntry, ...prev]);
  };

  const handleStockVerified = (stockData) => {
    setActiveStep(3); // Step 3: Stock Verified
    if (stockData?.auditEntry) {
      setAuditLogs((prev) => [stockData.auditEntry, ...prev]);
    }
  };

  const handleOrderCreated = (orderData) => {
    setActiveStep(4); // Step 4: Order Created
    if (orderData?.auditEntry) {
      setAuditLogs((prev) => [orderData.auditEntry, ...prev]);
    }
  };

  const handleOrderSuccess = (orderData) => {
    setActiveStep(5); // Step 5: Payment Verified
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
        catalogOpen={catalogOpen}
        onToggleCatalog={() => {
          if (catalogOpen) {
            setCatalogOpen(false);
          } else {
            openCatalogPanel();
          }
        }}
        blockedCount={blockedCount}
        onClearChatHistory={handleClearChatHistory}
        sidebarCollapsed={sidebarCollapsed}
        onToggleSidebar={() => setSidebarCollapsed(!sidebarCollapsed)}
        mobileSummaryOpen={mobileSummaryOpen}
        onToggleMobileSummary={() => setMobileSummaryOpen(!mobileSummaryOpen)}
        hasSelectedItem={!!selectedProduct}
      />

      <div className="app-main-layout">
        {/* Left Column: Persistent Saved Chat History Sidebar */}
        <ChatSidebar
          sessions={sessions}
          activeSessionId={sessionId}
          onSelectSession={(sid) => {
            handleSelectSession(sid);
            setSidebarCollapsed(true);
          }}
          onNewChat={() => {
            handleNewChat();
            setSidebarCollapsed(true);
          }}
          onDeleteSession={handleDeleteSession}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
        />

        {/* Center Column: Conversation & Product Discovery */}
        <div className="chat-discovery-column">
          <ChatPanel
            messages={messages}
            activeStep={activeStep}
            onSendMessage={handleSendMessage}
            onSelectProduct={handleSelectProduct}
            onAuditLogged={handleAuditLogged}
            showConsentPrompt={showConsentPrompt}
            onConsentChoice={handleConsentChoice}
          />
        </div>

        {/* Right Column: Persistent Purchase Summary Panel */}
        <div className={`purchase-summary-column ${mobileSummaryOpen ? 'mobile-open' : ''}`}>
          <PurchaseSummaryPanel
            key={selectedProduct?.sku || 'empty-purchase'}
            selectedProduct={selectedProduct}
            quantity={selectedQty}
            onQtyChange={setSelectedQty}
            onResetSelection={handleResetSelection}
            onStockVerified={handleStockVerified}
            onOrderCreated={handleOrderCreated}
            onOrderSuccess={handleOrderSuccess}
            sessionId={sessionId}
          />
        </div>

        {/* Mobile Backdrop Overlays */}
        {!sidebarCollapsed && (
          <div className="mobile-overlay-backdrop sidebar-backdrop" onClick={() => setSidebarCollapsed(true)} />
        )}
        {mobileSummaryOpen && (
          <div className="mobile-overlay-backdrop summary-backdrop" onClick={() => setMobileSummaryOpen(false)} />
        )}
      </div>

      <AuditLogPanel
        open={auditOpen}
        onClose={() => setAuditOpen(false)}
        auditLogs={auditLogs}
        onClearLogs={handleClearLogs}
        spendCap={10000}
      />

      <CatalogPanel
        open={catalogOpen}
        onClose={() => setCatalogOpen(false)}
        products={catalogProducts}
        onSelectProduct={handleSelectProduct}
      />
    </div>
  );
}
