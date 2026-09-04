import React, { useState, useRef, useEffect } from 'react';
import { ArrowUp, User, ShieldAlert, ShoppingBag, Plus, Minus, CheckCircle2, Database } from 'lucide-react';
import AgentWorkflowBar from './AgentWorkflowBar';

const DEFAULT_FALLBACK_IMAGE = 'https://images.unsplash.com/photo-1560343776-97e7d202ff0e?w=800&auto=format&fit=crop&q=80';

function ProductCard({ item, onSelectForPurchase }) {
  const [qty, setQty] = useState(1);
  const [imgSrc, setImgSrc] = useState(item.image || DEFAULT_FALLBACK_IMAGE);

  const isOutOfStock = item.stock === 0;
  const isLowStock = item.stock > 0 && item.stock <= 3;
  const subtotal = (item.price || 0) * qty;

  const handleQtyChange = (delta) => {
    const nextQty = qty + delta;
    if (nextQty >= 1 && nextQty <= item.stock) {
      setQty(nextQty);
    }
  };

  return (
    <div className="product-item-card">
      <div className="product-img-wrapper">
        <img
          src={imgSrc}
          alt={item.name}
          className="product-img"
          loading="lazy"
          onError={() => setImgSrc(DEFAULT_FALLBACK_IMAGE)}
        />
        {item.category && <span className="category-pill">{item.category}</span>}
      </div>

      <div className="product-card-content">
        <div className="product-header-row">
          <span className="product-sku">SKU: {item.sku}</span>
          <span className={`stock-badge ${isOutOfStock ? 'out-stock' : isLowStock ? 'low-stock' : 'in-stock'}`}>
            {isOutOfStock ? 'Out of Stock' : `✓ ${item.stock} available`}
          </span>
        </div>

        <h4 className="product-title">{item.name}</h4>
        {item.description && <p className="product-desc">{item.description}</p>}

        <div className="product-price-row">
          <span className="product-price">₹{(item.price || 0).toLocaleString()}</span>
        </div>

        {!isOutOfStock ? (
          <div className="card-action-row">
            <div className="card-qty-controls">
              <button
                type="button"
                className="card-qty-btn"
                disabled={qty <= 1}
                onClick={() => handleQtyChange(-1)}
              >
                <Minus size={12} />
              </button>
              <span className="card-qty-num">{qty}</span>
              <button
                type="button"
                className="card-qty-btn"
                disabled={qty >= item.stock}
                onClick={() => handleQtyChange(1)}
              >
                <Plus size={12} />
              </button>
            </div>

            <button
              type="button"
              className="buy-now-btn"
              onClick={() => onSelectForPurchase(item, qty)}
            >
              <ShoppingBag size={14} />
              <span>Buy Now • ₹{subtotal.toLocaleString()}</span>
            </button>
          </div>
        ) : (
          <button className="buy-now-btn disabled" disabled>
            <span>Out of Stock</span>
          </button>
        )}
      </div>
    </div>
  );
}

export default function ChatPanel({
  messages,
  activeStep,
  onSendMessage,
  onSelectProduct,
  showConsentPrompt,
  onConsentChoice,
}) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim()) return;
    onSendMessage(input);
    setInput('');
  };

  return (
    <div className="chat-panel-container">
      {/* Top Compact Workflow Indicator Bar */}
      <AgentWorkflowBar activeStep={activeStep} />

      {/* Privacy Consent Prompt Banner */}
      {showConsentPrompt && (
        <div className="consent-banner-bar">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Database size={15} color="var(--accent-primary)" />
            <span>Save this conversation so I can pick up where we left off?</span>
          </div>
          <div className="consent-btn-group">
            <button type="button" className="consent-btn yes" onClick={() => onConsentChoice(true)}>
              Yes
            </button>
            <button type="button" className="consent-btn no" onClick={() => onConsentChoice(false)}>
              No
            </button>
          </div>
        </div>
      )}

      <div className="messages-scroll-area">
        {messages.map((msg) => (
          <div key={msg.id} className={`message-row ${msg.sender}`}>
            {msg.sender === 'assistant' && (
              <div className="message-avatar">
                <img src="/agent-logo.png" alt="Agent Logo" className="agent-avatar-img" />
              </div>
            )}

            <div className="message-body">
              {msg.blocked && (
                <div className="blocked-banner">
                  <ShieldAlert size={14} />
                  <span>Guardrail Enforcement Blocked Action</span>
                </div>
              )}

              {/* In-Chat Agent Activity Card */}
              {msg.agentActivity && (
                <div className="in-chat-activity-card">
                  <CheckCircle2 size={14} color="var(--accent-success)" />
                  <span>{msg.agentActivity}</span>
                </div>
              )}

              <div style={{ whiteSpace: 'pre-wrap' }}>
                {msg.sender === 'assistant'
                  ? msg.text
                      .split('\n')
                      .filter((line) => !line.includes('|'))
                      .join('\n')
                      .replace(/\*\*(.*?)\*\*/g, '$1')
                      .replace(/`([^`]+)`/g, '$1')
                      .trim()
                  : msg.text}
              </div>

              {/* Render Product Cards when type is product_search or products exist */}
              {msg.products && msg.products.length > 0 && (
                <div className="products-container">
                  {msg.products.map((item) => (
                    <ProductCard
                      key={item.sku}
                      item={item}
                      onSelectForPurchase={onSelectProduct}
                    />
                  ))}
                </div>
              )}
            </div>

            {msg.sender === 'user' && (
              <div className="message-avatar">
                <User size={16} />
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Fixed Bottom Command Dock */}
      <div className="input-dock">
        <div className="input-box-wrapper">
          <form onSubmit={handleSubmit} className="input-form">
            <input
              type="text"
              className="chat-input-field"
              placeholder="Ask the agent to find products, compare options, or start a purchase..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
            />
            <button type="submit" className="send-circle-btn" title="Send Message">
              <ArrowUp size={18} />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
