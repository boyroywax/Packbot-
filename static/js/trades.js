'use strict';

// ============================================================
// Trade Matches
// ============================================================

el('trades-refresh-btn').addEventListener('click', loadTradeMatches);

async function loadTradeMatches() {
  el('trades-auth-msg').style.display  = 'none';
  el('trades-content').style.display   = '';
  el('trades-you-have').innerHTML  = '<p class="placeholder-msg">Loading\u2026</p>';
  el('trades-they-have').innerHTML = '<p class="placeholder-msg">Loading\u2026</p>';
  try {
    const data = await apiFetch('/api/trade-matches');
    renderTradeMatches(data.data);
  } catch (e) {
    const authErr = e.message.toLowerCase().includes('auth') || e.message.includes('401');
    if (authErr) {
      el('trades-auth-msg').style.display = '';
      el('trades-content').style.display  = 'none';
    } else {
      el('trades-you-have').innerHTML  = `<p class="placeholder-msg" style="color:var(--red)">Error: ${e.message}</p>`;
      el('trades-they-have').innerHTML = '';
    }
  }
}

function renderTradeMatches(data) {
  renderTradeList('trades-you-have',  data.you_have_they_want || [], true);
  renderTradeList('trades-they-have', data.they_have_you_want || [], false);
}

function renderTradeList(containerId, items, isYouHave) {
  const container = el(containerId);
  if (!items.length) {
    container.innerHTML = '<p class="placeholder-msg" style="height:60px">No matches yet.</p>';
    return;
  }
  container.innerHTML = items.map(m => {
    const name     = packEsc(m.card_name || 'Unknown');
    const set      = packEsc(m.set_name  || m.set_id || '');
    const num      = m.number ? ` \u00b7 #${packEsc(m.number)}` : '';
    const username = packEsc(m.match_username || '');
    const img      = packEsc(m.image_small || '');
    const label    = isYouHave ? 'Wants your card' : 'Has this for trade';
    const cond     = (!isYouHave && m.condition)    ? `<span>${packEsc(m.condition)}</span>` : '';
    const price    = (!isYouHave && m.asking_price) ? `<span class="tmc-price">$${Number(m.asking_price).toFixed(2)}</span>` : '';
    const safeUser = username.replace(/'/g, "\\'");
    const safeName = name.replace(/'/g, "\\'");
    return `
      <div class="trade-match-card">
        <img src="${img}" alt="${name}" onerror="this.style.display='none'" loading="lazy" />
        <div class="tmc-info">
          <div class="tmc-name">${name}</div>
          <div class="tmc-meta">${set}${num}</div>
          ${cond}${price}
        </div>
        <div class="tmc-actions">
          <span class="tmc-user">${packEsc(label)}<br/>
            <a href="/u/${username}" target="_blank">@${username}</a>
          </span>
          <button class="btn-secondary" style="font-size:0.78rem;padding:4px 10px"
            onclick="startTradeMessage('${safeUser}','${safeName}')">
            \u2709 Message
          </button>
        </div>
      </div>`;
  }).join('');
}

window.startTradeMessage = function(username, cardName) {
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  const msgBtn = document.querySelector('[data-tab="messages"]');
  if (msgBtn) msgBtn.classList.add('active');
  el('tab-messages').classList.add('active');
  initMessagesTab();
  showCompose(username, `Trade request: ${cardName}`);
};
