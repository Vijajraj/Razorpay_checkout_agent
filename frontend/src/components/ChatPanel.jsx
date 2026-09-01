import React, { useState, useRef, useEffect } from 'react';
import { ArrowUp, Bot, User, ShieldAlert, ShoppingBag, ExternalLink, CheckCircle2 } from 'lucide-react';
import RedTeamPresets from './RedTeamPresets';
import { createRazorpayOrder } from '../services/api';

export default function ChatPanel({ messages, onSendMessage, onAuditLogged }) {
  const [input, setInput] = useState('');
  const [activeOrder, setActiveOrder] = useState(null);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, activeOrder]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim()) return;
    onSendMessage(input);
    setInput('');
  };

  const handleSelectPreset = (promptText) => {
    onSendMessage(promptText);
  };

  const handleCheckoutClick = (product) => {
    try {
      const orderResult = createRazorpayOrder(product.sku, 1);
      if (onAuditLogged && orderResult.auditEntry) {
        onAuditLogged(orderResult.auditEntry);
      }

      if (orderResult.success) {
        setActiveOrder(orderResult);
      } else {
        alert(`Guardrail Block: ${orderResult.reason}`);
      }
    } catch (err) {
      alert(`Error creating order: ${err.message}`);
    }
  };

  return (
    <div className="chat-container">
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

              <div style={{ whiteSpace: 'pre-wrap' }}>{msg.text}</div>

              {/* Product recommendation cards */}
              {msg.products && msg.products.length > 0 && (
                <div className="products-container">
                  {msg.products.map((item) => (
                    <div key={item.sku} className="product-item">
                      <div>
                        <div className="product-sku">{item.sku}</div>
                        <div className="product-name">{item.name}</div>
                        <div className="product-price">₹{item.price.toLocaleString()}</div>
                        <div className="stock-tag">
                          {item.stock > 0 ? `${item.stock} in stock` : 'Out of stock'}
                        </div>
                      </div>

                      <button
                        className="order-btn"
                        disabled={item.stock === 0}
                        onClick={() => handleCheckoutClick(item)}
                      >
                        <ShoppingBag size={14} />
                        <span>Checkout via Razorpay</span>
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Active Razorpay Link Card */}
              {activeOrder && msg.sender === 'assistant' && msg.id === messages[messages.length - 1].id && (
                <div className="razorpay-link-card">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#818cf8', fontWeight: 600, fontSize: '13px' }}>
                    <CheckCircle2 size={15} color="#34d399" />
                    <span>Razorpay Order Ready: #{activeOrder.orderId}</span>
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                    Total Amount: <strong>₹{activeOrder.amount.toLocaleString()}</strong>
                  </div>
                  <a
                    href={activeOrder.paymentLink}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="pay-btn"
                    onClick={(e) => {
                      e.preventDefault();
                      alert(`[Razorpay Test Mode Payment Simulated]\n\nOrder ID: ${activeOrder.orderId}\nStatus: SUCCESS (PAID)`);
                    }}
                  >
                    <span>Complete Test Payment</span>
                    <ExternalLink size={13} />
                  </a>
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

      {/* Floating Input Dock */}
      <div className="input-dock">
        <div className="input-box-wrapper">
          <RedTeamPresets onSelectPreset={handleSelectPreset} />

          <form onSubmit={handleSubmit} className="input-form">
            <input
              type="text"
              className="chat-input-field"
              placeholder="Ask agent to search catalog or purchase items..."
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
