'use strict';

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
  ['scan', 'opening', 'review', 'history'].forEach(s =>
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

  // Wire history buttons
  el('pack-btn-history').addEventListener('click', loadPackHistory);
  el('pack-btn-back-to-scan').addEventListener('click', () => packShowStep('scan'));

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

// ============================================================
// Pack History
// ============================================================

async function loadPackHistory() {
  packShowStep('history');
  const container = el('pack-history-list');
  container.innerHTML = '<p class="placeholder-msg">Loading&hellip;</p>';
  try {
    const data = await apiFetch('/api/pack-sessions');
    renderPackHistory(data.data || []);
  } catch (e) {
    const authErr = e.message.toLowerCase().includes('auth') || e.message.includes('401');
    container.innerHTML = authErr
      ? '<p class="placeholder-msg">Sign in to view your pack history.</p>'
      : `<p class="placeholder-msg" style="color:var(--red)">Error: ${e.message}</p>`;
  }
}

function renderPackHistory(sessions) {
  const container = el('pack-history-list');
  if (!sessions.length) {
    container.innerHTML = '<p class="placeholder-msg">No pack openings yet. Start your first!</p>';
    return;
  }

  container.innerHTML = sessions.map(s => {
    const title = [s.pack_name, s.set_name].filter(Boolean).join(' \u2013 ') || `Session #${s.id}`;
    const date  = formatDate(s.started_at);
    const count = s.card_count ?? '?';
    const status = s.status || 'unknown';
    const barcodePart = s.barcode ? ` \u00b7 ${packEsc(s.barcode)}` : '';
    return `
      <div class="pack-history-item">
        <div class="phi-summary" onclick="togglePackHistoryItem(${s.id}, this)">
          <div class="phi-info">
            <div class="phi-title">${packEsc(title)}</div>
            <div class="phi-meta">${packEsc(date)}${barcodePart}</div>
          </div>
          <span class="phi-badge ${packEsc(status)}">${packEsc(status)}</span>
          <span class="phi-card-count">${count} card${count !== 1 ? 's' : ''}</span>
          <span class="phi-chevron">&#9660;</span>
        </div>
        <div id="phi-cards-${s.id}" class="phi-cards"></div>
      </div>`;
  }).join('');
}

async function togglePackHistoryItem(sessionId, summaryEl) {
  const cardsEl = el(`phi-cards-${sessionId}`);
  const chevron = summaryEl.querySelector('.phi-chevron');
  const isOpen  = cardsEl.classList.contains('open');

  if (isOpen) {
    cardsEl.classList.remove('open');
    chevron.classList.remove('open');
    return;
  }

  cardsEl.classList.add('open');
  chevron.classList.add('open');

  // Lazy-load cards on first expand
  if (cardsEl.dataset.loaded) return;
  cardsEl.dataset.loaded = '1';
  cardsEl.innerHTML = '<p style="font-size:0.82rem;color:var(--muted);padding:6px 0">Loading cards&hellip;</p>';

  try {
    const data  = await apiFetch(`/api/pack-sessions/${sessionId}`);
    const cards = data.data?.cards || [];
    if (!cards.length) {
      cardsEl.innerHTML = '<p style="font-size:0.82rem;color:var(--muted);padding:6px 0">No cards recorded for this session.</p>';
      return;
    }
    cardsEl.innerHTML = `<div class="phi-card-grid">${
      cards.map(c => `
        <div class="phi-card-tile">
          <img src="${packEsc(c.image_small || '')}" alt="${packEsc(c.card_name)}"
               onerror="this.style.display='none'" loading="lazy" />
          <div class="pct-name">${packEsc(c.card_name || 'Unknown')}</div>
          <div class="pct-meta">${packEsc(c.set_name || '')} · #${packEsc(c.number || '')}</div>
        </div>`).join('')
    }</div>`;
  } catch (e) {
    cardsEl.innerHTML = `<p style="font-size:0.82rem;color:var(--red);padding:6px 0">Error: ${e.message}</p>`;
  }
}

window.togglePackHistoryItem = togglePackHistoryItem;
