'use strict';

// ============================================================
// Messages
// ============================================================

let msgTabInited  = false;
let currentMessage = null;

function showMsgPane(name) {
  ['inbox', 'detail', 'compose'].forEach(p =>
    el(`msg-${p}-pane`).style.display = (p === name ? '' : 'none')
  );
}

function initMessagesTab() {
  if (msgTabInited) return;
  msgTabInited = true;

  el('msg-btn-compose').addEventListener('click', () => showCompose());
  el('msg-btn-cancel-compose').addEventListener('click', () => showMsgPane('inbox'));
  el('msg-btn-back').addEventListener('click', () => {
    currentMessage = null;
    el('msg-reply-section').style.display = 'none';
    loadInbox();
    showMsgPane('inbox');
  });
  el('msg-btn-delete').addEventListener('click', deleteCurrentMessage);
  el('msg-send-btn').addEventListener('click', sendMessage);
  el('msg-reply-send').addEventListener('click', sendReply);

  loadInbox();
}

async function loadInbox() {
  el('msg-auth-warning').style.display = 'none';
  el('msg-inbox-list').innerHTML = '';
  try {
    const data = await apiFetch('/api/messages');
    renderInbox(data.data || []);
    refreshUnreadBadge();
  } catch (e) {
    const authErr = e.message.toLowerCase().includes('auth') || e.message.includes('401');
    if (authErr) {
      el('msg-auth-warning').style.display = '';
    } else {
      el('msg-inbox-list').innerHTML = `<p class="placeholder-msg" style="color:var(--red)">Error: ${e.message}</p>`;
    }
  }
}

function renderInbox(messages) {
  if (!messages.length) {
    el('msg-inbox-list').innerHTML = '<p class="placeholder-msg">Your inbox is empty.</p>';
    return;
  }
  el('msg-inbox-list').innerHTML = messages.map(m => `
    <div class="msg-item ${m.read ? '' : 'unread'}" onclick="openMessage(${m.id})">
      <div class="msg-unread-dot"></div>
      <div class="msg-item-info">
        <div class="msg-item-from">${packEsc(m.sender_username || '')}</div>
        <div class="msg-item-subject">${packEsc(m.subject || '(no subject)')}</div>
      </div>
      <div class="msg-item-time">${formatDate(m.created_at)}</div>
    </div>`).join('');
}

window.openMessage = async function(messageId) {
  try {
    const data = await apiFetch(`/api/messages/${messageId}`);
    currentMessage = data.data;
    const m = currentMessage;
    el('msg-detail-body').innerHTML = `
      <div class="msg-detail-card">
        <div class="msg-detail-subject">${packEsc(m.subject || '(no subject)')}</div>
        <div class="msg-detail-meta">
          <span>From: <strong>${packEsc(m.sender_username || '')}</strong></span>
          <span>To: <strong>${packEsc(m.recipient_username || '')}</strong></span>
          <span>${formatDate(m.created_at)}</span>
        </div>
        <div class="msg-detail-body">${packEsc(m.body || '')}</div>
      </div>`;
    el('msg-reply-section').style.display = '';
    el('msg-reply-body').value = '';
    el('msg-reply-feedback').textContent = '';
    showMsgPane('detail');
    refreshUnreadBadge();
  } catch (e) {
    alert(`Error loading message: ${e.message}`);
  }
};

async function deleteCurrentMessage() {
  if (!currentMessage || !confirm('Delete this message?')) return;
  try {
    await apiFetch(`/api/messages/${currentMessage.id}`, { method: 'DELETE' });
    currentMessage = null;
    el('msg-reply-section').style.display = 'none';
    loadInbox();
    showMsgPane('inbox');
  } catch (e) {
    alert(`Error: ${e.message}`);
  }
}

function showCompose(toUsername = '', subject = '') {
  el('msg-to').value      = toUsername;
  el('msg-subject').value = subject;
  el('msg-body').value    = '';
  el('msg-send-feedback').textContent = '';
  showMsgPane('compose');
}

async function sendMessage() {
  const to      = el('msg-to').value.trim();
  const subject = el('msg-subject').value.trim();
  const body    = el('msg-body').value.trim();
  if (!to)   { showFeedback('msg-send-feedback', 'Recipient is required', true); return; }
  if (!body) { showFeedback('msg-send-feedback', 'Message body is required', true); return; }

  el('msg-send-btn').disabled    = true;
  el('msg-send-btn').textContent = 'Sending\u2026';
  try {
    await apiFetch('/api/messages', {
      method: 'POST', body: JSON.stringify({ to, subject, body }),
    });
    showFeedback('msg-send-feedback', 'Message sent!');
    setTimeout(() => { loadInbox(); showMsgPane('inbox'); }, 1200);
  } catch (e) {
    showFeedback('msg-send-feedback', `Error: ${e.message}`, true);
  } finally {
    el('msg-send-btn').disabled    = false;
    el('msg-send-btn').textContent = 'Send';
  }
}

async function sendReply() {
  if (!currentMessage) return;
  const body = el('msg-reply-body').value.trim();
  if (!body) { showFeedback('msg-reply-feedback', 'Reply cannot be empty', true); return; }

  el('msg-reply-send').disabled    = true;
  el('msg-reply-send').textContent = 'Sending\u2026';
  try {
    await apiFetch('/api/messages', {
      method: 'POST',
      body: JSON.stringify({
        to:      currentMessage.sender_username,
        subject: currentMessage.subject ? `Re: ${currentMessage.subject}` : '',
        body,
      }),
    });
    showFeedback('msg-reply-feedback', 'Reply sent!');
    el('msg-reply-body').value = '';
  } catch (e) {
    showFeedback('msg-reply-feedback', `Error: ${e.message}`, true);
  } finally {
    el('msg-reply-send').disabled    = false;
    el('msg-reply-send').textContent = 'Send Reply';
  }
}

async function refreshUnreadBadge() {
  try {
    const data  = await apiFetch('/api/messages/unread-count');
    const count = data.data?.count ?? 0;
    const badge = el('msg-unread-badge');
    if (count > 0) {
      badge.textContent  = count;
      badge.style.display = '';
    } else {
      badge.style.display = 'none';
    }
  } catch (_) {
    el('msg-unread-badge').style.display = 'none';
  }
}

// Poll unread badge every 60 s and check immediately on load
setInterval(refreshUnreadBadge, 60_000);
refreshUnreadBadge();
