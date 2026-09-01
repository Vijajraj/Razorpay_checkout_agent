import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, ShieldAlert, ShoppingCart, ExternalLink, CheckCircle, AlertTriangle } from 'lucide-react';
import RedTeamPresets from './RedTeamPresets';
import { createRazorpayOrder } from '../services/api';

export default function ChatPanel({ messages, onSendMessage, onAuditLogged }) {
  const [input, setInput] = useState('');
  const [activePaymentOrder, setActivePaymentOrder] = useState(null);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, activePaymentOrder]);

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
        setActivePaymentOrder(orderResult);
      } else {
        alert(`Order Blocked by Guardrail Engine: ${orderResult.reason}`);
      }
    } catch (err) {
      alert(`Error creating order: ${err.message}`);
    }
  };

  return (
    <div className="chat-section">
      <RedTeamPresets onSelectPreset={handleSelectPreset} />

      <div className="messages-container">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`message-bubble ${msg.sender} ${msg.blocked ? 'blocked' : ''}`}
          >
            <div className="avatar">
              {msg.sender === 'user' ? <User size={16} /> : <Bot size={16} />}
            </div>

            <div className="message-content">
              {msg.blocked && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#ef4444', fontWeight: 700, marginBottom: '8px' }}>
                  <ShieldAlert size={16} />
                  <span>GUARDRAIL ENFORCED BLOCK</span>
                </div>
              )}

              <div style={{ whiteSpace: 'pre-wrap' }}>{msg.text}</div>

              {/* Products list if recommended */}
              {msg.products && msg.products.length > 0 && (
                <div className="products-grid">
                  {msg.products.map((item) => (
                    <div key={item.sku} className="product-card">
                      <div>
                        <div className="product-sku">{item.sku}</div>
                        <div className="product-title">{item.name}</div>
                        <div className="product-price">₹{item.price.toLocaleString()}</div>
                        <div className={`stock-badge ${item.stock > 0 ? 'in-stock' : 'out-stock'}`}>
                          {item.stock > 0 ? `${item.stock} in stock` : 'Out of stock'}
                        </div>
                      </div>

                      <button
                        className="buy-btn"
                        disabled={item.stock === 0}
                        onClick={() => handleCheckoutClick(item)}
                      >
                        <ShoppingCart size={14} />
                        <span>Order via Razorpay</span>
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Razorpay Active Payment Box */}
              {activePaymentOrder && msg.sender === 'assistant' && msg.id === messages[messages.length - 1].id && (
                <div className="razorpay-link-box">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#60a5fa', fontWeight: 700 }}>
                    <CheckCircle size={16} color="#10b981" />
                    <span>Razorpay Order Created: #{activePaymentOrder.orderId}</span>
                  </div>
                  <div style={{ fontSize: '12px', color: '#9ca3af' }}>
                    Item: <strong>{activePaymentOrder.productName}</strong> | Amount: <strong>₹{activePaymentOrder.amount.toLocaleString()}</strong>
                  </div>
                  <a
                    href={activePaymentOrder.paymentLink}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="pay-now-btn"
                    onClick={(e) => {
                      e.preventDefault();
                      alert(`[Razorpay Test Mode Simulated Payment Success]\n\nOrder ID: ${activePaymentOrder.orderId}\nPayment Link: ${activePaymentOrder.paymentLink}\nStatus: PAID`);
                    }}
                  >
                    <span>Pay with Razorpay (Test Mode)</span>
                    <ExternalLink size={14} />
                  </a>
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <form onSubmit={handleSubmit} className="input-container">
        <input
          type="text"
          className="chat-input"
          placeholder="Ask agent to search catalog or purchase (e.g. 'I need running shoes under ₹3000')"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button type="submit" className="send-btn">
          <Send size={18} />
        </button>
      </form>
    </div>
  );
}
