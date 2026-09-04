import React, { useState } from 'react';
import { ShoppingBag, Plus, Minus, ArrowRight, ArrowLeft, CheckCircle2, CreditCard, Loader2, AlertCircle, RefreshCw } from 'lucide-react';
import { createOrderOnServer, verifyPaymentOnServer, verifyStock } from '../services/api';

const DEFAULT_FALLBACK_IMAGE = 'https://images.unsplash.com/photo-1560343776-97e7d202ff0e?w=800&auto=format&fit=crop&q=80';

export default function PurchaseSummaryPanel({
  selectedProduct,
  quantity,
  onQtyChange,
  onResetSelection,
  onOrderSuccess,
  onStockVerified,
  onOrderCreated,
  sessionId = 'session_default',
}) {
  const [step, setStep] = useState(1); // 1: Product Selected, 2: Shipping Form, 3: Order Review, 4: Paid Success
  const [imgSrc, setImgSrc] = useState(selectedProduct?.image || DEFAULT_FALLBACK_IMAGE);

  const [shipping, setShipping] = useState({
    fullName: '',
    phone: '',
    address1: '',
    address2: '',
    city: '',
    state: '',
    pinCode: '',
  });

  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [orderResult, setOrderResult] = useState(null);
  const [paymentError, setPaymentError] = useState(null);

  if (!selectedProduct) {
    return (
      <aside className="purchase-summary-panel empty">
        <div className="panel-header">
          <h3>PURCHASE SUMMARY</h3>
        </div>
        <div className="panel-empty-state">
          <div className="empty-icon-circle">
            <ShoppingBag size={24} />
          </div>
          <h4>No product selected</h4>
          <p>Select a product card from the conversation to begin your checkout.</p>
        </div>
      </aside>
    );
  }

  const unitPrice = parseFloat(selectedProduct.price || 0);
  const subtotal = unitPrice * quantity;
  const shippingFee = 0;
  const totalAmount = subtotal + shippingFee;

  const handleQtyChange = (delta) => {
    const nextQty = quantity + delta;
    if (nextQty >= 1 && nextQty <= selectedProduct.stock) {
      onQtyChange(nextQty);
    }
  };

  const handleContinueToShipping = async () => {
    setLoading(true);
    setPaymentError(null);
    try {
      const stockRes = await verifyStock(selectedProduct.sku, quantity, sessionId);
      if (stockRes && stockRes.verified === false) {
        setPaymentError(stockRes.message || `Insufficient stock. Only ${stockRes.available_stock || 0} units available.`);
        setLoading(false);
        return;
      }
      if (onStockVerified) {
        onStockVerified(stockRes);
      }
      setStep(2);
    } catch (err) {
      setPaymentError(err.message || 'Stock verification failed.');
    } finally {
      setLoading(false);
    }
  };

  const validateAddressForm = () => {
    const newErrors = {};
    if (!shipping.fullName.trim()) newErrors.fullName = 'Full name is required';
    if (!shipping.phone.trim() || !/^\d{10}$/.test(shipping.phone.trim())) {
      newErrors.phone = 'Valid 10-digit phone number is required';
    }
    if (!shipping.address1.trim()) newErrors.address1 = 'Address line 1 is required';
    if (!shipping.city.trim()) newErrors.city = 'City is required';
    if (!shipping.state.trim()) newErrors.state = 'State is required';
    if (!shipping.pinCode.trim() || !/^\d{6}$/.test(shipping.pinCode.trim())) {
      newErrors.pinCode = 'Valid 6-digit PIN code is required';
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleShippingSubmit = (e) => {
    e.preventDefault();
    if (validateAddressForm()) {
      setStep(3); // Go to Order Review
    }
  };

  const handleProceedToPayment = async () => {
    setLoading(true);
    setPaymentError(null);

    try {
      // 1. Create Order on Server
      const payload = {
        sku: selectedProduct.sku,
        quantity: quantity,
        customer_name: shipping.fullName,
        customer_phone: shipping.phone,
        address_line1: shipping.address1,
        address_line2: shipping.address2,
        city: shipping.city,
        state: shipping.state,
        pin_code: shipping.pinCode,
        session_id: sessionId,
      };

      const serverRes = await createOrderOnServer(payload);

      if (!serverRes || !serverRes.success) {
        throw new Error(serverRes?.detail || 'Order creation failed.');
      }

      setOrderResult(serverRes);
      if (onOrderCreated) {
        onOrderCreated(serverRes);
      }

      // 2. Razorpay Checkout Modal
      if (window.Razorpay) {
        const options = {
          key: serverRes.razorpay_key_id || 'rzp_test_mockkey123',
          amount: Math.round(totalAmount * 100),
          currency: 'INR',
          name: 'Razorpay Agentic Store',
          description: `Order ${serverRes.order_id} - ${selectedProduct.name}`,
          order_id: serverRes.razorpay_order_id,
          handler: async function (response) {
            try {
              const verifyRes = await verifyPaymentOnServer({
                order_id: serverRes.order_id,
                razorpay_order_id: response.razorpay_order_id || serverRes.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id || `pay_sim_${Date.now()}`,
                razorpay_signature: response.razorpay_signature || 'sig_simulated_valid',
              });

              if (verifyRes.success) {
                setStep(4); // Paid Success
                if (onOrderSuccess) onOrderSuccess(serverRes);
              } else {
                setPaymentError('Payment verification failed.');
              }
            } catch (vErr) {
              setPaymentError(`Verification error: ${vErr.message}`);
            } finally {
              setLoading(false);
            }
          },
          modal: {
            ondismiss: function () {
              setLoading(false);
              setPaymentError('Payment window closed by user.');
            },
          },
          prefill: {
            name: shipping.fullName,
            contact: shipping.phone,
          },
          theme: { color: '#6366f1' },
        };

        const rzp = new window.Razorpay(options);
        rzp.open();
      } else {
        // Fallback simulation mode
        setTimeout(async () => {
          await verifyPaymentOnServer({
            order_id: serverRes.order_id,
            razorpay_order_id: serverRes.razorpay_order_id,
            razorpay_payment_id: `pay_test_${Date.now()}`,
            razorpay_signature: 'sig_test_valid',
          });
          setStep(4);
          setLoading(false);
          if (onOrderSuccess) onOrderSuccess(serverRes);
        }, 1200);
      }
    } catch (err) {
      setPaymentError(err.message || 'Order process failed.');
      setLoading(false);
    }
  };

  return (
    <aside className="purchase-summary-panel">
      <div className="panel-header">
        <h3>PURCHASE SUMMARY</h3>
        {step < 4 && (
          <button className="text-link-btn" onClick={onResetSelection}>
            Change
          </button>
        )}
      </div>

      <div className="panel-body">
        {/* STEP 1: PRODUCT REVIEW & QUANTITY */}
        {step === 1 && (
          <div className="panel-step">
            <div className="selected-product-card">
              <img src={imgSrc} alt={selectedProduct.name} className="product-thumb" onError={() => setImgSrc(DEFAULT_FALLBACK_IMAGE)} />
              <div>
                <span className="product-sku">{selectedProduct.sku}</span>
                <h4 className="product-name">{selectedProduct.name}</h4>
                <div className="product-price">₹{unitPrice.toLocaleString()}</div>
                <span className={`stock-badge ${selectedProduct.stock > 3 ? 'in-stock' : 'low-stock'}`}>
                  {selectedProduct.stock > 3 ? `${selectedProduct.stock} available` : `Only ${selectedProduct.stock} left`}
                </span>
              </div>
            </div>

            <div className="qty-row">
              <label>Quantity:</label>
              <div className="panel-qty-controls">
                <button type="button" className="qty-btn" disabled={quantity <= 1} onClick={() => handleQtyChange(-1)}>
                  <Minus size={12} />
                </button>
                <span className="qty-num">{quantity}</span>
                <button type="button" className="qty-btn" disabled={quantity >= selectedProduct.stock} onClick={() => handleQtyChange(1)}>
                  <Plus size={12} />
                </button>
              </div>
            </div>

            <div className="panel-price-breakdown">
              <div className="breakdown-row">
                <span>Subtotal ({quantity}x)</span>
                <span>₹{subtotal.toLocaleString()}</span>
              </div>
              <div className="breakdown-row">
                <span>Shipping Fee</span>
                <span style={{ color: 'var(--accent-success)', fontWeight: 600 }}>FREE (₹0)</span>
              </div>
              <div className="breakdown-divider" />
              <div className="breakdown-row total">
                <span>TOTAL</span>
                <strong>₹{totalAmount.toLocaleString()}</strong>
              </div>
            </div>

            {paymentError && (
              <div className="error-alert" style={{ marginBottom: '12px' }}>
                <AlertCircle size={15} />
                <span>{paymentError}</span>
              </div>
            )}

            <button className="primary-action-btn" disabled={loading} onClick={handleContinueToShipping}>
              {loading ? (
                <>
                  <Loader2 size={16} className="spin-icon" />
                  <span>Verifying Stock...</span>
                </>
              ) : (
                <>
                  <span>Continue to Shipping</span>
                  <ArrowRight size={16} />
                </>
              )}
            </button>
          </div>
        )}

        {/* STEP 2: SHIPPING FORM */}
        {step === 2 && (
          <form onSubmit={handleShippingSubmit} className="panel-step">
            <h4 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-muted)' }}>Shipping Details</h4>

            <div className="form-group">
              <label>Full Name *</label>
              <input
                type="text"
                className={`form-input ${errors.fullName ? 'error' : ''}`}
                placeholder="Rahul Sharma"
                value={shipping.fullName}
                onChange={(e) => setShipping({ ...shipping, fullName: e.target.value })}
              />
              {errors.fullName && <span className="error-text">{errors.fullName}</span>}
            </div>

            <div className="form-group">
              <label>Phone Number *</label>
              <input
                type="tel"
                className={`form-input ${errors.phone ? 'error' : ''}`}
                placeholder="10-digit mobile number"
                maxLength={10}
                value={shipping.phone}
                onChange={(e) => setShipping({ ...shipping, phone: e.target.value })}
              />
              {errors.phone && <span className="error-text">{errors.phone}</span>}
            </div>

            <div className="form-group">
              <label>Address *</label>
              <input
                type="text"
                className={`form-input ${errors.address1 ? 'error' : ''}`}
                placeholder="Flat / Building / Street"
                value={shipping.address1}
                onChange={(e) => setShipping({ ...shipping, address1: e.target.value })}
              />
              {errors.address1 && <span className="error-text">{errors.address1}</span>}
            </div>

            <div className="form-row-2">
              <div className="form-group">
                <label>City *</label>
                <input
                  type="text"
                  className={`form-input ${errors.city ? 'error' : ''}`}
                  placeholder="City"
                  value={shipping.city}
                  onChange={(e) => setShipping({ ...shipping, city: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>PIN Code *</label>
                <input
                  type="text"
                  className={`form-input ${errors.pinCode ? 'error' : ''}`}
                  placeholder="6-digit PIN"
                  maxLength={6}
                  value={shipping.pinCode}
                  onChange={(e) => setShipping({ ...shipping, pinCode: e.target.value })}
                />
              </div>
            </div>

            <div className="form-group">
              <label>State *</label>
              <input
                type="text"
                className={`form-input ${errors.state ? 'error' : ''}`}
                placeholder="State"
                value={shipping.state}
                onChange={(e) => setShipping({ ...shipping, state: e.target.value })}
              />
            </div>

            <div className="button-row">
              <button type="button" className="secondary-btn" onClick={() => setStep(1)}>
                <ArrowLeft size={14} />
                <span>Back</span>
              </button>
              <button type="submit" className="primary-action-btn" style={{ flex: 1 }}>
                <span>Review Order</span>
              </button>
            </div>
          </form>
        )}

        {/* STEP 3: ORDER CREATION & PAYMENT TRIGGER */}
        {step === 3 && (
          <div className="panel-step">
            <div className="order-review-box">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h4 style={{ fontSize: '14px', fontWeight: 600 }}>{selectedProduct.name}</h4>
                <span style={{ fontSize: '11px', fontFamily: 'monospace', color: 'var(--text-dim)' }}>{selectedProduct.sku}</span>
              </div>

              <div className="review-calc">
                <span>{quantity}x @ ₹{unitPrice.toLocaleString()}</span>
                <strong>₹{subtotal.toLocaleString()}</strong>
              </div>

              <div className="review-address">
                <span className="box-title">Deliver To:</span>
                <div><strong>{shipping.fullName}</strong> ({shipping.phone})</div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                  {shipping.address1}, {shipping.city}, {shipping.state} - {shipping.pinCode}
                </div>
              </div>

              <div className="breakdown-divider" />
              <div className="breakdown-row total">
                <span>TOTAL AMOUNT</span>
                <strong>₹{totalAmount.toLocaleString()}</strong>
              </div>
            </div>

            {paymentError && (
              <div className="error-alert">
                <AlertCircle size={15} />
                <span>{paymentError}</span>
              </div>
            )}

            <div className="button-row">
              <button type="button" className="secondary-btn" onClick={() => setStep(2)}>
                <ArrowLeft size={14} />
                <span>Edit Address</span>
              </button>
              <button type="button" className="primary-action-btn" disabled={loading} onClick={handleProceedToPayment} style={{ flex: 1 }}>
                {loading ? (
                  <>
                    <Loader2 size={16} className="spin-icon" />
                    <span>Processing...</span>
                  </>
                ) : (
                  <>
                    <CreditCard size={16} />
                    <span>Pay ₹{totalAmount.toLocaleString()}</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* STEP 4: ORDER CONFIRMED SUCCESS */}
        {step === 4 && (
          <div className="panel-step center-text">
            <CheckCircle2 size={44} color="var(--accent-success)" style={{ margin: '0 auto 8px auto' }} />
            <h4 style={{ fontSize: '16px', fontWeight: 700, color: 'var(--accent-success)' }}>Order Confirmed!</h4>
            <span className="badge-paid">✓ Payment Successful</span>

            <div className="receipt-box">
              <div className="receipt-row">
                <span>Order ID</span>
                <strong style={{ fontFamily: 'monospace' }}>{orderResult?.order_id || 'ORD-839201'}</strong>
              </div>
              <div className="receipt-row">
                <span>Product</span>
                <span>{selectedProduct.name} (x{quantity})</span>
              </div>
              <div className="receipt-row">
                <span>Total Paid</span>
                <strong>₹{totalAmount.toLocaleString()}</strong>
              </div>
              <div className="receipt-row">
                <span>Status</span>
                <span style={{ color: 'var(--accent-success)', fontWeight: 600 }}>PAID</span>
              </div>
            </div>

            <button className="primary-action-btn" onClick={onResetSelection} style={{ marginTop: '12px' }}>
              <RefreshCw size={14} />
              <span>Start New Purchase</span>
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
