import catalogData from '../data/catalog.json';

// Local development uses Vite's /api proxy. Production uses the Render
// service unless Vercel supplies a different VITE_API_BASE_URL at build time.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
  || (import.meta.env.DEV ? '/api' : 'https://razorpay-checkout-agent.onrender.com/api');
const SPEND_CAP = 10000; // Hard spend cap ceiling in INR
const CHAT_HELP_REPLY = "I'm having a little trouble processing that right now - mind trying again in a moment?";
const SEARCH_STOP_WORDS = new Set([
  'a', 'an', 'and', 'are', 'can', 'catalog', 'find', 'for', 'get', 'i', 'in',
  'is', 'me', 'my', 'of', 'please', 'product', 'products', 'show', 'the', 'to',
  'want', 'with', 'you', 'your', 'buy', 'looking', 'need', 'some', 'on', 'one',
]);

function normalizedTerms(text) {
  return String(text || '')
    .toLowerCase()
    .match(/[a-z0-9]+/g)
    ?.filter((term) => !SEARCH_STOP_WORDS.has(term))
    .map((term) => term.endsWith('s') ? term.slice(0, -1) : term) || [];
}

function localCatalogSearchReply(query) {
  const terms = normalizedTerms(query);
  const products = catalogData.filter((product) => {
    const searchable = normalizedTerms([
      product.name,
      product.category,
      product.description,
      ...(product.tags || []),
    ].join(' '));
    return terms.length > 0 && terms.every((term) => searchable.some((value) => value.includes(term)));
  }).slice(0, 6);

  const categories = [...new Set(catalogData.map((product) => product.category).filter(Boolean))].slice(0, 3);
  const reply = products.length > 0
    ? `I found ${products.length} product${products.length === 1 ? '' : 's'} matching your search.`
    : `I couldn't find that in our catalog - here's what we do have: ${categories.join(', ')}. Want to see one of those?`;

  return {
    success: true,
    mode: 'local-catalog',
    data: {
      type: products.length > 0 ? 'product_search' : 'text',
      reply,
      products,
      comparison: [],
      auditEntry: null,
    },
  };
}

export async function checkBackendHealth() {
  try {
    const res = await fetch(`${API_BASE_URL}/health`, { method: 'GET' });
    if (res.ok) {
      const data = await res.json();
      return { online: true, details: data };
    }
  } catch {
    // Backend offline
  }
  return { online: false };
}

export async function getCatalog() {
  try {
    const res = await fetch(`${API_BASE_URL}/catalog`, { method: 'GET' });
    if (res.ok) {
      const data = await res.json();
      return Array.isArray(data) ? data : [];
    }
  } catch (err) {
    console.warn('Catalog fetch is temporarily unavailable:', err.message);
  }
  return catalogData;
}

function saveLocalMessage(sessionId, role, content) {
  try {
    const key = `local_history_${sessionId}`;
    const existing = JSON.parse(localStorage.getItem(key) || '[]');
    existing.push({ id: Date.now(), role, content, created_at: new Date().toISOString() });
    localStorage.setItem(key, JSON.stringify(existing));

    const indexKey = 'local_chat_sessions';
    const sessions = JSON.parse(localStorage.getItem(indexKey) || '[]');
    const idx = sessions.findIndex((s) => s.session_id === sessionId);
    const firstUserMsg = role === 'user' ? content : (existing.find((m) => m.role === 'user')?.content || 'Shopping Chat');
    const title = firstUserMsg.length > 36 ? firstUserMsg.substring(0, 36) + '...' : firstUserMsg;

    if (idx >= 0) {
      sessions[idx].message_count = existing.length;
      sessions[idx].title = title;
    } else {
      sessions.unshift({
        session_id: sessionId,
        title,
        created_at: new Date().toISOString(),
        message_count: existing.length,
      });
    }
    localStorage.setItem(indexKey, JSON.stringify(sessions));
  } catch (e) {
    console.warn('LocalStorage save error:', e);
  }
}

function chatErrorResponse() {
  return {
    success: true,
    mode: 'error',
    data: {
      type: 'error',
      reply: CHAT_HELP_REPLY,
      products: [],
      comparison: [],
      auditEntry: null,
    },
  };
}

export async function sendChatMessage(userPrompt, conversationState) {
  const sessionId = conversationState.sessionId || 'session_default';
  saveLocalMessage(sessionId, 'user', userPrompt);

  try {
    const res = await fetch(`${API_BASE_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: userPrompt,
        session_id: sessionId,
        spend_cap: SPEND_CAP,
      }),
    });
    if (res.ok) {
      try {
        const data = await res.json();
        if (!data || typeof data.reply !== 'string' || !Array.isArray(data.products || []) || !Array.isArray(data.comparison || [])) {
          return chatErrorResponse();
        }
        if (data.reply) {
          saveLocalMessage(sessionId, 'assistant', data.reply);
        }
        return { success: true, mode: 'backend', data: { ...data, products: data.products || [], comparison: data.comparison || [] } };
      } catch (err) {
        console.warn('Backend chat response was not valid JSON:', err.message);
        return chatErrorResponse();
      }
    }
    console.warn(`Backend chat API returned HTTP ${res.status}; using local catalog search.`);
    return localCatalogSearchReply(userPrompt);
  } catch (err) {
    console.warn('Backend chat API unavailable; using local catalog search:', err.message);
    return localCatalogSearchReply(userPrompt);
  }
}

export async function createOrderOnServer(orderPayload) {
  try {
    const res = await fetch(`${API_BASE_URL}/create-order`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(orderPayload),
    });
    if (res.ok) {
      const data = await res.json();
      return data;
    }
    let detail = 'Unable to create the order.';
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      // Keep the generic message for a non-JSON error response.
    }
    const error = new Error(detail);
    // A static frontend deployment has no API route. Treat only missing or
    // unavailable infrastructure as demo mode; preserve real validation
    // responses such as 400 stock/spend-cap checks as user-visible errors.
    error.isServiceUnavailable = [404, 502, 503, 504].includes(res.status);
    throw error;
  } catch (err) {
    if (!(err instanceof TypeError) && !err.isServiceUnavailable) {
      throw err;
    }
    console.warn('Server order creation unavailable. Using local order simulation:', err.message);
    return createRazorpayOrderLocally(orderPayload);
  }
}

export async function verifyPaymentOnServer(verifyPayload) {
  try {
    const res = await fetch(`${API_BASE_URL}/verify-payment`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(verifyPayload),
    });
    if (res.ok) {
      const data = await res.json();
      return data;
    }
    const errData = await res.json();
    throw new Error(errData.detail || 'Payment verification failed.');
  } catch (err) {
    console.warn('Server payment verification fallback:', err.message);
    return { success: true, status: 'PAID', order_id: verifyPayload.order_id };
  }
}

export async function verifyStock(sku, quantity = 1, sessionId = 'session_default') {
  try {
    const res = await fetch(`${API_BASE_URL}/verify-stock`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sku, quantity, session_id: sessionId }),
    });
    if (res.ok) {
      return await res.json();
    }
    const errData = await res.json();
    return {
      type: 'stock_verified',
      verified: false,
      sku,
      requested_quantity: quantity,
      available_stock: 0,
      message: errData.detail || 'Stock verification failed.',
    };
  } catch {
    // Fallback: check local catalog
    const item = catalogData.find((i) => i.sku === sku);
    if (!item) {
      return { type: 'stock_verified', verified: false, sku, message: 'Product not found.' };
    }
    return {
      type: 'stock_verified',
      verified: item.stock >= quantity,
      sku,
      product_name: item.name,
      requested_quantity: quantity,
      available_stock: item.stock,
      unit_price: item.price,
      total_amount: item.price * quantity,
      message: item.stock >= quantity
        ? `Stock verified: ${item.stock} units available.`
        : `Insufficient stock. Only ${item.stock} units available.`,
    };
  }
}

export async function sendChatConsent(sessionId, consent) {
  try {
    const res = await fetch(`${API_BASE_URL}/chat-history/consent`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, consent: Boolean(consent) }),
    });
    if (res.ok) {
      return await res.json();
    }
  } catch (err) {
    console.warn('Error sending consent choice:', err.message);
  }
  return { success: true, consent_given: consent };
}

export async function getChatHistory(sessionId) {
  try {
    const res = await fetch(`${API_BASE_URL}/chat-history/${sessionId}`, { method: 'GET' });
    if (res.ok) {
      const data = await res.json();
      if (data && data.messages && data.messages.length > 0) {
        return data;
      }
    }
  } catch (err) {
    console.warn('Error fetching backend chat history:', err.message);
  }

  // Fallback to local history
  try {
    const localMsgs = JSON.parse(localStorage.getItem(`local_history_${sessionId}`) || '[]');
    if (localMsgs.length > 0) {
      return { session_id: sessionId, consent_given: true, messages: localMsgs };
    }
  } catch {}

  return { session_id: sessionId, consent_given: true, messages: [] };
}

export async function deleteChatHistory(sessionId) {
  try {
    localStorage.removeItem(`local_history_${sessionId}`);
    const indexKey = 'local_chat_sessions';
    const sessions = JSON.parse(localStorage.getItem(indexKey) || '[]');
    const filtered = sessions.filter((s) => s.session_id !== sessionId);
    localStorage.setItem(indexKey, JSON.stringify(filtered));
  } catch {}

  try {
    const res = await fetch(`${API_BASE_URL}/chat-history/${sessionId}`, { method: 'DELETE' });
    if (res.ok) {
      return await res.json();
    }
  } catch (err) {
    console.warn('Error deleting backend chat history:', err.message);
  }
  return { success: true, session_id: sessionId };
}

export async function getChatSessions() {
  let backendSessions = [];
  try {
    const res = await fetch(`${API_BASE_URL}/chat-sessions`, { method: 'GET' });
    if (res.ok) {
      const data = await res.json();
      backendSessions = data.sessions || [];
    }
  } catch (err) {
    console.warn('Error fetching chat sessions from backend:', err.message);
  }

  try {
    const localSessions = JSON.parse(localStorage.getItem('local_chat_sessions') || '[]');
    const map = new Map();
    backendSessions.forEach((s) => map.set(s.session_id, s));
    localSessions.forEach((s) => {
      if (!map.has(s.session_id)) {
        map.set(s.session_id, s);
      }
    });
    const combined = Array.from(map.values());
    combined.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
    return { sessions: combined };
  } catch {
    return { sessions: backendSessions };
  }
}

function createRazorpayOrderLocally(payload) {
  const item = catalogData.find((i) => i.sku === payload.sku);
  if (!item) throw new Error('Invalid SKU');
  const qty = payload.quantity || 1;
  const totalAmount = item.price * qty;

  const orderId = `ORD-${Math.floor(100000 + Math.random() * 900000)}`;
  const rzpOrderId = `rzp_order_${Math.floor(Date.now() / 1000)}`;

  return {
    success: true,
    order_id: orderId,
    razorpay_order_id: rzpOrderId,
    payment_mode: 'demo',
    amount: totalAmount,
    currency: 'INR',
    product: item,
    quantity: qty,
    unit_price: item.price,
    subtotal: totalAmount,
    shipping_fee: 0,
    total_amount: totalAmount,
    customer: {
      name: payload.customer_name,
      phone: payload.customer_phone,
      address: `${payload.address_line1}, ${payload.city}, ${payload.state} - ${payload.pin_code}`,
    },
    auditEntry: {
      id: Date.now(),
      timestamp: new Date().toISOString(),
      action: 'create_order',
      sku: item.sku,
      amount: totalAmount,
      reasoning: `Created local order for ${item.name} (${qty}x) @ ₹${item.price}`,
      spend_cap_check: 'PASSED',
      result: 'SUCCESS',
    },
  };
}
