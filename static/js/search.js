'use strict';

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
