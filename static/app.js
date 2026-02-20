/* Packbot Frontend Application – Tab navigation & initialization */
'use strict';

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
    if (btn.dataset.tab === 'trades') loadTradeMatches();
    if (btn.dataset.tab === 'messages') initMessagesTab();
  });
});
