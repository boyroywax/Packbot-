'use strict';

// ============================================================
// History Tab
// ============================================================

async function loadHistory() {
  try {
    const data = await apiFetch('/api/scans?limit=50');
    renderHistory(data.data || []);
  } catch (err) {
    el('history-list').innerHTML = `<p class="placeholder-msg" style="color:var(--red)">Error: ${err.message}</p>`;
  }
}

function renderHistory(items) {
  const list = el('history-list');
  if (items.length === 0) {
    list.innerHTML = '<p class="placeholder-msg">No scans yet.</p>';
    return;
  }

  list.innerHTML = items.map(item => `
    <div class="history-item">
      <img src="${item.image_small || ''}" alt="${item.name || 'Unknown'}" />
      <div class="h-info">
        <div class="h-name">${item.name || '(unknown)'}</div>
        <div class="h-meta">${item.set_name || ''} · #${item.number || ''} · ${item.method || ''}</div>
      </div>
      <div class="h-time">${formatDate(item.scanned_at)}</div>
    </div>
  `).join('');
}
