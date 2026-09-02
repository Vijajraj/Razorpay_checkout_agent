import React, { useState, useRef, useEffect } from 'react';
import { ArrowUp, Bot, User, ShieldAlert, ShoppingBag, Plus, Minus, CheckCircle2, Search, ArrowRight } from 'lucide-react';
import AgentWorkflowBar from './AgentWorkflowBar';

const DEFAULT_FALLBACK_IMAGE = 'https://images.unsplash.com/photo-1560343776-97e7d202ff0e?w=800&auto=format&fit=crop&q=80';

const SUGGESTION_CHIPS = [
  'Running shoes under ₹3000',
  'Black sneakers',
  'Oversized T-shirts',
  'Show me products under ₹1500',
];

function ProductCardItem({ item, onSelectForPurchase }) {
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
          <span className="product-sku">{item.sku}</span>
          <span className={`stock-badge ${isOutOfStock ? 'out-stock' : isLowStock ? 'low-stock' : 'in-stock'}`}>
            {isOutOfStock ? 'Out of Stock' : isLowStock ? `Only ${item.stock} left` : 'In Stock'}
          </span>
        </div>

        <h4 className="product-title">{item.name}</h4>
        {item.description && <p className="product-desc">{item.description}</p>}

        <div className="product-price-row">
          <span className="product-price">₹{(item.price || 0).toLocaleString()}</span>
          {item.stock > 0 && (
            <span className="stock-count-muted">{item.stock} available</span>
          )}
        </div>

        {item.tags && item.tags.length > 0 && (
          <div className="product-tags">
            {item.tags.map((tag, idx) => (
              <span key={idx} className="tag-pill">#{tag}</span>
            ))}
          </div>
        )}

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
  onSelectProduct
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

  const handleChipClick = (chipText) => {
    onSendMessage(chipText);
  };

  return (
    <div className="chat-panel-container">
      {/* Top Compact Workflow Indicator Bar */}
      <AgentWorkflowBar activeStep={activeStep} />

      <div className="messages-scroll-area">
        {messages.map((msg) => (
          <div key={msg.id} className={`message-row ${msg.sender}`}>
            {msg.sender === 'assistant' && (
              <div className="message-avatar">
                <Bot size={16} />
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

              <div style={{ whiteSpace: 'pre-wrap' }}>{msg.text}</div>

              {/* Product recommendation cards */}
              {msg.products && msg.products.length > 0 && (
                <div className="products-container">
                  {msg.products.map((item) => (
                    <ProductCardItem
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

      {/* Fixed Bottom AI Shopping Command Bar */}
      <div className="input-dock">
        <div className="input-box-wrapper">
          {/* Quick Suggestion Chips */}
          <div className="suggestion-chips-row">
            {SUGGESTION_CHIPS.map((chip, idx) => (
              <button
                key={idx}
                type="button"
                className="chip-pill"
                onClick={() => handleChipClick(chip)}
              >
                <Search size={11} />
                <span>{chip}</span>
              </button>
            ))}
          </div>

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
