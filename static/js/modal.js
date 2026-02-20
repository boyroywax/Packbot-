'use strict';

// ============================================================
// Card Modal
// ============================================================

async function openCardModal(card) {
  const modal = el('card-modal');
  const body = el('modal-body');

  body.innerHTML = `
    <img src="${card.images?.large || card.images?.small || ''}" alt="${card.name}" />
    <h2>${card.name}</h2>
    <div class="meta-row">Set: ${card.set?.name || ''} (${card.set?.id || ''})</div>
    <div class="meta-row">Number: ${card.number || ''}</div>
    <div class="meta-row">Rarity: ${card.rarity || 'Unknown'}</div>
    <div class="price-section">
      <h3>Market Prices</h3>
      <div id="modal-prices"><em style="color:var(--muted)">Loading prices…</em></div>
    </div>
    <div style="margin-top:16px">
      <button class="btn-primary" id="modal-add-btn">+ Add to Collection</button>
    </div>
  `;

  modal.style.display = 'flex';

  // Load prices async
  try {
    const prices = await apiFetch(`/api/cards/${card.id}/price`);
    renderModalPrices(prices.data);
  } catch {
    el('modal-prices').innerHTML = '<em style="color:var(--muted)">Price data unavailable.</em>';
  }

  // Add to collection from modal
  el('modal-add-btn').addEventListener('click', async () => {
    try {
      await apiFetch('/api/collection', {
        method: 'POST',
        body: JSON.stringify({ card_id: card.id, condition: 'NM', quantity: 1 }),
      });
      el('modal-add-btn').textContent = 'Added!';
      el('modal-add-btn').disabled = true;
    } catch (err) {
      alert(`Error: ${err.message}`);
    }
  });
}

function renderModalPrices(prices) {
  if (!prices || Object.keys(prices).length === 0) {
    el('modal-prices').innerHTML = '<em style="color:var(--muted)">No price data available.</em>';
    return;
  }

  const fmt = v => (v != null ? `$${Number(v).toFixed(2)}` : '—');

  let html = '<div class="price-grid">';
  Object.entries(prices).forEach(([condition, data]) => {
    if (data.source === 'cardmarket') {
      html += `
        <div class="price-item">
          <div class="p-label">Cardmarket (trend)</div>
          <div class="p-value">€${data.trend != null ? Number(data.trend).toFixed(2) : '—'}</div>
        </div>`;
    } else {
      html += `
        <div class="price-item">
          <div class="p-label">${condition} (market)</div>
          <div class="p-value">${fmt(data.market)}</div>
        </div>`;
    }
  });
  html += '</div>';
  el('modal-prices').innerHTML = html;
}

el('modal-close').addEventListener('click', () => { el('card-modal').style.display = 'none'; });
el('modal-backdrop').addEventListener('click', () => { el('card-modal').style.display = 'none'; });
