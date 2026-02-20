/* Packbot Frontend Application */
'use strict';

const API = '';  // Same origin

// ============================================================
// Utility helpers
// ============================================================

async function apiFetch(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.error || `HTTP ${res.status}`);
  return json;
}

function el(id) { return document.getElementById(id); }

function showFeedback(elId, msg, isError = false) {
  const elem = el(elId);
  elem.textContent = msg;
  elem.style.color = isError ? 'var(--red)' : 'var(--green)';
  setTimeout(() => { elem.textContent = ''; }, 4000);
}

function formatDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString();
}

function cardImageUrl(card) {
  return card.image_small || card.images?.small || '';
}

// ============================================================
// Tab navigation
// ============================================================

document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    el(`tab-${btn.dataset.tab}`).classList.add('active');

    if (btn.dataset.tab === 'collection') loadCollection();
    if (btn.dataset.tab === 'history') loadHistory();
    if (btn.dataset.tab === 'pack') initPackTab();
  });
});

// ============================================================
// Camera / Scanner
// ============================================================

let mediaStream = null;
let currentCard = null;

el('btn-start-camera').addEventListener('click', startCamera);
el('btn-stop-camera').addEventListener('click', stopCamera);
el('btn-capture').addEventListener('click', captureAndScan);
el('btn-manual-lookup').addEventListener('click', manualLookup);
el('btn-add-collection').addEventListener('click', addToCollection);

async function startCamera() {
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 960 } },
    });
    el('camera-feed').srcObject = mediaStream;
    el('btn-start-camera').disabled = true;
    el('btn-capture').disabled = false;
    el('btn-stop-camera').disabled = false;
  } catch (err) {
    alert(`Camera error: ${err.message}\n\nUse Manual Hints instead.`);
  }
}

function stopCamera() {
  if (mediaStream) {
    mediaStream.getTracks().forEach(t => t.stop());
    mediaStream = null;
  }
  el('camera-feed').srcObject = null;
  el('btn-start-camera').disabled = false;
  el('btn-capture').disabled = true;
  el('btn-stop-camera').disabled = true;
}

async function captureAndScan() {
  const video = el('camera-feed');
  const canvas = el('capture-canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);
  const dataUrl = canvas.toDataURL('image/jpeg', 0.85);

  const body = {
    image: dataUrl,
    pokemon_name: el('hint-name').value.trim(),
    set_code: el('hint-set').value.trim(),
    card_number: el('hint-number').value.trim(),
  };

  el('btn-capture').disabled = true;
  el('btn-capture').textContent = 'Scanning…';

  try {
    const result = await apiFetch('/api/scan/image', { method: 'POST', body: JSON.stringify(body) });
    displayScanResult(result);
  } catch (err) {
    showFeedback('add-feedback', `Scan failed: ${err.message}`, true);
  } finally {
    el('btn-capture').disabled = false;
    el('btn-capture').textContent = '📷 Capture';
  }
}

async function manualLookup() {
  const body = {
    image: '',
    pokemon_name: el('hint-name').value.trim(),
    set_code: el('hint-set').value.trim(),
    card_number: el('hint-number').value.trim(),
  };

  if (!body.pokemon_name && !(body.set_code && body.card_number)) {
    showFeedback('add-feedback', 'Enter a Pokémon name or set code + number', true);
    return;
  }

  el('btn-manual-lookup').disabled = true;
  el('btn-manual-lookup').textContent = 'Looking up…';

  try {
    const result = await apiFetch('/api/scan/image', { method: 'POST', body: JSON.stringify(body) });
    displayScanResult(result);
  } catch (err) {
    showFeedback('add-feedback', `Lookup failed: ${err.message}`, true);
  } finally {
    el('btn-manual-lookup').disabled = false;
    el('btn-manual-lookup').textContent = '🔍 Lookup by Hints';
  }
}

function displayScanResult(result) {
  const card = result.card;
  if (!card) {
    el('scan-result-placeholder').style.display = 'flex';
    el('scan-result-placeholder').querySelector('span').textContent = 'Card not found. Try adjusting hints.';
    el('scan-result').style.display = 'none';
    return;
  }

  currentCard = card;

  el('scan-result-placeholder').style.display = 'none';
  el('scan-result').style.display = 'block';

  el('result-img').src = card.images?.small || '';
  el('result-img').alt = card.name;
  el('result-name').textContent = card.name;
  el('result-set').textContent = `Set: ${card.set?.name || ''} (${card.set?.id || ''})`;
  el('result-number').textContent = `Number: ${card.number || ''}`;
  el('result-rarity').textContent = `Rarity: ${card.rarity || 'Unknown'}`;

  const pct = Math.round((result.confidence || 0) * 100);
  el('result-confidence').textContent = `${result.method} · ${pct}% confidence`;

  const candidates = result.candidates || [];
  if (candidates.length > 0) {
    el('candidates-section').style.display = 'block';
    const list = el('candidates-list');
    list.innerHTML = '';
    candidates.slice(0, 6).forEach(c => {
      const chip = document.createElement('span');
      chip.className = 'candidate-chip';
      chip.textContent = `${c.name} – ${c.set?.name || ''}`;
      chip.addEventListener('click', () => displayScanResult({ ...result, card: c, candidates: [] }));
      list.appendChild(chip);
    });
  } else {
    el('candidates-section').style.display = 'none';
  }

  el('add-feedback').textContent = '';
}

async function addToCollection() {
  if (!currentCard) {
    showFeedback('add-feedback', 'No card selected', true);
    return;
  }

  const body = {
    card_id: currentCard.id,
    condition: el('add-condition').value,
    foil: el('add-foil').checked,
    quantity: parseInt(el('add-qty').value, 10) || 1,
    notes: el('add-notes').value.trim(),
  };

  try {
    await apiFetch('/api/collection', { method: 'POST', body: JSON.stringify(body) });
    showFeedback('add-feedback', `${currentCard.name} added to collection!`);
  } catch (err) {
    showFeedback('add-feedback', `Error: ${err.message}`, true);
  }
}

// ============================================================
// Search Tab
// ============================================================

let searchPage = 1;
let lastQuery = '';

el('btn-search').addEventListener('click', () => { searchPage = 1; runSearch(); });
el('search-input').addEventListener('keydown', e => { if (e.key === 'Enter') { searchPage = 1; runSearch(); } });

async function runSearch() {
  const raw = el('search-input').value.trim();
  if (!raw) return;

  lastQuery = raw;

  // Detect if it's a raw TCG query (contains colons) or a name search
  const isQuery = raw.includes(':');
  const params = isQuery
    ? `q=${encodeURIComponent(raw)}&page=${searchPage}&page_size=24`
    : `name=${encodeURIComponent(raw)}&page=${searchPage}&page_size=24`;

  el('search-results').innerHTML = '<p class="placeholder-msg">Searching…</p>';
  el('search-pagination').innerHTML = '';

  try {
    const data = await apiFetch(`/api/cards/search?${params}`);
    renderCardGrid(data);
  } catch (err) {
    el('search-results').innerHTML = `<p class="placeholder-msg" style="color:var(--red)">Error: ${err.message}</p>`;
  }
}

function renderCardGrid(data) {
  const grid = el('search-results');
  const cards = data.data || [];
  if (cards.length === 0) {
    grid.innerHTML = '<p class="placeholder-msg">No cards found.</p>';
    return;
  }

  grid.innerHTML = '';
  cards.forEach(card => {
    const tile = document.createElement('div');
    tile.className = 'card-tile';
    tile.innerHTML = `
      <img src="${card.images?.small || ''}" alt="${card.name}" loading="lazy" />
      <div class="tile-name">${card.name}</div>
      <div class="tile-meta">${card.set?.name || ''} · #${card.number || ''}</div>
      <div class="tile-meta">${card.rarity || ''}</div>
    `;
    tile.addEventListener('click', () => openCardModal(card));
    grid.appendChild(tile);
  });

  // Pagination
  const total = data.totalCount || 0;
  const pageSize = 24;
  const totalPages = Math.ceil(total / pageSize);
  renderPagination('search-pagination', searchPage, totalPages, page => {
    searchPage = page;
    runSearch();
  });
}

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

// ============================================================
// Collection Tab
// ============================================================

let colPage = 1;

el('btn-col-filter').addEventListener('click', () => { colPage = 1; loadCollection(); });
el('col-search').addEventListener('keydown', e => { if (e.key === 'Enter') { colPage = 1; loadCollection(); } });

async function loadCollection() {
  const search = el('col-search').value.trim();
  const setId = el('col-set-filter').value.trim();
  const params = `search=${encodeURIComponent(search)}&set_id=${encodeURIComponent(setId)}&page=${colPage}&page_size=50`;

  try {
    const [data, statsData] = await Promise.all([
      apiFetch(`/api/collection?${params}`),
      apiFetch('/api/collection/stats'),
    ]);

    renderCollectionStats(statsData.data);
    renderCollectionTable(data);
  } catch (err) {
    el('collection-list').innerHTML = `<p class="placeholder-msg" style="color:var(--red)">Error: ${err.message}</p>`;
  }
}

function renderCollectionStats(stats) {
  el('collection-stats').innerHTML = `
    <span><strong>${stats.unique_cards ?? 0}</strong> unique cards</span>
    <span><strong>${stats.total_cards ?? 0}</strong> total copies</span>
    <span><strong>${stats.unique_sets ?? 0}</strong> sets</span>
  `;
}

function renderCollectionTable(data) {
  const items = data.items || [];
  const wrapper = el('collection-list');

  if (items.length === 0) {
    wrapper.innerHTML = '<p class="placeholder-msg">No cards match your filter.</p>';
    el('col-pagination').innerHTML = '';
    return;
  }

  let html = `
    <table>
      <thead>
        <tr>
          <th></th>
          <th>Name</th>
          <th>Set</th>
          <th>#</th>
          <th>Condition</th>
          <th>Foil</th>
          <th>Qty</th>
          <th>Added</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
  `;

  items.forEach(item => {
    html += `
      <tr>
        <td><img src="${item.image_small || ''}" alt="${item.name}" /></td>
        <td>${item.name}</td>
        <td>${item.set_name || item.set_id}</td>
        <td>${item.number}</td>
        <td>${item.condition}</td>
        <td>${item.foil ? '✓' : ''}</td>
        <td>${item.quantity}</td>
        <td>${formatDate(item.added_at)}</td>
        <td>
          <button class="btn-danger" data-id="${item.id}" onclick="removeCollectionEntry(${item.id})">Remove</button>
        </td>
      </tr>
    `;
  });

  html += '</tbody></table>';
  wrapper.innerHTML = html;

  const totalPages = Math.ceil(data.total / data.page_size);
  renderPagination('col-pagination', colPage, totalPages, page => {
    colPage = page;
    loadCollection();
  });
}

async function removeCollectionEntry(id) {
  if (!confirm('Remove this card from your collection?')) return;
  try {
    await apiFetch(`/api/collection/${id}`, { method: 'DELETE' });
    loadCollection();
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

// Expose globally for inline onclick
window.removeCollectionEntry = removeCollectionEntry;

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

// ============================================================
// Pagination helper
// ============================================================

function renderPagination(containerId, current, total, onPage) {
  const container = el(containerId);
  if (total <= 1) { container.innerHTML = ''; return; }

  let html = '';
  const start = Math.max(1, current - 2);
  const end = Math.min(total, current + 2);

  if (current > 1) html += `<button data-page="${current - 1}">&#8249; Prev</button>`;
  if (start > 1) html += `<button data-page="1">1</button>${start > 2 ? '<span>…</span>' : ''}`;

  for (let p = start; p <= end; p++) {
    html += `<button data-page="${p}" class="${p === current ? 'current' : ''}">${p}</button>`;
  }

  if (end < total) html += `${end < total - 1 ? '<span>…</span>' : ''}<button data-page="${total}">${total}</button>`;
  if (current < total) html += `<button data-page="${current + 1}">Next &#8250;</button>`;

  container.innerHTML = html;
  container.querySelectorAll('button[data-page]').forEach(btn => {
    btn.addEventListener('click', () => onPage(parseInt(btn.dataset.page, 10)));
  });
}

// ============================================================
// Pack Opening Wizard
// ============================================================

let packSession        = null;   // active session object from API
let packSessionCards   = [];     // locally-tracked session cards
let packCamStream      = null;   // MediaStream for barcode-scan camera (step 1)
let packOpenStream     = null;   // MediaStream for opening camera (step 2)
let packAutoInterval   = null;   // setInterval ID for auto-detect
let packLastCardId     = null;   // deduplication: last auto-detected card id
let packTabInited      = false;  // sets dropdown loaded once

function packEsc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function packShowStep(name) {
  ['scan', 'opening', 'review'].forEach(s =>
    el(`pack-step-${s}`).style.display = (s === name ? '' : 'none')
  );
}

// ---------- Init (lazy, runs once) ----------

async function initPackTab() {
  if (packTabInited) return;
  packTabInited = true;

  // Load sets into the dropdown
  try {
    const data = await apiFetch('/api/sets');
    const sets = data.data || [];
    const sel = el('pack-set-select');
    sets.slice(0, 300).forEach(set => {
      const opt = document.createElement('option');
      opt.value = set.id;
      opt.textContent = `${set.name} (${set.id})`;
      sel.appendChild(opt);
    });
  } catch (e) {
    el('pack-barcode-status').textContent = `Could not load sets: ${e.message}`;
  }

  // Wire step-1 buttons
  el('pack-btn-start-cam').addEventListener('click', packStartBarcodeCamera);
  el('pack-btn-stop-cam').addEventListener('click', packStopBarcodeCamera);
  el('pack-btn-scan-bar').addEventListener('click', packScanBarcode);
  el('pack-btn-start-session').addEventListener('click', startPackSession);

  // Wire step-2 buttons
  el('pack-btn-open-cam').addEventListener('click', packStartOpenCamera);
  el('pack-btn-stop-open-cam').addEventListener('click', packStopOpenCamera);
  el('pack-btn-capture-now').addEventListener('click', capturePackFrame);
  el('pack-btn-toggle-auto').addEventListener('click', packToggleAuto);
  el('pack-btn-done-opening').addEventListener('click', doneOpening);
  el('pack-btn-manual-add').addEventListener('click', manualAddToSession);
  el('pack-manual-number').addEventListener('keydown', e => {
    if (e.key === 'Enter') manualAddToSession();
  });

  // Wire step-3 buttons
  el('pack-complete-btn').addEventListener('click', completePackSession);
  el('pack-reset-btn').addEventListener('click', resetPackOpening);
}

// ---------- Step 1: barcode camera ----------

async function packStartBarcodeCamera() {
  try {
    packCamStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment', width: { ideal: 1280 } },
    });
    el('pack-cam').srcObject = packCamStream;
    el('pack-btn-start-cam').disabled = true;
    el('pack-btn-scan-bar').disabled = false;
    el('pack-btn-stop-cam').disabled = false;
  } catch (err) {
    el('pack-barcode-status').textContent = `Camera error: ${err.message}`;
  }
}

function packStopBarcodeCamera() {
  if (packCamStream) { packCamStream.getTracks().forEach(t => t.stop()); packCamStream = null; }
  el('pack-cam').srcObject = null;
  el('pack-btn-start-cam').disabled = false;
  el('pack-btn-scan-bar').disabled = true;
  el('pack-btn-stop-cam').disabled = true;
}

async function packScanBarcode() {
  const video = el('pack-cam');
  const canvas = el('pack-canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);
  const dataUrl = canvas.toDataURL('image/jpeg', 0.9);

  el('pack-barcode-status').textContent = 'Scanning…';

  // Try native BarcodeDetector first (Chromium)
  if ('BarcodeDetector' in window) {
    try {
      const bd = new BarcodeDetector({ formats: ['ean_13','upc_a','qr_code','ean_8','code_128','upc_e'] });
      const codes = await bd.detect(canvas);
      if (codes.length) {
        el('pack-barcode-value').value = codes[0].rawValue;
        el('pack-barcode-status').textContent = `✓ Detected (${codes[0].format}): ${codes[0].rawValue}`;
        return;
      }
    } catch (_) { /* unsupported format list – fall through */ }
  }

  // Fallback: backend pyzbar
  try {
    const result = await apiFetch('/api/packs/scan-barcode', {
      method: 'POST', body: JSON.stringify({ image: dataUrl }),
    });
    if (result.barcode) {
      el('pack-barcode-value').value = result.barcode;
      el('pack-barcode-status').textContent = `✓ Detected (${result.barcode_type}): ${result.barcode}`;
    } else {
      el('pack-barcode-status').textContent = 'No barcode detected – try again or enter manually.';
    }
  } catch (e) {
    el('pack-barcode-status').textContent = `Error: ${e.message}`;
  }
}

async function startPackSession() {
  const setEl  = el('pack-set-select');
  const setId  = setEl.value;
  const setName = setEl.options[setEl.selectedIndex]?.text || '';
  const barcode = el('pack-barcode-value').value.trim();
  const packName = el('pack-name-input').value.trim();

  el('pack-step1-error').textContent = '';
  el('pack-btn-start-session').disabled = true;
  el('pack-btn-start-session').textContent = 'Starting…';

  try {
    const res = await apiFetch('/api/pack-sessions', {
      method: 'POST',
      body: JSON.stringify({ barcode, set_id: setId, set_name: setName, pack_name: packName }),
    });
    packSession = res.data;
    packSessionCards = [];
    packLastCardId = null;

    const label = [packSession.pack_name, packSession.set_name].filter(Boolean).join(' – ')
      || `Session #${packSession.id}`;
    el('pack-session-info').textContent = `📦 ${label}`;

    packStopBarcodeCamera();
    packShowStep('opening');
    renderPackCardList();
  } catch (e) {
    el('pack-step1-error').textContent = `Error: ${e.message}`;
  } finally {
    el('pack-btn-start-session').disabled = false;
    el('pack-btn-start-session').textContent = 'Start Opening →';
  }
}

// ---------- Step 2: opening camera ----------

async function packStartOpenCamera() {
  try {
    packOpenStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment', width: { ideal: 1280 } },
    });
    el('pack-opening-feed').srcObject = packOpenStream;
    el('pack-btn-open-cam').disabled = true;
    el('pack-btn-capture-now').disabled = false;
    el('pack-btn-toggle-auto').disabled = false;
    el('pack-btn-stop-open-cam').disabled = false;
    el('pack-detect-status').textContent = 'Camera ready. Show a card.';
  } catch (err) {
    el('pack-detect-status').textContent = `Camera error: ${err.message}`;
  }
}

function packStopOpenCamera() {
  if (packAutoInterval) { clearInterval(packAutoInterval); packAutoInterval = null; }
  el('pack-btn-toggle-auto').textContent = '▶ Auto-Detect';
  if (packOpenStream) { packOpenStream.getTracks().forEach(t => t.stop()); packOpenStream = null; }
  el('pack-opening-feed').srcObject = null;
  el('pack-btn-open-cam').disabled = false;
  el('pack-btn-capture-now').disabled = true;
  el('pack-btn-toggle-auto').disabled = true;
  el('pack-btn-stop-open-cam').disabled = true;
  el('pack-detect-status').textContent = 'Camera stopped.';
}

function packToggleAuto() {
  if (packAutoInterval) {
    clearInterval(packAutoInterval);
    packAutoInterval = null;
    el('pack-btn-toggle-auto').textContent = '▶ Auto-Detect';
    el('pack-detect-status').textContent = 'Auto-detect paused.';
  } else {
    el('pack-btn-toggle-auto').textContent = '⏸ Pause';
    capturePackFrame();
    packAutoInterval = setInterval(capturePackFrame, 2200);
  }
}

async function capturePackFrame() {
  if (!packOpenStream || !packSession) return;
  const video = el('pack-opening-feed');
  const canvas = el('pack-opening-canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);
  const dataUrl = canvas.toDataURL('image/jpeg', 0.8);

  try {
    const result = await apiFetch(`/api/pack-sessions/${packSession.id}/scan`, {
      method: 'POST', body: JSON.stringify({ image: dataUrl }),
    });
    const card = result.card;
    if (card) {
      const pct = Math.round((result.confidence || 0) * 100);
      el('pack-detect-status').textContent = `Detected: ${card.name} (${pct}% confidence)`;
      el('pack-detect-status').className = 'pack-status-msg success';
      if (card.id !== packLastCardId) {
        packLastCardId = card.id;
        await autoAddCardToSession(card, result.confidence);
      }
    } else {
      el('pack-detect-status').textContent = 'No card detected…';
      el('pack-detect-status').className = 'pack-status-msg';
      packLastCardId = null;
    }
  } catch (e) {
    el('pack-detect-status').textContent = `Scan error: ${e.message}`;
    el('pack-detect-status').className = 'pack-status-msg error';
  }
}

async function autoAddCardToSession(card, confidence) {
  const entry = await addCardToSession({
    card_id:    card.id,
    card_name:  card.name,
    number:     card.number  || '',
    set_name:   card.set?.name || '',
    image_small: card.images?.small || '',
    rarity:     card.rarity  || '',
    confidence: confidence   || 1.0,
  });
  if (entry) packFlashToast(`✓ Added: ${card.name}`);
}

async function manualAddToSession() {
  const number = el('pack-manual-number').value.trim();
  if (!number || !packSession) return;
  const setId = packSession.set_id || '';

  el('pack-manual-status').textContent = 'Looking up…';
  el('pack-manual-status').className   = 'pack-status-msg';

  try {
    const result = await apiFetch('/api/scan/image', {
      method: 'POST',
      body: JSON.stringify({ image: '', set_code: setId, card_number: number }),
    });
    if (result.card) {
      const card = result.card;
      const entry = await addCardToSession({
        card_id:    card.id,
        card_name:  card.name,
        number:     card.number  || '',
        set_name:   card.set?.name || '',
        image_small: card.images?.small || '',
        rarity:     card.rarity  || '',
        confidence: result.confidence,
      });
      if (entry) {
        el('pack-manual-number').value = '';
        el('pack-manual-status').textContent = `Added: ${card.name}`;
        el('pack-manual-status').className   = 'pack-status-msg success';
      }
    } else {
      el('pack-manual-status').textContent = 'Card not found. Try a different number.';
      el('pack-manual-status').className   = 'pack-status-msg error';
    }
  } catch (e) {
    el('pack-manual-status').textContent = `Error: ${e.message}`;
    el('pack-manual-status').className   = 'pack-status-msg error';
  }
}

async function addCardToSession(payload) {
  if (!packSession) return null;
  try {
    const res = await apiFetch(`/api/pack-sessions/${packSession.id}/cards`, {
      method: 'POST', body: JSON.stringify(payload),
    });
    packSessionCards.push(res.data);
    renderPackCardList();
    return res.data;
  } catch (e) {
    console.error('addCardToSession failed:', e);
    return null;
  }
}

async function removePackCard(sessionCardId) {
  if (!packSession) return;
  try {
    await apiFetch(`/api/pack-sessions/${packSession.id}/cards/${sessionCardId}`, { method: 'DELETE' });
    packSessionCards = packSessionCards.filter(c => c.id !== sessionCardId);
    renderPackCardList();
  } catch (e) {
    console.error('removePackCard failed:', e);
  }
}

function renderPackCardList() {
  const list = el('pack-card-list');
  el('pack-card-count').textContent = packSessionCards.length;

  if (!packSessionCards.length) {
    list.innerHTML = '<p class="placeholder-msg">No cards detected yet.</p>';
    return;
  }

  list.innerHTML = packSessionCards.map(c => `
    <div class="pack-card-entry">
      <img src="${packEsc(c.image_small || '')}" alt="${packEsc(c.card_name)}"
           onerror="this.style.display='none'" loading="lazy" />
      <div class="pack-card-info">
        <strong>${packEsc(c.card_name || 'Unknown')}</strong>
        <span>${packEsc(c.set_name)} &nbsp;#${packEsc(c.number)}</span>
        <span>${packEsc(c.rarity || '')}</span>
        ${c.confidence != null ? `<span class="pack-conf-badge">${Math.round(c.confidence * 100)}% match</span>` : ''}
      </div>
      <button class="btn-remove-card" onclick="removePackCard(${c.id})" title="Remove">&#xd7;</button>
    </div>`).join('');
}

function packFlashToast(msg) {
  const t = el('pack-toast');
  t.textContent = msg;
  t.style.opacity = '1';
  setTimeout(() => { t.style.opacity = '0'; }, 3000);
}

function doneOpening() {
  packStopOpenCamera();
  packShowStep('review');
  renderPackReview();
}

// ---------- Step 3: review & save ----------

function renderPackReview() {
  const count = packSessionCards.length;
  el('pack-review-count').textContent = `${count} card${count !== 1 ? 's' : ''} in this opening`;

  const grid = el('pack-review-grid');
  if (!count) {
    grid.innerHTML = '<p class="placeholder-msg">No cards in this session.</p>';
    return;
  }
  grid.innerHTML = packSessionCards.map(c => `
    <div class="pack-review-card">
      <img src="${packEsc(c.image_small || '')}" alt="${packEsc(c.card_name)}"
           onerror="this.style.display='none'" loading="lazy" />
      <div class="prc-name">${packEsc(c.card_name || 'Unknown')}</div>
      <div class="prc-meta">${packEsc(c.set_name)} · #${packEsc(c.number)}</div>
    </div>`).join('');
}

async function completePackSession() {
  if (!packSession) return;
  const addToCol = el('pack-add-to-col').checked;
  const condition = el('pack-review-condition').value;

  el('pack-complete-btn').disabled = true;
  el('pack-complete-btn').textContent = 'Saving…';
  el('pack-complete-msg').textContent = '';
  el('pack-complete-msg').className   = 'pack-status-msg';

  try {
    const result = await apiFetch(`/api/pack-sessions/${packSession.id}/complete`, {
      method: 'POST',
      body: JSON.stringify({ add_to_collection: addToCol, condition }),
    });
    const msg = addToCol
      ? `✓ Saved! ${result.cards_added} card(s) added to your collection.`
      : '✓ Opening session saved.';
    el('pack-complete-msg').textContent = msg;
    el('pack-complete-msg').className   = 'pack-status-msg success';
    packSession = null;   // session is now closed
  } catch (e) {
    el('pack-complete-msg').textContent = `Error: ${e.message}`;
    el('pack-complete-msg').className   = 'pack-status-msg error';
    el('pack-complete-btn').disabled = false;
    el('pack-complete-btn').textContent = 'Save to Collection';
  }
}

function resetPackOpening() {
  packSession      = null;
  packSessionCards = [];
  packLastCardId   = null;
  el('pack-barcode-value').value  = '';
  el('pack-name-input').value     = '';
  el('pack-barcode-status').textContent = '';
  el('pack-step1-error').textContent   = '';
  el('pack-complete-msg').textContent  = '';
  el('pack-complete-btn').disabled     = false;
  el('pack-complete-btn').textContent  = 'Save to Collection';
  packShowStep('scan');
}
