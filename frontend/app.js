const BACKEND_URL = 'https://saucer-backend-987132498395.us-central1.run.app';
const ALLOWED_EMAILS = ['dcjohnston1@gmail.com', 'emily.osteen.johnston@gmail.com'];
const GOOGLE_CLIENT_ID = '987132498395-o9ldqc2vqu1b36d7d8leh8d56f4eu83a.apps.googleusercontent.com';

let currentUser = null;
let conversationHistory = [];
let sessionPrevSeenAt = 0;

// ── Auth ──────────────────────────────────────────────────────────────────────

function initGoogleAuth() {
  google.accounts.id.initialize({ client_id: GOOGLE_CLIENT_ID, callback: handleGoogleSignIn, auto_select: true });

  // Skip prompt and button if we already have a valid stored session
  const stored = localStorage.getItem('saucer_user');
  if (stored) {
    try {
      const user = JSON.parse(stored);
      if (ALLOWED_EMAILS.includes(user.email)) return;
    } catch {}
  }

  renderGoogleButton();
  google.accounts.id.prompt();
}

function renderGoogleButton() {
  const el = document.querySelector('.g_id_signin');
  if (el) google.accounts.id.renderButton(el, { type: 'standard', theme: 'outline', size: 'large' });
}

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
  closeChat();
  localStorage.removeItem('saucer_user');
  currentUser = null;
  conversationHistory = [];
  document.getElementById('chat-btn').classList.add('hidden');
  document.getElementById('main-app').classList.add('hidden');
  document.getElementById('login-screen').classList.remove('hidden');
  if (window.google?.accounts?.id) {
    renderGoogleButton();
    google.accounts.id.prompt();
  }
}

function openChat() {
  document.getElementById('chat-panel').classList.add('chat-open');
  document.getElementById('chat-overlay').classList.remove('hidden');
  document.getElementById('msg-input').focus();
}

function closeChat() {
  document.getElementById('chat-panel').classList.remove('chat-open');
  document.getElementById('chat-overlay').classList.add('hidden');
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
  document.getElementById('chat-btn').addEventListener('click', openChat);
  document.getElementById('chat-overlay').addEventListener('click', closeChat);
  document.getElementById('chat-close-btn').addEventListener('click', closeChat);
  document.getElementById('add-sender-btn').addEventListener('click', addSender);
  document.getElementById('new-sender-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') addSender();
  });
  document.getElementById('add-keyword-btn').addEventListener('click', addKeyword);
  document.getElementById('new-keyword-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') addKeyword();
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

  // Members screen
  document.getElementById('menu-members').addEventListener('click', () => {
    closeDrawer();
    openMembersScreen();
  });
  document.getElementById('members-back-btn').addEventListener('click', closeMembersScreen);

  // List screen
  document.getElementById('menu-list').addEventListener('click', () => {
    closeDrawer();
    openListScreen();
  });
  document.getElementById('list-back-btn').addEventListener('click', closeListScreen);

  // Resync button inside Email Filters screen
  document.getElementById('resync-btn').addEventListener('click', () => resyncEmails());

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
  if (currentUser) return;
  currentUser = user;
  sessionPrevSeenAt = getLastSeenAt();
  setLastSeenAt(Date.now());
  document.getElementById('login-screen').classList.add('hidden');
  document.getElementById('main-app').classList.remove('hidden');
  document.getElementById('hamburger-btn').classList.remove('hidden');
  document.getElementById('chat-btn').classList.remove('hidden');
  document.getElementById('user-name').textContent = user.name;
  loadEmailFilters();
  loadKeywordFilters();
  loadProposals();
  initVoice();
}

function openMembersScreen() {
  const list = document.getElementById('members-list');
  list.innerHTML = '';
  ALLOWED_EMAILS.forEach(email => {
    const initial = email[0].toUpperCase();
    const isCurrent = currentUser && currentUser.email === email;
    const row = document.createElement('div');
    row.className = 'drawer-member-row' + (isCurrent ? ' drawer-member-row--active' : '');
    row.innerHTML = `
      <div class="drawer-member-avatar">${initial}</div>
      <span class="drawer-member-email">${email}</span>
      ${isCurrent ? '<span class="drawer-member-you">you</span>' : ''}
    `;
    list.appendChild(row);
  });
  document.getElementById('members-screen').classList.remove('hidden');
}

function closeMembersScreen() {
  document.getElementById('members-screen').classList.add('hidden');
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

async function loadKeywordFilters() {
  try {
    const res = await fetch(`${BACKEND_URL}/keyword-filters`);
    const data = await res.json();
    renderKeywords(data.keywords || []);
  } catch (err) {
    console.error('Failed to load keywords:', err);
  }
}

function renderKeywords(keywords) {
  const list = document.getElementById('keywords-list');
  list.innerHTML = '';
  if (keywords.length === 0) {
    list.innerHTML = '<p class="empty-state" style="padding: 4px 0 8px; font-size: 0.85rem;">No keywords added yet.</p>';
    return;
  }
  keywords.forEach(kw => {
    const row = document.createElement('div');
    row.className = 'sender-row';
    row.innerHTML = `
      <span>${escapeHtml(kw)}</span>
      <button class="remove-sender-btn" data-kw="${escapeHtml(kw)}">Remove</button>
    `;
    row.querySelector('.remove-sender-btn').addEventListener('click', () => removeKeyword(kw));
    list.appendChild(row);
  });
}

async function addKeyword() {
  const input = document.getElementById('new-keyword-input');
  const keyword = input.value.trim().toLowerCase();
  if (!keyword) return;
  try {
    await fetch(`${BACKEND_URL}/keyword-filters`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keyword })
    });
    input.value = '';
    loadKeywordFilters();
  } catch (err) {
    alert(`Failed to add keyword: ${err.message}`);
  }
}

async function removeKeyword(keyword) {
  try {
    await fetch(`${BACKEND_URL}/keyword-filters/${encodeURIComponent(keyword)}`, { method: 'DELETE' });
    loadKeywordFilters();
  } catch (err) {
    alert(`Failed to remove keyword: ${err.message}`);
  }
}

// ── Search highlight helpers ──────────────────────────────────────────────────

const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'BUTTON', 'MARK']);

function highlightSearchTerm(node, query) {
  if (node.nodeType === Node.TEXT_NODE) {
    const text = node.textContent;
    const idx = text.toLowerCase().indexOf(query);
    if (idx === -1) return;
    const before = document.createTextNode(text.slice(0, idx));
    const mark = document.createElement('mark');
    mark.className = 'search-highlight';
    mark.textContent = text.slice(idx, idx + query.length);
    const rest = document.createTextNode(text.slice(idx + query.length));
    node.parentNode.replaceChild(before, node);
    before.parentNode.insertBefore(mark, before.nextSibling);
    mark.parentNode.insertBefore(rest, mark.nextSibling);
    highlightSearchTerm(rest, query);
  } else if (node.nodeType === Node.ELEMENT_NODE && !SKIP_TAGS.has(node.tagName)) {
    Array.from(node.childNodes).forEach(child => highlightSearchTerm(child, query));
  }
}

function removeSearchHighlights(node) {
  node.querySelectorAll('mark.search-highlight').forEach(mark => {
    const parent = mark.parentNode;
    while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
    parent.removeChild(mark);
    parent.normalize();
  });
}

// ── Emails ────────────────────────────────────────────────────────────────────

function getLastSeenAt() {
  try { return parseInt(localStorage.getItem('saucer_last_seen_at') || '0'); }
  catch { return 0; }
}

function setLastSeenAt(ts) {
  try { localStorage.setItem('saucer_last_seen_at', String(ts)); } catch {}
}

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

function buildEmailCard(email, isNew = false) {
  const bodyText = (email.body || email.snippet || '').trim();
  const preview = bodyText.slice(0, 220).replace(/\n+/g, ' ');
  const hasMore = bodyText.length > 220;

  const wrapper = document.createElement('div');
  wrapper.className = 'email-card-wrapper';
  wrapper.innerHTML = '<div class="swipe-dismiss-bg">Dismiss ✕</div>';

  const card = document.createElement('div');
  card.className = 'email-card';
  const accountBadge = email.account ? `<span class="email-account-badge">${escapeHtml(email.account)}</span>` : '';
  const newTag = isNew ? '<span class="email-new-tag">new</span>' : '';
  card.innerHTML = `
    <div class="email-meta">
      <span class="email-sender">${escapeHtml(email.sender)}</span>
      <div class="email-meta-right-group">${newTag}<span class="email-date">${escapeHtml(formatEmailDate(email.date))}</span></div>
    </div>
    ${accountBadge}
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

async function resyncEmails() {
  const emailsContent = document.getElementById('emails-content');
  emailsContent.innerHTML = '<div class="loading">Syncing 90 days of history…</div>';
  try {
    const res = await fetch(`${BACKEND_URL}/emails/resync`, { method: 'POST' });
    if (!res.ok) throw new Error('Resync failed');
    const data = await res.json();
    emailsContent.innerHTML = '';
    if (!data.emails || data.emails.length === 0) {
      emailsContent.innerHTML = '<div class="empty-state">No emails found.</div>';
      return;
    }
    const emails = data.emails;
    emails.sort((a, b) => new Date(b.date) - new Date(a.date));
    emails.forEach(email => {
      const isNew = sessionPrevSeenAt > 0 && new Date(email.date).getTime() > sessionPrevSeenAt;
      emailsContent.appendChild(buildEmailCard(email, isNew));
    });
    wireSearchInput(emailsContent);
  } catch (err) {
    emailsContent.textContent = `Error: ${err.message}`;
  }
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
    const emails = data.emails;
    emails.sort((a, b) => new Date(b.date) - new Date(a.date));
    emails.forEach(email => {
      const isNew = sessionPrevSeenAt > 0 && new Date(email.date).getTime() > sessionPrevSeenAt;
      emailsContent.appendChild(buildEmailCard(email, isNew));
    });
    wireSearchInput(emailsContent);
  } catch (err) {
    emailsContent.textContent = `Error: ${err.message}`;
  }
}

function wireSearchInput(emailsContent) {
  const searchInput = document.getElementById('email-search');
  searchInput.value = '';
  searchInput.oninput = () => {
    const q = searchInput.value.trim().toLowerCase();
    emailsContent.querySelectorAll('.email-card-wrapper').forEach(wrapper => {
      const card = wrapper.querySelector('.email-card');
      removeSearchHighlights(card);
      if (!q) {
        wrapper.style.display = '';
        return;
      }
      if (!card.textContent.toLowerCase().includes(q)) {
        wrapper.style.display = 'none';
      } else {
        wrapper.style.display = '';
        highlightSearchTerm(card, q);
      }
    });
  };
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
      const wrapper = document.createElement('div');
      wrapper.className = 'proposal-card-wrapper';

      const bg = document.createElement('div');
      bg.className = 'swipe-assign-bg';
      ALLOWED_EMAILS.forEach(email => {
        const btn = document.createElement('div');
        btn.className = 'assign-avatar';
        btn.dataset.email = email;
        btn.textContent = email[0].toUpperCase();
        bg.appendChild(btn);
      });
      const bothBtn = document.createElement('div');
      bothBtn.className = 'assign-avatar assign-avatar--both';
      bothBtn.dataset.email = 'both';
      bothBtn.innerHTML = `<span>${ALLOWED_EMAILS[0][0].toUpperCase()}</span><span>${ALLOWED_EMAILS[1][0].toUpperCase()}</span>`;
      bg.appendChild(bothBtn);

      const card = document.createElement('div');
      card.className = 'proposal-card';
      card.innerHTML = `
        <div class="proposal-source">${escapeHtml(p.email_sender)} &mdash; ${escapeHtml(p.email_subject)}</div>
        <div class="proposal-title">💡 ${escapeHtml(p.title)}</div>
        ${p.notes ? `<div class="proposal-notes">${escapeHtml(p.notes)}</div>` : ''}
        <div class="proposal-actions">
          <button class="proposal-dismiss-btn">Dismiss</button>
        </div>
      `;
      card.querySelector('.proposal-dismiss-btn').addEventListener('click', () => dismissProposal(p.id, wrapper));

      wrapper.appendChild(bg);
      wrapper.appendChild(card);
      addSwipeToAssign(wrapper, card, p.id);
      list.appendChild(wrapper);
    });
  } catch (err) {
    console.error('Failed to load proposals:', err);
  }
}

// ── Shared List ───────────────────────────────────────────────────────────────

function openListScreen() {
  document.getElementById('list-screen').classList.remove('hidden');
  loadListScreen();
}

function closeListScreen() {
  document.getElementById('list-screen').classList.add('hidden');
}

async function loadListScreen() {
  const container = document.getElementById('list-screen-content');
  container.innerHTML = '<div class="loading">Loading shared list...</div>';
  try {
    const res = await fetch(`${BACKEND_URL}/doc`);
    if (!res.ok) throw new Error('Failed to fetch doc');
    const data = await res.json();

    if (!data.tasks || data.tasks.length === 0) {
      container.innerHTML = '<div class="empty-state">The list is currently empty.</div>';
      return;
    }
    container.innerHTML = '';
    data.tasks.forEach(task => {
      const wrapper = document.createElement('div');
      wrapper.className = 'task-card-wrapper';
      wrapper.innerHTML = '<div class="swipe-done-bg">Done ✓</div>';

      const card = document.createElement('div');
      card.className = 'task-card';
      const dateHtml = task.due && task.due !== 'none' ? `<span class="task-due">📅 ${task.due}</span>` : '';
      const assigneeHtml = task.assignee === 'both'
        ? `<div class="task-assignee-both"><div class="task-assignee task-assignee--${ALLOWED_EMAILS[0][0].toLowerCase()}">${ALLOWED_EMAILS[0][0].toUpperCase()}</div><div class="task-assignee task-assignee--${ALLOWED_EMAILS[1][0].toLowerCase()}">${ALLOWED_EMAILS[1][0].toUpperCase()}</div></div>`
        : task.assignee
          ? `<div class="task-assignee task-assignee--${task.assignee[0].toLowerCase()}">${task.assignee[0].toUpperCase()}</div>`
          : '';
      card.innerHTML = `
        <div class="task-main">
          <div class="task-title">${escapeHtml(task.title)}</div>
          <div class="task-meta-right">${dateHtml}${assigneeHtml}</div>
        </div>
        ${task.notes ? `<div class="task-notes">${escapeHtml(task.notes)}</div>` : ''}
      `;

      wrapper.appendChild(card);
      container.appendChild(wrapper);
      addSwipeToComplete(wrapper, card, task.title);
    });
  } catch (err) {
    container.textContent = `Error: ${err.message}`;
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

function addSwipeToAssign(wrapper, card, proposalId) {
  let startX = 0;
  let deltaX = 0;
  let dragging = false;
  let snapped = false;
  const SNAP_WIDTH = 164;

  function snapBack() {
    card.style.transition = 'transform 0.25s ease';
    card.style.transform = 'translateX(0)';
    snapped = false;
  }

  card.addEventListener('touchstart', (e) => {
    if (snapped) { snapBack(); return; }
    startX = e.touches[0].clientX;
    dragging = true;
    card.style.transition = 'none';
  }, { passive: true });

  card.addEventListener('touchmove', (e) => {
    if (!dragging) return;
    deltaX = e.touches[0].clientX - startX;
    if (deltaX > 0) card.style.transform = `translateX(${Math.min(deltaX, SNAP_WIDTH)}px)`;
  }, { passive: true });

  card.addEventListener('touchend', () => {
    if (!dragging) return;
    dragging = false;
    if (deltaX > 60) {
      card.style.transition = 'transform 0.25s ease';
      card.style.transform = `translateX(${SNAP_WIDTH}px)`;
      snapped = true;
    } else {
      snapBack();
    }
    deltaX = 0;
  });

  document.addEventListener('touchstart', (e) => {
    if (snapped && !wrapper.contains(e.target)) snapBack();
  }, { passive: true });

  wrapper.querySelectorAll('.assign-avatar').forEach(btn => {
    btn.addEventListener('click', () => {
      const email = btn.dataset.email;
      card.style.transition = 'transform 0.25s ease, opacity 0.25s ease';
      card.style.transform = 'translateX(100%)';
      card.style.opacity = '0';
      card.addEventListener('transitionend', () => wrapper.remove(), { once: true });
      acceptProposalWithAssignee(proposalId, email);
    });
  });
}

async function acceptProposalWithAssignee(proposalId, assigneeEmail) {
  try {
    await fetch(`${BACKEND_URL}/proposals/${proposalId}/accept`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ assignee: assigneeEmail })
    });
    loadProposals();
  } catch (err) {
    console.error('Failed to accept proposal:', err);
  }
}

async function dismissProposal(proposalId, wrapperEl) {
  wrapperEl.remove();
  try {
    await fetch(`${BACKEND_URL}/proposals/${proposalId}`, { method: 'DELETE' });
    loadProposals();
  } catch (err) {
    console.error('Failed to dismiss proposal:', err);
  }
}

// ── Voice ─────────────────────────────────────────────────────────────────────

let voiceEnabled = false;
let recognition = null;

function initVoice() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) return; // browser doesn't support it — mic stays hidden

  const micBtn = document.getElementById('mic-btn');
  micBtn.classList.remove('hidden');

  recognition = new SpeechRecognition();
  recognition.lang = 'en-US';
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  recognition.onresult = (e) => {
    const transcript = e.results[0][0].transcript;
    document.getElementById('msg-input').value = transcript;
    micBtn.classList.remove('mic-btn--recording');
    sendMessage(true);
  };

  recognition.onerror = () => micBtn.classList.remove('mic-btn--recording');
  recognition.onend = () => micBtn.classList.remove('mic-btn--recording');

  micBtn.addEventListener('click', () => {
    if (micBtn.classList.contains('mic-btn--recording')) {
      recognition.stop();
    } else {
      // Unlock speechSynthesis during user gesture so iOS allows playback later
      if (window.speechSynthesis) {
        const unlock = new SpeechSynthesisUtterance('');
        window.speechSynthesis.speak(unlock);
      }
      micBtn.classList.add('mic-btn--recording');
      recognition.start();
    }
  });
}

function speakReply(text) {
  if (!voiceEnabled || !window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const utt = new SpeechSynthesisUtterance(text);
  utt.lang = 'en-US';
  utt.rate = 1.05;
  window.speechSynthesis.speak(utt);
}

// ── Chat ──────────────────────────────────────────────────────────────────────

async function sendMessage(fromVoice = false) {
  const msgInput = document.getElementById('msg-input');
  const sendBtn = document.getElementById('send-btn');
  const text = msgInput.value.trim();
  if (!text || !currentUser) return;

  if (fromVoice) voiceEnabled = true;

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
    speakReply(data.reply);
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
