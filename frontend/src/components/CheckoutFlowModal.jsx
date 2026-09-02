import React, { useState } from 'react';
import { X, Plus, Minus, CheckCircle2, ShieldCheck, CreditCard, ArrowRight, ArrowLeft, AlertCircle, Loader2 } from 'lucide-react';
import { createOrderOnServer, verifyPaymentOnServer } from '../services/api';

const DEFAULT_FALLBACK_IMAGE = 'https://images.unsplash.com/photo-1560343776-97e7d202ff0e?w=800&auto=format&fit=crop&q=80';

export default function CheckoutFlowModal({ product, initialQuantity = 1, onClose, onOrderComplete }) {
  const [step, setStep] = useState(1); // 1: Qty, 2: Address, 3: Summary, 4: Paying/Processing, 5: Success
  const [quantity, setQuantity] = useState(initialQuantity);
  const [imgSrc, setImgSrc] = useState(product.image || DEFAULT_FALLBACK_IMAGE);

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

  const unitPrice = parseFloat(product.price);
  const subtotal = unitPrice * quantity;
  const shippingFee = 0;
  const totalAmount = subtotal + shippingFee;

  const handleQtyChange = (delta) => {
    const nextQty = quantity + delta;
    if (nextQty >= 1 && nextQty <= product.stock) {
      setQuantity(nextQty);
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

  const handleAddressSubmit = (e) => {
    e.preventDefault();
    if (validateAddressForm()) {
      setStep(3); // Proceed to Order Summary
    }
  };

  const handleProceedToPayment = async () => {
    setLoading(true);
    setPaymentError(null);

    try {
      // 1. Call server-side order creation
      const payload = {
        sku: product.sku,
        quantity: quantity,
        customer_name: shipping.fullName,
        customer_phone: shipping.phone,
        address_line1: shipping.address1,
        address_line2: shipping.address2,
        city: shipping.city,
        state: shipping.state,
        pin_code: shipping.pinCode,
      };

      const serverRes = await createOrderOnServer(payload);

      if (!serverRes || !serverRes.success) {
        throw new Error(serverRes?.detail || 'Failed to create order on server.');
      }

      setOrderResult(serverRes);
      setStep(4);

      // 2. Trigger Razorpay Checkout Modal if SDK is loaded
      if (window.Razorpay) {
        const options = {
          key: serverRes.razorpay_key_id || 'rzp_test_mockkey123',
          amount: Math.round(totalAmount * 100),
          currency: 'INR',
          name: 'Razorpay Agentic Store',
          description: `Order ${serverRes.order_id} - ${product.name}`,
          order_id: serverRes.razorpay_order_id,
          handler: async function (response) {
            // 3. Server-side payment verification
            try {
              const verifyRes = await verifyPaymentOnServer({
                order_id: serverRes.order_id,
                razorpay_order_id: response.razorpay_order_id || serverRes.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id || `pay_sim_${Date.now()}`,
                razorpay_signature: response.razorpay_signature || 'sig_simulated_valid',
              });

              if (verifyRes.success) {
                setStep(5); // Order Confirmed Success Screen
                if (onOrderComplete) onOrderComplete(serverRes);
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
          theme: {
            color: '#6366f1',
          },
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
          setStep(5);
          setLoading(false);
          if (onOrderComplete) onOrderComplete(serverRes);
        }, 1200);
      }
    } catch (err) {
      setPaymentError(err.message || 'Order creation failed.');
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="checkout-modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="checkout-modal-header">
          <div className="checkout-title">
            <ShieldCheck size={18} color="var(--accent-primary)" />
            <span>
              {step === 1 && 'Select Quantity'}
              {step === 2 && 'Shipping Address'}
              {step === 3 && 'Order Summary & Confirmation'}
              {step === 4 && 'Processing Payment'}
              {step === 5 && 'Order Confirmed'}
            </span>
          </div>

          <button className="icon-btn" onClick={onClose} style={{ padding: '4px', border: 'none' }}>
            <X size={18} />
          </button>
        </div>

        <div className="checkout-modal-body">
          {/* STEP 1: QUANTITY & REVIEW */}
          {step === 1 && (
            <div className="step-container">
              <div className="product-summary-row">
                <img
                  src={imgSrc}
                  alt={product.name}
                  className="summary-img"
                  onError={() => setImgSrc(DEFAULT_FALLBACK_IMAGE)}
                />
                <div style={{ flex: 1 }}>
                  <span className="summary-sku">{product.sku}</span>
                  <h3 className="summary-title">{product.name}</h3>
                  <div className="summary-price">₹{unitPrice.toLocaleString()}</div>
                  <div className={`stock-badge ${product.stock > 3 ? 'in-stock' : product.stock > 0 ? 'low-stock' : 'out-stock'}`}>
                    {product.stock > 3 ? `${product.stock} available` : product.stock > 0 ? `Only ${product.stock} left in stock!` : 'Out of Stock'}
                  </div>
                </div>
              </div>

              <div className="quantity-select-box">
                <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-muted)' }}>Quantity:</span>
                <div className="qty-controls">
                  <button
                    type="button"
                    className="qty-btn"
                    disabled={quantity <= 1}
                    onClick={() => handleQtyChange(-1)}
                  >
                    <Minus size={14} />
                  </button>
                  <span className="qty-num">{quantity}</span>
                  <button
                    type="button"
                    className="qty-btn"
                    disabled={quantity >= product.stock}
                    onClick={() => handleQtyChange(1)}
                  >
                    <Plus size={14} />
                  </button>
                </div>
              </div>

              <div className="price-calc-box">
                <div className="calc-row">
                  <span>Unit Price</span>
                  <span>₹{unitPrice.toLocaleString()}</span>
                </div>
                <div className="calc-row">
                  <span>Quantity</span>
                  <span>× {quantity}</span>
                </div>
                <div className="calc-row total">
                  <span>Subtotal</span>
                  <strong>₹{subtotal.toLocaleString()}</strong>
                </div>
              </div>

              <button className="primary-action-btn" onClick={() => setStep(2)}>
                <span>Continue to Shipping</span>
                <ArrowRight size={16} />
              </button>
            </div>
          )}

          {/* STEP 2: SHIPPING ADDRESS FORM */}
          {step === 2 && (
            <form onSubmit={handleAddressSubmit} className="step-container">
              <div className="form-grid">
                <div className="form-group">
                  <label>Full Name *</label>
                  <input
                    type="text"
                    className={`form-input ${errors.fullName ? 'error' : ''}`}
                    placeholder="e.g. Rahul Sharma"
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

                <div className="form-group full-width">
                  <label>Address Line 1 *</label>
                  <input
                    type="text"
                    className={`form-input ${errors.address1 ? 'error' : ''}`}
                    placeholder="Flat / House No., Building, Street"
                    value={shipping.address1}
                    onChange={(e) => setShipping({ ...shipping, address1: e.target.value })}
                  />
                  {errors.address1 && <span className="error-text">{errors.address1}</span>}
                </div>

                <div className="form-group full-width">
                  <label>Address Line 2 (Optional)</label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="Landmark, Area"
                    value={shipping.address2}
                    onChange={(e) => setShipping({ ...shipping, address2: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label>City *</label>
                  <input
                    type="text"
                    className={`form-input ${errors.city ? 'error' : ''}`}
                    placeholder="City"
                    value={shipping.city}
                    onChange={(e) => setShipping({ ...shipping, city: e.target.value })}
                  />
                  {errors.city && <span className="error-text">{errors.city}</span>}
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
                  {errors.state && <span className="error-text">{errors.state}</span>}
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
                  {errors.pinCode && <span className="error-text">{errors.pinCode}</span>}
                </div>
              </div>

              <div className="button-row">
                <button type="button" className="secondary-btn" onClick={() => setStep(1)}>
                  <ArrowLeft size={16} />
                  <span>Back</span>
                </button>
                <button type="submit" className="primary-action-btn" style={{ width: 'auto', flex: 1 }}>
                  <span>Review Order</span>
                  <ArrowRight size={16} />
                </button>
              </div>
            </form>
          )}

          {/* STEP 3: ORDER SUMMARY */}
          {step === 3 && (
            <div className="step-container">
              <div className="order-summary-card">
                <div style={{ display: 'flex', gap: '12px', alignItems: 'center', marginBottom: '12px' }}>
                  <img src={imgSrc} alt={product.name} className="summary-thumb" onError={() => setImgSrc(DEFAULT_FALLBACK_IMAGE)} />
                  <div>
                    <h4 style={{ fontSize: '14px', fontWeight: 600 }}>{product.name}</h4>
                    <span style={{ fontSize: '11px', color: 'var(--text-dim)', fontFamily: 'monospace' }}>SKU: {product.sku}</span>
                  </div>
                </div>

                <div className="summary-table">
                  <div className="sum-row">
                    <span>Item Price ({quantity}x)</span>
                    <span>₹{subtotal.toLocaleString()}</span>
                  </div>
                  <div className="sum-row">
                    <span>Shipping Fee</span>
                    <span style={{ color: 'var(--accent-success)', fontWeight: 600 }}>FREE (₹0)</span>
                  </div>
                  <div className="sum-divider" />
                  <div className="sum-row total">
                    <span>Total Amount</span>
                    <strong style={{ fontSize: '16px', color: 'var(--text-main)' }}>₹{totalAmount.toLocaleString()}</strong>
                  </div>
                </div>

                <div className="shipping-review-box">
                  <span className="box-title">Deliver To:</span>
                  <div><strong>{shipping.fullName}</strong> ({shipping.phone})</div>
                  <div style={{ color: 'var(--text-muted)' }}>
                    {shipping.address1}, {shipping.address2 ? shipping.address2 + ', ' : ''}{shipping.city}, {shipping.state} - {shipping.pinCode}
                  </div>
                </div>
              </div>

              {paymentError && (
                <div className="error-alert">
                  <AlertCircle size={16} />
                  <span>{paymentError}</span>
                </div>
              )}

              <div className="button-row">
                <button type="button" className="secondary-btn" onClick={() => setStep(2)}>
                  <ArrowLeft size={16} />
                  <span>Edit Address</span>
                </button>
                <button
                  type="button"
                  className="primary-action-btn"
                  disabled={loading}
                  onClick={handleProceedToPayment}
                  style={{ width: 'auto', flex: 1 }}
                >
                  {loading ? (
                    <>
                      <Loader2 size={16} className="spin-icon" />
                      <span>Creating Order...</span>
                    </>
                  ) : (
                    <>
                      <CreditCard size={16} />
                      <span>Proceed to Payment</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* STEP 4: PAYMENT PROCESSING */}
          {step === 4 && (
            <div className="step-container center-text">
              <Loader2 size={36} className="spin-icon" color="var(--accent-primary)" style={{ margin: '20px auto' }} />
              <h3 style={{ fontSize: '16px', fontWeight: 600 }}>Processing Payment via Razorpay...</h3>
              <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '8px' }}>
                Please complete payment in the Razorpay Checkout modal window.
              </p>
              {paymentError && (
                <div className="error-alert" style={{ marginTop: '16px' }}>
                  <AlertCircle size={16} />
                  <span>{paymentError}</span>
                </div>
              )}
            </div>
          )}

          {/* STEP 5: SUCCESS CONFIRMATION SCREEN */}
          {step === 5 && (
            <div className="step-container center-text">
              <CheckCircle2 size={48} color="var(--accent-success)" style={{ margin: '0 auto 12px auto' }} />
              <h3 style={{ fontSize: '18px', fontWeight: 700, color: 'var(--accent-success)' }}>Order Confirmed!</h3>
              <span className="badge-paid">✓ Payment Successful</span>

              <div className="order-receipt-box">
                <div className="receipt-row">
                  <span>Order ID</span>
                  <strong style={{ fontFamily: 'monospace' }}>{orderResult?.order_id || 'ORD-982143'}</strong>
                </div>
                <div className="receipt-row">
                  <span>Item</span>
                  <span>{product.name} (x{quantity})</span>
                </div>
                <div className="receipt-row">
                  <span>Total Amount Paid</span>
                  <strong>₹{totalAmount.toLocaleString()}</strong>
                </div>
                <div className="receipt-row">
                  <span>Status</span>
                  <span style={{ color: 'var(--accent-success)', fontWeight: 600 }}>PAID</span>
                </div>
              </div>

              <button className="primary-action-btn" onClick={onClose} style={{ marginTop: '16px' }}>
                <span>Done</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
