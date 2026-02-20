'use strict';

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
