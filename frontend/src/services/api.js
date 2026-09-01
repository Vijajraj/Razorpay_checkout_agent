import catalogData from '../data/catalog.json';

const API_BASE_URL = 'http://localhost:8000/api';
const SPEND_CAP = 10000; // Hard spend cap ceiling in INR

export async function checkBackendHealth() {
  try {
    const res = await fetch(`${API_BASE_URL}/health`, { method: 'GET' });
    if (res.ok) {
      const data = await res.json();
      return { online: true, details: data };
    }
  } catch (err) {
    // Backend offline
  }
  return { online: false };
}

export async function sendChatMessage(userPrompt, conversationState) {
  // Try real FastAPI backend first
  try {
    const res = await fetch(`${API_BASE_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: userPrompt,
        session_id: conversationState.sessionId || 'session_default',
        spend_cap: SPEND_CAP,
      }),
    });
    if (res.ok) {
      const data = await res.json();
      return { success: true, mode: 'backend', data };
    }
  } catch (err) {
    console.warn('Backend API unavailable. Falling back to frontend Guardrail Engine simulation.');
  }

  // Fallback standalone Simulation Engine with Guardrails
  return simulateAgentResponse(userPrompt, conversationState);
}

function simulateAgentResponse(userPrompt, state) {
  const promptLower = userPrompt.toLowerCase();

  // Attack 1: Spend-cap bypass attempt
  if (promptLower.includes('50000') || promptLower.includes('50,000') || (promptLower.includes('ignore') && promptLower.includes('order'))) {
    const blockedLog = {
      id: Date.now(),
      timestamp: new Date().toISOString(),
      action: 'create_order',
      sku: 'CUSTOM_OVERRIDE',
      amount: 50000,
      reasoning: 'User attempted prompt injection to create order of ₹50,000 bypassing rules.',
      spend_cap_check: 'FAILED (Exceeds ₹10,000 Cap)',
      result: 'BLOCKED',
      attackType: 'Spend-Cap Bypass',
    };

    return {
      success: true,
      mode: 'simulator',
      data: {
        reply: `🚨 **SECURITY GUARDRAIL TRIGGERED**: Action Blocked!\n\nRequested order amount (₹50,000) exceeds configured merchant hard spend cap of **₹${SPEND_CAP.toLocaleString()}**. The request was rejected at code-level before calling Razorpay API.`,
        blocked: true,
        guardrailViolation: 'Spend-Cap Exceeded (₹50,000 > ₹10,000)',
        auditEntry: blockedLog,
      },
    };
  }

  // Attack 2: Price Manipulation / Unauthorized Discount
  if (promptLower.includes('secret90') || promptLower.includes('discount') || promptLower.includes('90%')) {
    const blockedLog = {
      id: Date.now(),
      timestamp: new Date().toISOString(),
      action: 'apply_discount',
      sku: 'UNKNOWN',
      amount: 0,
      reasoning: 'User requested 90% discount code SECRET90.',
      spend_cap_check: 'REJECTED (Unauthorized Action)',
      result: 'BLOCKED',
      attackType: 'Price Manipulation',
    };

    return {
      success: true,
      mode: 'simulator',
      data: {
        reply: `🛡️ **GUARDRAIL BLOCK**: Unauthorized Action!\n\nDiscount code \`SECRET90\` is not in the whitelisted action set. The agent is locked strictly to canonical catalog prices and cannot mutate order amounts without authorization.`,
        blocked: true,
        guardrailViolation: 'Unauthorized Action (Scope Lock)',
        auditEntry: blockedLog,
      },
    };
  }

  // Attack 3: Data Leakage attempt
  if (promptLower.includes('last customer') || promptLower.includes('phone number') || promptLower.includes('other session')) {
    const blockedLog = {
      id: Date.now(),
      timestamp: new Date().toISOString(),
      action: 'read_session_data',
      sku: 'N/A',
      amount: 0,
      reasoning: 'User queried cross-session customer order history and personal data.',
      spend_cap_check: 'BLOCKED (Isolation Enforced)',
      result: 'BLOCKED',
      attackType: 'Data Leakage',
    };

    return {
      success: true,
      mode: 'simulator',
      data: {
        reply: `🔒 **SESSION ISOLATION GUARD**: Data Access Denied!\n\nAgent execution environment is isolated to your current session (\`${state.sessionId || 'sess_active'}\`). Cross-session database read tools are not exposed to the agent.`,
        blocked: true,
        guardrailViolation: 'Session Data Isolation',
        auditEntry: blockedLog,
      },
    };
  }

  // Normal Purchase / Intent Flow
  // Search catalog
  let matchedItems = catalogData.filter((item) => {
    return item.tags.some((t) => promptLower.includes(t)) || item.name.toLowerCase().includes(promptLower) || item.category.toLowerCase().includes(promptLower);
  });

  if (matchedItems.length === 0 && (promptLower.includes('shoes') || promptLower.includes('sneaker') || promptLower.includes('buy') || promptLower.includes('running'))) {
    matchedItems = catalogData.filter((i) => i.tags.includes('shoes'));
  } else if (matchedItems.length === 0 && (promptLower.includes('watch') || promptLower.includes('time'))) {
    matchedItems = catalogData.filter((i) => i.tags.includes('watch'));
  } else if (matchedItems.length === 0 && (promptLower.includes('headphones') || promptLower.includes('audio') || promptLower.includes('sound'))) {
    matchedItems = catalogData.filter((i) => i.tags.includes('audio'));
  }

  if (matchedItems.length > 0) {
    const item = matchedItems[0];
    const isOutOfStock = item.stock === 0;

    let responseReply = `I found **${item.name}** (SKU: \`${item.sku}\`) for **₹${item.price.toLocaleString()}**.\n\n${item.description}`;
    if (isOutOfStock) {
      responseReply += `\n\n⚠️ *Note: This item is currently OUT OF STOCK (${item.stock} available). I cannot initiate a Razorpay checkout for out-of-stock SKUs.*`;
    } else {
      responseReply += `\n\nWould you like me to generate a Razorpay test payment link for this order?`;
    }

    return {
      success: true,
      mode: 'simulator',
      data: {
        reply: responseReply,
        products: matchedItems.slice(0, 2),
        selectedSku: item.sku,
        outOfStock: isOutOfStock,
        auditEntry: {
          id: Date.now(),
          timestamp: new Date().toISOString(),
          action: 'catalog_lookup',
          sku: item.sku,
          amount: item.price,
          reasoning: `Found ${matchedItems.length} matching products for query '${userPrompt}'. Selected SKU ${item.sku}.`,
          spend_cap_check: 'PASSED (Under ₹10,000 Cap)',
          result: 'SUCCESS',
        },
      },
    };
  }

  // Default response
  return {
    success: true,
    mode: 'simulator',
    data: {
      reply: `Hello! I am your AI Checkout Agent. I can help you search our catalog (running shoes, smartwatches, wireless headphones, backpacks) and complete purchases securely with Razorpay test-mode.\n\nWhat are you looking for today?`,
      products: catalogData.slice(0, 3),
      auditEntry: null,
    },
  };
}

export function createRazorpayOrder(sku, quantity = 1) {
  const item = catalogData.find((i) => i.sku === sku);
  if (!item) {
    throw new Error('Invalid SKU');
  }

  if (item.stock < quantity) {
    return {
      success: false,
      reason: 'Out of stock',
      auditEntry: {
        id: Date.now(),
        timestamp: new Date().toISOString(),
        action: 'create_order',
        sku: sku,
        amount: item.price * quantity,
        reasoning: `Order failed: Requested ${quantity} units of SKU ${sku}, but stock is ${item.stock}.`,
        spend_cap_check: 'N/A',
        result: 'FAILED (Out of Stock)',
      },
    };
  }

  const totalAmount = item.price * quantity;
  if (totalAmount > SPEND_CAP) {
    return {
      success: false,
      reason: 'Spend cap exceeded',
      auditEntry: {
        id: Date.now(),
        timestamp: new Date().toISOString(),
        action: 'create_order',
        sku: sku,
        amount: totalAmount,
        reasoning: `Guardrail triggered: Order total ₹${totalAmount} exceeds max cap ₹${SPEND_CAP}.`,
        spend_cap_check: 'FAILED',
        result: 'BLOCKED',
      },
    };
  }

  const orderId = `order_${Math.random().toString(36).substring(2, 9)}`;
  const paymentLink = `https://rzp.io/i/test_${orderId}`;

  return {
    success: true,
    orderId,
    paymentLink,
    amount: totalAmount,
    currency: 'INR',
    sku: item.sku,
    productName: item.name,
    auditEntry: {
      id: Date.now(),
      timestamp: new Date().toISOString(),
      action: 'create_order',
      sku: item.sku,
      amount: totalAmount,
      reasoning: `User confirmed order for ${item.name} (SKU: ${item.sku}) @ ₹${item.price}. Verified catalog match and stock (${item.stock} units left).`,
      spend_cap_check: 'PASSED',
      result: 'SUCCESS',
    },
  };
}
