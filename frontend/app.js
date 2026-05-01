const BACKEND_URL = 'https://saucer-backend-987132498395.us-central1.run.app';
const ALLOWED_EMAILS = ['dcjohnston1@gmail.com', 'emily.osteen.johnston@gmail.com'];

let currentUser = null;
let conversationHistory = [];

// ── Auth ──────────────────────────────────────────────────────────────────────

function handleGoogleSignIn(response) {
  const payload = JSON.parse(atob(response.credential.split('.')[1]));
  if (!ALLOWED_EMAILS.includes(payload.email)) {
    document.getElementById('login-error').classList.remove('hidden');
    return;
  }
  const user = { email: payload.email, name: payload.name || payload.email };
  localStorage.setItem('saucer_user', JSON.stringify(user));
  showMainApp(user);
}

function signOut() {
  localStorage.removeItem('saucer_user');
  currentUser = null;
  conversationHistory = [];
  document.getElementById('main-app').classList.add('hidden');
  document.getElementById('login-screen').classList.remove('hidden');
}

// ── Init ──────────────────────────────────────────────────────────────────────

function openDrawer() {
  document.getElementById('side-drawer').classList.add('drawer-open');
  document.getElementById('drawer-overlay').classList.remove('hidden');
}

function closeDrawer() {
  document.getElementById('side-drawer').classList.remove('drawer-open');
  document.getElementById('drawer-overlay').classList.add('hidden');
}

function openSendersScreen() {
  document.getElementById('senders-screen').classList.remove('hidden');
}

function closeSendersScreen() {
  document.getElementById('senders-screen').classList.add('hidden');
}

window.addEventListener('DOMContentLoaded', () => {
  // Wire up static elements
  document.getElementById('sign-out-btn').addEventListener('click', signOut);
  document.getElementById('add-sender-btn').addEventListener('click', addSender);
  document.getElementById('new-sender-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') addSender();
  });
  document.getElementById('send-btn').addEventListener('click', sendMessage);
  document.getElementById('msg-input').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });

  // Drawer
  document.getElementById('hamburger-btn').addEventListener('click', openDrawer);
  document.getElementById('drawer-overlay').addEventListener('click', closeDrawer);
  document.getElementById('menu-senders').addEventListener('click', () => {
    closeDrawer();
    openSendersScreen();
  });

  // Senders screen
  document.getElementById('senders-back-btn').addEventListener('click', closeSendersScreen);

  // Proposals screen
  document.getElementById('menu-proposals').addEventListener('click', () => {
    closeDrawer();
    openProposalsScreen();
  });
  document.getElementById('proposals-back-btn').addEventListener('click', closeProposalsScreen);

  // Check for existing session
  const stored = localStorage.getItem('saucer_user');
  if (stored) {
    try {
      const user = JSON.parse(stored);
      if (ALLOWED_EMAILS.includes(user.email)) {
        showMainApp(user);
        return;
      }
    } catch (e) {}
    localStorage.removeItem('saucer_user');
  }
});

function showMainApp(user) {
  currentUser = user;
  document.getElementById('login-screen').classList.add('hidden');
  document.getElementById('main-app').classList.remove('hidden');
  document.getElementById('hamburger-btn').classList.remove('hidden');
  document.getElementById('user-name').textContent = user.name;
  loadEmailFilters();
  loadHomeList();
  loadProposals();
}

// ── Email Filters ─────────────────────────────────────────────────────────────

async function loadEmailFilters() {
  try {
    const res = await fetch(`${BACKEND_URL}/email-filters`);
    const data = await res.json();
    renderSenders(data.filters || []);
    loadEmails(data.filters || []);
  } catch (err) {
    document.getElementById('emails-content').textContent = `Error loading filters: ${err.message}`;
  }
}

function renderSenders(filters) {
  const list = document.getElementById('senders-list');
  list.innerHTML = '';
  if (filters.length === 0) {
    list.innerHTML = '<p class="empty-state" style="padding: 4px 0 8px; font-size: 0.85rem;">No senders added yet.</p>';
    return;
  }
  filters.forEach(email => {
    const row = document.createElement('div');
    row.className = 'sender-row';
    row.innerHTML = `
      <span>${email}</span>
      <button class="remove-sender-btn" data-email="${email}">Remove</button>
    `;
    row.querySelector('.remove-sender-btn').addEventListener('click', () => removeSender(email));
    list.appendChild(row);
  });
}

async function addSender() {
  const input = document.getElementById('new-sender-input');
  const email = input.value.trim().toLowerCase();
  if (!email) return;
  try {
    await fetch(`${BACKEND_URL}/email-filters`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email })
    });
    input.value = '';
    loadEmailFilters();
  } catch (err) {
    alert(`Failed to add sender: ${err.message}`);
  }
}

async function removeSender(email) {
  try {
    await fetch(`${BACKEND_URL}/email-filters/${encodeURIComponent(email)}`, { method: 'DELETE' });
    loadEmailFilters();
  } catch (err) {
    alert(`Failed to remove sender: ${err.message}`);
  }
}

// ── Emails ────────────────────────────────────────────────────────────────────

function escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatEmailDate(dateStr) {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    const now = new Date();
    if (d.toDateString() === now.toDateString()) {
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  } catch { return ''; }
}

function buildEmailCard(email) {
  const bodyText = (email.body || email.snippet || '').trim();
  const preview = bodyText.slice(0, 220).replace(/\n+/g, ' ');
  const hasMore = bodyText.length > 220;

  const wrapper = document.createElement('div');
  wrapper.className = 'email-card-wrapper';
  wrapper.innerHTML = '<div class="swipe-dismiss-bg">Dismiss ✕</div>';

  const card = document.createElement('div');
  card.className = 'email-card';
  card.innerHTML = `
    <div class="email-meta">
      <span class="email-sender">${escapeHtml(email.sender)}</span>
      <span class="email-date">${escapeHtml(formatEmailDate(email.date))}</span>
    </div>
    <div class="email-subject">${escapeHtml(email.subject || '(No Subject)')}</div>
    <div class="email-preview">${escapeHtml(preview)}${hasMore ? '…' : ''}</div>
    ${hasMore ? `
      <div class="email-full-body hidden">${escapeHtml(bodyText)}</div>
      <button class="email-expand-btn">Show more ▾</button>
    ` : ''}
  `;

  if (hasMore) {
    card.querySelector('.email-expand-btn').addEventListener('click', () => {
      const body = card.querySelector('.email-full-body');
      const btn = card.querySelector('.email-expand-btn');
      const expanded = !body.classList.contains('hidden');
      body.classList.toggle('hidden');
      btn.textContent = expanded ? 'Show more ▾' : 'Show less ▴';
    });
  }

  if (email.attachments && email.attachments.length > 0) {
    const chips = document.createElement('div');
    chips.className = 'email-attachments';
    email.attachments.forEach(a => {
      const chip = document.createElement('span');
      chip.className = 'attachment-chip';
      chip.textContent = `📎 ${a.filename}`;

      if (a.extracted_text) {
        chip.classList.add('attachment-chip--expandable');
        const textEl = document.createElement('div');
        textEl.className = 'attachment-text hidden';
        textEl.textContent = a.extracted_text;
        chip.addEventListener('click', () => {
          const expanded = !textEl.classList.contains('hidden');
          textEl.classList.toggle('hidden');
          chip.classList.toggle('attachment-chip--open', !expanded);
        });
        chips.appendChild(chip);
        chips.appendChild(textEl);
      } else {
        chips.appendChild(chip);
      }
    });
    card.appendChild(chips);
  }

  wrapper.appendChild(card);
  addSwipeToDismiss(wrapper, card, email.id);
  return wrapper;
}

async function loadEmails(filters) {
  const emailsContent = document.getElementById('emails-content');
  if (!filters || filters.length === 0) {
    emailsContent.innerHTML = '<div class="empty-state">Add a sender via the menu to see their emails here.</div>';
    return;
  }
  emailsContent.innerHTML = '<div class="loading">Fetching emails...</div>';
  try {
    const res = await fetch(`${BACKEND_URL}/emails`);
    if (!res.ok) throw new Error('Failed to fetch emails');
    const data = await res.json();

    if (!data.emails || data.emails.length === 0) {
      emailsContent.innerHTML = '<div class="empty-state">No recent emails found.</div>';
      return;
    }
    emailsContent.innerHTML = '';
    data.emails.forEach(email => emailsContent.appendChild(buildEmailCard(email)));
  } catch (err) {
    emailsContent.textContent = `Error: ${err.message}`;
  }
}

// ── Proposals ────────────────────────────────────────────────────────────────

function openProposalsScreen() {
  document.getElementById('proposals-screen').classList.remove('hidden');
}

function closeProposalsScreen() {
  document.getElementById('proposals-screen').classList.add('hidden');
}

async function loadProposals() {
  try {
    const res = await fetch(`${BACKEND_URL}/proposals`);
    const data = await res.json();
    const proposals = data.proposals || [];

    const badge = document.getElementById('proposals-badge');
    if (proposals.length > 0) {
      badge.textContent = proposals.length;
      badge.classList.remove('hidden');
    } else {
      badge.classList.add('hidden');
    }

    const list = document.getElementById('proposals-list');
    if (!list) return;
    list.innerHTML = '';

    if (proposals.length === 0) {
      list.innerHTML = '<div class="empty-state">No suggestions right now.</div>';
      return;
    }

    proposals.forEach(p => {
      const card = document.createElement('div');
      card.className = 'proposal-card';
      card.innerHTML = `
        <div class="proposal-source">${escapeHtml(p.email_sender)} &mdash; ${escapeHtml(p.email_subject)}</div>
        <div class="proposal-title">💡 ${escapeHtml(p.title)}</div>
        ${p.notes ? `<div class="proposal-notes">${escapeHtml(p.notes)}</div>` : ''}
        <div class="proposal-actions">
          <button class="proposal-add-btn">Add to List</button>
          <button class="proposal-dismiss-btn">Dismiss</button>
        </div>
      `;
      card.querySelector('.proposal-add-btn').addEventListener('click', () => acceptProposal(p.id, card));
      card.querySelector('.proposal-dismiss-btn').addEventListener('click', () => dismissProposal(p.id, card));
      list.appendChild(card);
    });
  } catch (err) {
    console.error('Failed to load proposals:', err);
  }
}

// ── Shared List ───────────────────────────────────────────────────────────────

async function loadHomeList() {
  const homeDocContent = document.getElementById('home-doc-content');
  homeDocContent.innerHTML = '<div class="loading">Loading shared list...</div>';
  try {
    const res = await fetch(`${BACKEND_URL}/doc`);
    if (!res.ok) throw new Error('Failed to fetch doc');
    const data = await res.json();

    if (!data.tasks || data.tasks.length === 0) {
      homeDocContent.innerHTML = '<div class="empty-state">The list is currently empty.</div>';
      return;
    }
    homeDocContent.innerHTML = '';
    data.tasks.forEach(task => {
      const wrapper = document.createElement('div');
      wrapper.className = 'task-card-wrapper';
      wrapper.innerHTML = '<div class="swipe-done-bg">Done ✓</div>';

      const card = document.createElement('div');
      card.className = 'task-card';
      const dateHtml = task.due && task.due !== 'none' ? `<span class="task-due">📅 ${task.due}</span>` : '';
      card.innerHTML = `
        <div class="task-main">
          <div class="task-title">${task.title}</div>
          ${dateHtml}
        </div>
        ${task.notes ? `<div class="task-notes">${task.notes}</div>` : ''}
      `;

      wrapper.appendChild(card);
      homeDocContent.appendChild(wrapper);
      addSwipeToComplete(wrapper, card, task.title);
    });
  } catch (err) {
    homeDocContent.textContent = `Error: ${err.message}`;
  }
}

// ── Swipe to complete ─────────────────────────────────────────────────────────

function addSwipeToComplete(wrapper, card, title) {
  let startX = 0;
  let deltaX = 0;
  let dragging = false;

  card.addEventListener('touchstart', (e) => {
    startX = e.touches[0].clientX;
    dragging = true;
    card.style.transition = 'none';
  }, { passive: true });

  card.addEventListener('touchmove', (e) => {
    if (!dragging) return;
    deltaX = e.touches[0].clientX - startX;
    if (deltaX < 0) {
      card.style.transform = `translateX(${deltaX}px)`;
    }
  }, { passive: true });

  card.addEventListener('touchend', () => {
    if (!dragging) return;
    dragging = false;
    if (deltaX < -80) {
      card.style.transition = 'transform 0.3s ease, opacity 0.3s ease';
      card.style.transform = 'translateX(-100%)';
      card.style.opacity = '0';
      card.addEventListener('transitionend', () => wrapper.remove(), { once: true });
      completeTask(title);
    } else {
      card.style.transition = 'transform 0.25s ease';
      card.style.transform = 'translateX(0)';
    }
    deltaX = 0;
  });
}

async function completeTask(title) {
  try {
    await fetch(`${BACKEND_URL}/doc/task`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title })
    });
  } catch (err) {
    console.error('Failed to complete task:', err);
  }
}

// ── Swipe to dismiss (emails) ─────────────────────────────────────────────────

function addSwipeToDismiss(wrapper, card, emailId) {
  let startX = 0;
  let deltaX = 0;
  let dragging = false;

  card.addEventListener('touchstart', (e) => {
    startX = e.touches[0].clientX;
    dragging = true;
    card.style.transition = 'none';
  }, { passive: true });

  card.addEventListener('touchmove', (e) => {
    if (!dragging) return;
    deltaX = e.touches[0].clientX - startX;
    if (deltaX < 0) card.style.transform = `translateX(${deltaX}px)`;
  }, { passive: true });

  card.addEventListener('touchend', () => {
    if (!dragging) return;
    dragging = false;
    if (deltaX < -80) {
      card.style.transition = 'transform 0.3s ease, opacity 0.3s ease';
      card.style.transform = 'translateX(-100%)';
      card.style.opacity = '0';
      card.addEventListener('transitionend', () => wrapper.remove(), { once: true });
      dismissEmail(emailId);
    } else {
      card.style.transition = 'transform 0.25s ease';
      card.style.transform = 'translateX(0)';
    }
    deltaX = 0;
  });
}

async function dismissEmail(emailId) {
  try {
    await fetch(`${BACKEND_URL}/emails/${emailId}/dismiss`, { method: 'DELETE' });
  } catch (err) {
    console.error('Failed to dismiss email:', err);
  }
}

async function acceptProposal(proposalId, cardEl) {
  try {
    await fetch(`${BACKEND_URL}/proposals/${proposalId}/accept`, { method: 'POST' });
    cardEl.remove();
    loadProposals();
  } catch (err) {
    console.error('Failed to accept proposal:', err);
  }
}

async function dismissProposal(proposalId, cardEl) {
  try {
    await fetch(`${BACKEND_URL}/proposals/${proposalId}`, { method: 'DELETE' });
    cardEl.remove();
    loadProposals();
  } catch (err) {
    console.error('Failed to dismiss proposal:', err);
  }
}

// ── Chat ──────────────────────────────────────────────────────────────────────

async function sendMessage() {
  const msgInput = document.getElementById('msg-input');
  const sendBtn = document.getElementById('send-btn');
  const text = msgInput.value.trim();
  if (!text || !currentUser) return;

  appendMessage('user', text);
  msgInput.value = '';
  sendBtn.disabled = true;
  const typing = appendMessage('saucer', '…', true);

  try {
    const res = await fetch(`${BACKEND_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user: currentUser.name, message: text, history: conversationHistory })
    });
    if (!res.ok) throw new Error(`Server error ${res.status}`);
    const data = await res.json();
    typing.remove();
    appendMessage('saucer', data.reply);
    if (data.model) document.getElementById('model-info').textContent = `Powered by ${data.model}`;

    conversationHistory.push(
      { role: 'user', content: `${currentUser.name}: ${text}` },
      { role: 'assistant', content: data.reply }
    );
    if (conversationHistory.length > 20) conversationHistory.splice(0, 2);
  } catch (err) {
    typing.remove();
    appendMessage('saucer', `Something went wrong: ${err.message}`);
  } finally {
    sendBtn.disabled = false;
    msgInput.focus();
  }
}

function appendMessage(sender, text, isTyping = false) {
  const messages = document.getElementById('messages');
  const bubble = document.createElement('div');
  bubble.className = `bubble ${sender === 'saucer' ? 'saucer' : 'user'}`;
  if (isTyping) bubble.classList.add('typing');
  bubble.textContent = text;
  messages.appendChild(bubble);
  messages.scrollTop = messages.scrollHeight;
  return bubble;
}
