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
