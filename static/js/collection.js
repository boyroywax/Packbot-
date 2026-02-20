'use strict';

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
