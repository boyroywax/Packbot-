'use strict';

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
