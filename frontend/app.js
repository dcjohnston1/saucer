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

function _setChatPanelHeight() {
  const panel = document.getElementById('chat-panel');
  if (window.visualViewport) {
    panel.style.height = window.visualViewport.height + 'px';
    panel.style.top = window.visualViewport.offsetTop + 'px';
  }
}

function openChat() {
  const panel = document.getElementById('chat-panel');
  panel.classList.add('chat-open');
  document.getElementById('chat-overlay').classList.remove('hidden');
  _setChatPanelHeight();
  document.getElementById('msg-input').focus();
}

function closeChat() {
  const panel = document.getElementById('chat-panel');
  panel.classList.remove('chat-open');
  panel.style.height = '';
  panel.style.top = '';
  document.getElementById('chat-overlay').classList.add('hidden');
}

if (window.visualViewport) {
  window.visualViewport.addEventListener('resize', () => {
    const panel = document.getElementById('chat-panel');
    if (panel.classList.contains('chat-open')) _setChatPanelHeight();
  });
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
  document.getElementById('add-exclude-keyword-btn').addEventListener('click', addExcludeKeyword);
  document.getElementById('new-exclude-keyword-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') addExcludeKeyword();
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

  // Recently Reviewed screen
  document.getElementById('menu-reviewed').addEventListener('click', () => {
    closeDrawer();
    openReviewedScreen();
  });
  document.getElementById('reviewed-back-btn').addEventListener('click', closeReviewedScreen);

  // Usage screen
  document.getElementById('menu-usage').addEventListener('click', () => {
    closeDrawer();
    openUsageScreen();
  });
  document.getElementById('usage-back-btn').addEventListener('click', closeUsageScreen);

  // List screen
  document.getElementById('menu-list').addEventListener('click', () => {
    closeDrawer();
    openListScreen();
  });
  document.getElementById('list-back-btn').addEventListener('click', closeListScreen);

  // Calendar screens
  document.getElementById('menu-this-week').addEventListener('click', () => {
    closeDrawer();
    openCalendarScreen(0);
  });
  document.getElementById('menu-next-week').addEventListener('click', () => {
    closeDrawer();
    openCalendarScreen(1);
  });
  document.getElementById('calendar-back-btn').addEventListener('click', closeCalendarScreen);
  document.getElementById('cal-add-btn').addEventListener('click', openAddEventModal);

  // Add event modal
  document.getElementById('add-event-close-btn').addEventListener('click', closeAddEventModal);
  document.getElementById('add-event-overlay').addEventListener('click', closeAddEventModal);
  document.getElementById('add-event-save-btn').addEventListener('click', saveNewCalendarEvent);

  // Calendar event edit drawer
  document.getElementById('cal-edit-close-btn').addEventListener('click', closeCalendarEventEditDrawer);
  document.getElementById('cal-edit-overlay').addEventListener('click', closeCalendarEventEditDrawer);
  document.getElementById('cal-edit-save-btn').addEventListener('click', saveCalendarEventEdit);
  document.getElementById('cal-edit-delete-btn').addEventListener('click', deleteCalendarEventConfirm);

  // Task detail drawer
  document.getElementById('task-detail-close-btn').addEventListener('click', closeTaskDetailDrawer);
  document.getElementById('task-detail-overlay').addEventListener('click', closeTaskDetailDrawer);

  // Date picker modal (right-swipe to calendar)
  document.getElementById('date-picker-close-btn').addEventListener('click', closeDatePickerModal);
  document.getElementById('date-picker-overlay').addEventListener('click', closeDatePickerModal);

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
  loadExcludeKeywordFilters();
  loadProposals();
  initVoice();
  initPullToRefresh();
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

// ── Usage ─────────────────────────────────────────────────────────────────────

async function openUsageScreen() {
  const content = document.getElementById('usage-content');
  content.innerHTML = '<p class="empty-state">Loading…</p>';
  document.getElementById('usage-screen').classList.remove('hidden');
  try {
    const data = await fetch(`${BACKEND_URL}/stats`).then(r => r.json());
    const tokens = (data.lifetime_tokens || 0).toLocaleString();
    const messages = (data.chat_messages || 0).toLocaleString();
    content.innerHTML = `
      <div class="usage-stat">
        <div class="usage-stat-label">Lifetime tokens used</div>
        <div class="usage-stat-value">${tokens}</div>
      </div>
      <div class="usage-stat">
        <div class="usage-stat-label">Chat messages sent</div>
        <div class="usage-stat-value">${messages}</div>
      </div>
    `;
  } catch {
    content.innerHTML = '<p class="empty-state">Could not load stats.</p>';
  }
}

function closeUsageScreen() {
  document.getElementById('usage-screen').classList.add('hidden');
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
  const summary = email.summary || null;
  const previewText = summary || bodyText.slice(0, 220).replace(/\n+/g, ' ');
  const hasMore = bodyText.length > 220 || email.html_body;

  const wrapper = document.createElement('div');
  wrapper.className = 'email-card-wrapper';
  wrapper.innerHTML = '<div class="swipe-dismiss-bg">Dismiss ✕</div>';

  const card = document.createElement('div');
  card.className = 'email-card';
  if (isNew) card.classList.add('is-new');
  const accountBadge = email.account ? `<span class="email-account-badge">${escapeHtml(email.account)}</span>` : '';
  const newBadge = isNew ? '<span class="email-new-badge" title="New"></span>' : '';
  const previewClass = summary ? 'email-preview email-preview-summary' : 'email-preview';
  card.innerHTML = `
    <div class="email-meta">
      <span class="email-sender">${escapeHtml(email.sender)}</span>
      <div class="email-meta-right-group">${newBadge}<span class="email-date">${escapeHtml(formatEmailDate(email.date))}</span></div>
    </div>
    ${accountBadge}
    <div class="email-subject">${escapeHtml(email.subject || '(No Subject)')}</div>
    <div class="${previewClass}">${escapeHtml(previewText)}${(!summary && bodyText.length > 220) ? '…' : ''}</div>
    ${hasMore ? '<button class="email-expand-btn">Show more ▾</button>' : ''}
  `;

  if (hasMore) {
    const expandBtn = card.querySelector('.email-expand-btn');
    let expandedEl = null;
    expandBtn.addEventListener('click', () => {
      if (expandedEl) {
        expandedEl.classList.toggle('hidden');
        expandBtn.textContent = expandedEl.classList.contains('hidden') ? 'Show more ▾' : 'Show less ▴';
        return;
      }
      if (email.html_body) {
        expandedEl = document.createElement('div');
        expandedEl.className = 'email-html-body';
        expandedEl.innerHTML = sanitizeEmailHtml(email.html_body);
      } else {
        expandedEl = document.createElement('div');
        expandedEl.className = 'email-full-body';
        expandedEl.textContent = bodyText;
      }
      expandBtn.parentNode.insertBefore(expandedEl, expandBtn);
      expandBtn.textContent = 'Show less ▴';
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

  buildProposalsSection(card, email);
  wrapper.appendChild(card);
  addSwipeToDismiss(wrapper, card, email.id);
  return wrapper;
}

function buildProposalsSection(card, email) {
  const section = document.createElement('div');
  section.className = 'email-proposals';

  if (email.proposals === undefined || email.proposals === null) {
    const msg = document.createElement('div');
    msg.className = 'proposals-scanning';
    msg.textContent = 'Checking for action items…';
    section.appendChild(msg);
    card.appendChild(section);
    return;
  }

  const hasPending = email.proposals.length > 0;

  if (hasPending) {
    const header = document.createElement('div');
    header.className = 'proposals-header';
    header.textContent = 'Action items';
    section.appendChild(header);
    email.proposals.forEach(p => section.appendChild(buildProposalRow(p, email.id, card)));
  }

  const reviewBtn = document.createElement('button');
  reviewBtn.className = 'review-btn';
  reviewBtn.textContent = 'Mark Reviewed';
  reviewBtn.disabled = hasPending;
  reviewBtn.addEventListener('click', () => reviewEmail(email.id, card.closest('.email-card-wrapper')));
  section.appendChild(reviewBtn);

  card.appendChild(section);
}

function buildProposalRow(p, emailId, card) {
  const wrapper = document.createElement('div');
  wrapper.className = 'proposal-row-wrapper';

  // Hidden bg: revealed by swiping the row right
  const bg = document.createElement('div');
  bg.className = 'proposal-row-bg';

  ALLOWED_EMAILS.forEach(email => {
    const btn = document.createElement('div');
    btn.className = `pr-btn pr-btn--${email[0].toLowerCase()}`;
    btn.textContent = email[0].toUpperCase();
    btn.dataset.assignee = email;
    bg.appendChild(btn);
  });
  const bothBtn = document.createElement('div');
  bothBtn.className = 'pr-btn pr-btn--both';
  bothBtn.innerHTML = `<span>${ALLOWED_EMAILS[0][0].toUpperCase()}</span><span>${ALLOWED_EMAILS[1][0].toUpperCase()}</span>`;
  bothBtn.dataset.assignee = 'both';
  bg.appendChild(bothBtn);
  const skipBtn = document.createElement('div');
  skipBtn.className = 'pr-btn pr-btn--skip';
  skipBtn.textContent = '✕';
  bg.appendChild(skipBtn);

  // Row content
  const row = document.createElement('div');
  row.className = 'proposal-row';
  row.dataset.proposalId = p.id;

  const titleEl = document.createElement('div');
  titleEl.className = 'proposal-row-title';
  titleEl.textContent = p.title;
  row.appendChild(titleEl);

  if (p.notes) {
    const notesEl = document.createElement('div');
    notesEl.className = 'proposal-row-notes';
    notesEl.textContent = p.notes;
    row.appendChild(notesEl);
  }
  if (p.date_expression) {
    const dateEl = document.createElement('div');
    dateEl.className = 'proposal-row-date';
    dateEl.textContent = `📅 ${p.date_expression}`;
    row.appendChild(dateEl);
  }

  wrapper.appendChild(bg);
  wrapper.appendChild(row);
  addSwipeToProposalRow(wrapper, row, bg, p.id, emailId, card);
  return wrapper;
}

function addSwipeToProposalRow(wrapper, row, bg, proposalId, emailId, card) {
  let startX = 0, deltaX = 0, dragging = false, snapped = false;
  const SNAP_WIDTH = 196;

  function snapBack() {
    row.style.transition = 'transform 0.25s ease';
    row.style.transform = 'translateX(0)';
    snapped = false;
  }

  row.addEventListener('touchstart', (e) => {
    if (row.classList.contains('proposal-row--handled')) return;
    if (snapped) { snapBack(); return; }
    startX = e.touches[0].clientX;
    dragging = true;
    row.style.transition = 'none';
  }, { passive: true });

  row.addEventListener('touchmove', (e) => {
    if (!dragging) return;
    deltaX = e.touches[0].clientX - startX;
    if (deltaX > 0) row.style.transform = `translateX(${Math.min(deltaX, SNAP_WIDTH)}px)`;
  }, { passive: true });

  row.addEventListener('touchend', () => {
    if (!dragging) return;
    dragging = false;
    if (deltaX > 50) {
      row.style.transition = 'transform 0.25s ease';
      row.style.transform = `translateX(${SNAP_WIDTH}px)`;
      snapped = true;
    } else {
      snapBack();
    }
    deltaX = 0;
  });

  document.addEventListener('touchstart', (e) => {
    if (snapped && !wrapper.contains(e.target)) snapBack();
  }, { passive: true });

  bg.querySelectorAll('[data-assignee]').forEach(btn => {
    btn.addEventListener('click', () => {
      assignInlineProposal(proposalId, btn.dataset.assignee, emailId, row, card);
      snapBack();
      bg.style.visibility = 'hidden';
    });
  });
  bg.querySelector('.pr-btn--skip').addEventListener('click', () => {
    skipInlineProposal(proposalId, emailId, row, card);
    snapBack();
    bg.style.visibility = 'hidden';
  });
}

async function assignInlineProposal(proposalId, assigneeEmail, emailId, row, card) {
  const badgeHtml = assigneeEmail === 'both'
    ? `<span class="inline-assignee-badge inline-assign-btn--d">D</span><span class="inline-assignee-badge inline-assign-btn--e">E</span>`
    : `<span class="inline-assignee-badge inline-assign-btn--${assigneeEmail[0].toLowerCase()}">${assigneeEmail[0].toUpperCase()}</span>`;
  const status = document.createElement('div');
  status.className = 'proposal-row-status';
  status.innerHTML = `<span class="proposal-done-label">✓ Added to list</span>${badgeHtml}`;
  row.appendChild(status);
  row.classList.add('proposal-row--handled');
  checkAllProposalsHandled(emailId, card);
  try {
    await fetch(`${BACKEND_URL}/proposals/${proposalId}/accept`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ assignee: assigneeEmail })
    });
  } catch (err) {
    console.error('Failed to assign proposal:', err);
  }
}

async function skipInlineProposal(proposalId, emailId, row, card) {
  const status = document.createElement('div');
  status.className = 'proposal-row-status';
  status.innerHTML = '<span class="proposal-done-label">Skipped</span>';
  row.appendChild(status);
  row.classList.add('proposal-row--handled');
  checkAllProposalsHandled(emailId, card);
  try {
    await fetch(`${BACKEND_URL}/proposals/${proposalId}`, { method: 'DELETE' });
  } catch (err) {
    console.error('Failed to skip proposal:', err);
  }
}

function checkAllProposalsHandled(emailId, card) {
  const unhandled = card.querySelectorAll('.proposal-row:not(.proposal-row--handled)');
  if (unhandled.length === 0) {
    const reviewBtn = card.querySelector('.review-btn');
    if (reviewBtn) reviewBtn.disabled = false;
  }
}

async function reviewEmail(emailId, wrapper) {
  try {
    await fetch(`${BACKEND_URL}/emails/${encodeURIComponent(emailId)}/review`, { method: 'POST' });
  } catch (err) {
    console.error('Failed to review email:', err);
  }
  const card = wrapper.querySelector('.email-card');
  if (card) {
    card.style.transition = 'transform 0.35s ease, opacity 0.35s ease';
    card.style.transform = 'translateX(-100%)';
    card.style.opacity = '0';
    card.addEventListener('transitionend', () => wrapper.remove(), { once: true });
  } else {
    wrapper.remove();
  }
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

// ── Recently Reviewed ─────────────────────────────────────────────────────────

function openReviewedScreen() {
  document.getElementById('reviewed-screen').classList.remove('hidden');
  loadReviewedScreen();
}

function closeReviewedScreen() {
  document.getElementById('reviewed-screen').classList.add('hidden');
}

async function loadReviewedScreen() {
  const content = document.getElementById('reviewed-content');
  content.innerHTML = '<div class="loading">Loading…</div>';
  try {
    const res = await fetch(`${BACKEND_URL}/reviewed-emails`);
    const data = await res.json();
    const emails = data.emails || [];
    if (emails.length === 0) {
      content.innerHTML = '<div class="empty-state">No reviewed emails yet.</div>';
      return;
    }
    content.innerHTML = '';
    emails.forEach(email => {
      const card = document.createElement('div');
      card.className = 'reviewed-email-card';
      card.innerHTML = `
        <div class="reviewed-email-meta">
          <span class="reviewed-email-sender">${escapeHtml(email.sender)}</span>
          <span class="reviewed-email-date">${escapeHtml(formatEmailDate(email.date))}</span>
        </div>
        <div class="reviewed-email-subject">${escapeHtml(email.subject || '(No Subject)')}</div>
      `;
      content.appendChild(card);
    });
  } catch (err) {
    content.innerHTML = '<div class="empty-state">Error loading reviewed emails.</div>';
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

    const [DAN, EMILY] = ALLOWED_EMAILS;
    const groups = [
      { label: 'Shared',     tasks: data.tasks.filter(t => t.assignee === 'both') },
      { label: "Dan's",      tasks: data.tasks.filter(t => t.assignee === DAN) },
      { label: "Emily's",    tasks: data.tasks.filter(t => t.assignee === EMILY) },
      { label: 'Unassigned', tasks: data.tasks.filter(t => !t.assignee || t.assignee === 'none') },
    ];

    container.innerHTML = '';
    groups.forEach(({ label, tasks }) => {
      if (tasks.length === 0) return;

      const heading = document.createElement('div');
      heading.className = 'list-section-header';
      heading.textContent = label;
      container.appendChild(heading);

      tasks.forEach(task => {
        const wrapper = document.createElement('div');
        wrapper.className = 'task-card-wrapper';
        wrapper.innerHTML = '<div class="swipe-add-cal-bg">📅 Calendar</div><div class="swipe-done-bg">Done ✓</div>';

        const card = document.createElement('div');
        card.className = 'task-card';
        const dateHtml = task.due && task.due !== 'none' ? `<span class="task-due">📅 ${task.due}</span>` : '';
        const assigneeHtml = task.assignee === 'both'
          ? `<div class="task-assignee-both"><div class="task-assignee task-assignee--${DAN[0].toLowerCase()}">${DAN[0].toUpperCase()}</div><div class="task-assignee task-assignee--${EMILY[0].toLowerCase()}">${EMILY[0].toUpperCase()}</div></div>`
          : task.assignee && task.assignee !== 'none'
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
        addSwipeToComplete(wrapper, card, task.title, task);
      });
    });
  } catch (err) {
    container.textContent = `Error: ${err.message}`;
  }
}

// ── Swipe to complete ─────────────────────────────────────────────────────────

function addSwipeToComplete(wrapper, card, title, task) {
  let startX = 0, deltaX = 0, dragging = false, didSwipe = false;

  card.addEventListener('touchstart', (e) => {
    startX = e.touches[0].clientX;
    dragging = true;
    didSwipe = false;
    card.style.transition = 'none';
  }, { passive: true });

  card.addEventListener('touchmove', (e) => {
    if (!dragging) return;
    deltaX = e.touches[0].clientX - startX;
    if (Math.abs(deltaX) > 10) didSwipe = true;
    if (deltaX < 0) {
      card.style.transform = `translateX(${deltaX}px)`;
    } else if (deltaX > 0) {
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
    } else if (deltaX > 80 && task) {
      card.style.transition = 'transform 0.25s ease';
      card.style.transform = 'translateX(0)';
      addTaskToCalendar(task);
    } else {
      card.style.transition = 'transform 0.25s ease';
      card.style.transform = 'translateX(0)';
    }
    deltaX = 0;
  });

  if (task) {
    card.addEventListener('click', () => {
      if (didSwipe) return;
      openTaskDetailDrawer(task);
    });
  }
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
    const unhandled = card.querySelectorAll('.proposal-row:not(.proposal-row--handled)');
    if (deltaX < -80 && unhandled.length === 0) {
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

// ── Calendar ──────────────────────────────────────────────────────────────────

let calendarWeekOffset = 0;

function getWeekRange(offset) {
  const now = new Date();
  const day = now.getDay();
  const mondayDelta = day === 0 ? -6 : 1 - day;
  const monday = new Date(now);
  monday.setDate(now.getDate() + mondayDelta + offset * 7);
  monday.setHours(0, 0, 0, 0);
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  sunday.setHours(23, 59, 59, 999);
  return { start: monday, end: sunday };
}

function formatWeekRange(start, end) {
  const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  if (start.getMonth() === end.getMonth()) {
    return `${MONTHS[start.getMonth()]} ${start.getDate()}–${end.getDate()}`;
  }
  return `${MONTHS[start.getMonth()]} ${start.getDate()} – ${MONTHS[end.getMonth()]} ${end.getDate()}`;
}

function _buildCalendarEventRow(e) {
  const row = document.createElement('div');
  row.className = 'calendar-event' + (e.all_day ? ' calendar-event--allday' : '');

  let timeStr = '';
  if (!e.all_day) {
    const t = new Date(e.start);
    timeStr = t.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  }

  let assigneeBadge = '';
  const assigneeMatch = (e.description || '').match(/Assigned to:\s*(\w+)/i);
  if (assigneeMatch) {
    const who = assigneeMatch[1].toLowerCase();
    if (who === 'both') {
      assigneeBadge = `<span class="cal-assignee-badge cal-assignee--d">D</span><span class="cal-assignee-badge cal-assignee--e">E</span>`;
    } else if (who === 'daniel') {
      assigneeBadge = `<span class="cal-assignee-badge cal-assignee--d">D</span>`;
    } else if (who === 'emily') {
      assigneeBadge = `<span class="cal-assignee-badge cal-assignee--e">E</span>`;
    }
  }

  row.innerHTML = `
    <span class="cal-event-time">${e.all_day ? 'All day' : timeStr}</span>
    <span class="cal-event-title-row">
      <span class="cal-event-title">${escapeHtml(e.title)}</span>
      ${assigneeBadge ? `<span class="cal-assignee-wrap">${assigneeBadge}</span>` : ''}
    </span>
    ${e.location ? `<span class="cal-event-location">${escapeHtml(e.location)}</span>` : ''}
  `;

  row.addEventListener('click', () => openCalendarEventEditDrawer(e));
  return row;
}

async function openCalendarScreen(weekOffset) {
  calendarWeekOffset = weekOffset;
  const { start, end } = getWeekRange(weekOffset);
  document.getElementById('calendar-screen-title').textContent = formatWeekRange(start, end);
  const content = document.getElementById('calendar-content');
  content.innerHTML = '<p class="empty-state">Loading…</p>';
  document.getElementById('calendar-screen').classList.remove('hidden');

  await _loadCalendarContent(content, start, end);
  _attachCalendarSwipe(content);
}

async function _loadCalendarContent(content, start, end) {
  const startISO = start.toISOString();
  const endISO = end.toISOString();
  try {
    const data = await fetch(
      `${BACKEND_URL}/calendar/events?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}`
    ).then(r => r.json());

    if (data.error) throw new Error(data.error);

    const events = data.events || [];
    if (events.length === 0) {
      content.innerHTML = '<p class="empty-state">Nothing on the calendar this week.</p>';
      return;
    }

    const DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    const MONTH_NAMES = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

    const byDay = {};
    events.forEach(e => {
      const dateKey = e.start.substring(0, 10);
      if (!byDay[dateKey]) byDay[dateKey] = [];
      byDay[dateKey].push(e);
    });

    content.innerHTML = '';
    Object.keys(byDay).sort().forEach(dateKey => {
      const d = new Date(dateKey + 'T12:00:00');
      const header = document.createElement('div');
      header.className = 'calendar-day-header';
      header.textContent = `${DAY_NAMES[d.getDay()]}, ${MONTH_NAMES[d.getMonth()]} ${d.getDate()}`;
      content.appendChild(header);
      byDay[dateKey].forEach(e => content.appendChild(_buildCalendarEventRow(e)));
    });
  } catch (err) {
    content.innerHTML = `<p class="empty-state">Could not load calendar: ${err.message}</p>`;
  }
}

let _calSwipeController = null;

function _attachCalendarSwipe(content) {
  if (_calSwipeController) _calSwipeController.abort();
  _calSwipeController = new AbortController();
  const signal = _calSwipeController.signal;
  let startX = 0, startY = 0, active = false;

  content.addEventListener('touchstart', (e) => {
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
    active = true;
  }, { passive: true, signal });

  content.addEventListener('touchend', async (e) => {
    if (!active) return;
    active = false;
    const dx = e.changedTouches[0].clientX - startX;
    const dy = e.changedTouches[0].clientY - startY;
    if (Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy) * 1.5) return;
    calendarWeekOffset += dx < 0 ? 1 : -1;
    const { start, end } = getWeekRange(calendarWeekOffset);
    document.getElementById('calendar-screen-title').textContent = formatWeekRange(start, end);
    content.innerHTML = '<p class="empty-state">Loading…</p>';
    await _loadCalendarContent(content, start, end);
    _attachCalendarSwipe(content);
  }, { passive: true, signal });
}

function closeCalendarScreen() {
  document.getElementById('calendar-screen').classList.add('hidden');
}

// ── HTML sanitizer ────────────────────────────────────────────────────────────

function sanitizeEmailHtml(html) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');
  // Remove dangerous elements
  ['script', 'style', 'iframe', 'form', 'input', 'button', 'object', 'embed', 'meta', 'link', 'base'].forEach(tag => {
    doc.querySelectorAll(tag).forEach(el => el.remove());
  });
  doc.body.querySelectorAll('*').forEach(el => {
    // Strip event handlers
    Array.from(el.attributes).forEach(attr => {
      if (attr.name.startsWith('on')) el.removeAttribute(attr.name);
    });
    // Sanitize links
    if (el.tagName === 'A') {
      const href = el.getAttribute('href') || '';
      if (href.startsWith('javascript:') || href.startsWith('data:') || href.startsWith('vbscript:')) {
        el.removeAttribute('href');
      }
      el.setAttribute('target', '_blank');
      el.setAttribute('rel', 'noopener noreferrer');
    }
    // Limit inline styles to safe properties only (strip them entirely)
    if (el.hasAttribute('style')) el.removeAttribute('style');
  });
  return doc.body.innerHTML;
}

// ── Exclude Keyword Filters ───────────────────────────────────────────────────

async function loadExcludeKeywordFilters() {
  try {
    const res = await fetch(`${BACKEND_URL}/exclude-keyword-filters`);
    const data = await res.json();
    renderExcludeKeywords(data.keywords || []);
  } catch (err) {
    console.error('Failed to load exclude keywords:', err);
  }
}

function renderExcludeKeywords(keywords) {
  const list = document.getElementById('exclude-keywords-list');
  list.innerHTML = '';
  if (keywords.length === 0) {
    list.innerHTML = '<p class="empty-state" style="padding: 4px 0 8px; font-size: 0.85rem;">No exclude keywords added yet.</p>';
    return;
  }
  keywords.forEach(kw => {
    const row = document.createElement('div');
    row.className = 'sender-row';
    row.innerHTML = `
      <span>${escapeHtml(kw)}</span>
      <button class="remove-sender-btn">Remove</button>
    `;
    row.querySelector('.remove-sender-btn').addEventListener('click', () => removeExcludeKeyword(kw));
    list.appendChild(row);
  });
}

async function addExcludeKeyword() {
  const input = document.getElementById('new-exclude-keyword-input');
  const keyword = input.value.trim().toLowerCase();
  if (!keyword) return;
  try {
    await fetch(`${BACKEND_URL}/exclude-keyword-filters`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keyword })
    });
    input.value = '';
    loadExcludeKeywordFilters();
  } catch (err) {
    alert(`Failed to add exclude keyword: ${err.message}`);
  }
}

async function removeExcludeKeyword(keyword) {
  try {
    await fetch(`${BACKEND_URL}/exclude-keyword-filters/${encodeURIComponent(keyword)}`, { method: 'DELETE' });
    loadExcludeKeywordFilters();
  } catch (err) {
    alert(`Failed to remove exclude keyword: ${err.message}`);
  }
}

// ── Pull-to-refresh ───────────────────────────────────────────────────────────

function initPullToRefresh() {
  let startY = 0, pulling = false, triggered = false;
  const indicator = document.getElementById('pull-to-refresh');

  document.addEventListener('touchstart', (e) => {
    const screenOpen = document.querySelectorAll('.screen:not(.hidden)').length > 0
      || document.querySelectorAll('.modal-overlay:not(.hidden)').length > 0
      || document.getElementById('chat-panel').classList.contains('chat-open');
    if (window.scrollY === 0 && !screenOpen) {
      startY = e.touches[0].clientY;
      pulling = true;
      triggered = false;
    }
  }, { passive: true });

  document.addEventListener('touchmove', (e) => {
    if (!pulling) return;
    const dy = e.touches[0].clientY - startY;
    if (dy > 72 && !triggered) {
      triggered = true;
      indicator.classList.remove('hidden');
    }
  }, { passive: true });

  document.addEventListener('touchend', async () => {
    if (!pulling) return;
    pulling = false;
    if (!triggered) return;
    try {
      await loadEmailFilters();
    } finally {
      indicator.classList.add('hidden');
      triggered = false;
    }
  }, { passive: true });
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function showToast(message, durationMs = 2500) {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.classList.remove('hidden', 'toast-fading');
  toast.classList.add('toast-visible');
  setTimeout(() => {
    toast.classList.remove('toast-visible');
    toast.classList.add('toast-fading');
    setTimeout(() => toast.classList.add('hidden'), 350);
  }, durationMs);
}

// ── Add Calendar Event Modal ──────────────────────────────────────────────────

function openAddEventModal() {
  const today = new Date().toISOString().slice(0, 10);
  document.getElementById('add-event-title').value = '';
  document.getElementById('add-event-date').value = today;
  document.getElementById('add-event-time').value = '';
  document.getElementById('add-event-notes').value = '';
  document.getElementById('add-event-overlay').classList.remove('hidden');
  document.getElementById('add-event-modal').classList.remove('hidden');
  document.getElementById('add-event-title').focus();
}

function closeAddEventModal() {
  document.getElementById('add-event-overlay').classList.add('hidden');
  document.getElementById('add-event-modal').classList.add('hidden');
}

async function saveNewCalendarEvent() {
  const title = document.getElementById('add-event-title').value.trim();
  const date = document.getElementById('add-event-date').value;
  const time = document.getElementById('add-event-time').value || null;
  const notes = document.getElementById('add-event-notes').value.trim() || null;
  if (!title || !date) { showToast('Title and date are required.'); return; }
  const btn = document.getElementById('add-event-save-btn');
  btn.disabled = true;
  try {
    const res = await fetch(`${BACKEND_URL}/calendar/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, date, time, notes })
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'Failed');
    closeAddEventModal();
    showToast('Event added to calendar');
    // Reload calendar content
    const { start, end } = getWeekRange(calendarWeekOffset);
    const content = document.getElementById('calendar-content');
    content.innerHTML = '<p class="empty-state">Loading…</p>';
    await _loadCalendarContent(content, start, end);
    _attachCalendarSwipe(content);
  } catch (err) {
    showToast(`Error: ${err.message}`);
  } finally {
    btn.disabled = false;
  }
}

// ── Calendar Event Edit Drawer ────────────────────────────────────────────────

let _editingCalEvent = null;

function openCalendarEventEditDrawer(event) {
  _editingCalEvent = event;
  document.getElementById('cal-edit-title').value = event.title || '';
  const dateStr = event.start ? event.start.substring(0, 10) : '';
  document.getElementById('cal-edit-date').value = dateStr;
  const timeStr = (!event.all_day && event.start && event.start.length > 10)
    ? new Date(event.start).toLocaleTimeString('en-CA', { hour: '2-digit', minute: '2-digit', hour12: false })
    : '';
  document.getElementById('cal-edit-time').value = timeStr;
  document.getElementById('cal-edit-notes').value = event.description || '';
  document.getElementById('cal-edit-overlay').classList.remove('hidden');
  document.getElementById('cal-edit-drawer').classList.remove('hidden');
}

function closeCalendarEventEditDrawer() {
  _editingCalEvent = null;
  document.getElementById('cal-edit-overlay').classList.add('hidden');
  document.getElementById('cal-edit-drawer').classList.add('hidden');
}

async function saveCalendarEventEdit() {
  if (!_editingCalEvent) return;
  const title = document.getElementById('cal-edit-title').value.trim();
  const start_date = document.getElementById('cal-edit-date').value;
  const time = document.getElementById('cal-edit-time').value || null;
  const notes = document.getElementById('cal-edit-notes').value.trim();
  const btn = document.getElementById('cal-edit-save-btn');
  btn.disabled = true;
  try {
    const res = await fetch(`${BACKEND_URL}/calendar/events/${_editingCalEvent.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, start_date, time, notes })
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'Failed');
    closeCalendarEventEditDrawer();
    showToast('Event updated');
    const { start, end } = getWeekRange(calendarWeekOffset);
    const content = document.getElementById('calendar-content');
    content.innerHTML = '<p class="empty-state">Loading…</p>';
    await _loadCalendarContent(content, start, end);
    _attachCalendarSwipe(content);
  } catch (err) {
    showToast(`Error: ${err.message}`);
  } finally {
    btn.disabled = false;
  }
}

async function deleteCalendarEventConfirm() {
  if (!_editingCalEvent) return;
  if (!confirm(`Delete "${_editingCalEvent.title}"?`)) return;
  const btn = document.getElementById('cal-edit-delete-btn');
  btn.disabled = true;
  try {
    const res = await fetch(`${BACKEND_URL}/calendar/events/${_editingCalEvent.id}`, { method: 'DELETE' });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'Failed');
    closeCalendarEventEditDrawer();
    showToast('Event deleted');
    const { start, end } = getWeekRange(calendarWeekOffset);
    const content = document.getElementById('calendar-content');
    content.innerHTML = '<p class="empty-state">Loading…</p>';
    await _loadCalendarContent(content, start, end);
    _attachCalendarSwipe(content);
  } catch (err) {
    showToast(`Error: ${err.message}`);
  } finally {
    btn.disabled = false;
  }
}

// ── Task Detail Drawer ────────────────────────────────────────────────────────

function openTaskDetailDrawer(task) {
  const body = document.getElementById('task-detail-body');
  const dueHtml = task.due && task.due !== 'none'
    ? `<div class="task-detail-meta">📅 Due: ${escapeHtml(task.due)}</div>` : '';
  const notesHtml = task.notes
    ? `<div class="task-detail-notes">${escapeHtml(task.notes)}</div>` : '';

  body.innerHTML = `
    <div class="task-detail-title">${escapeHtml(task.title)}</div>
    ${dueHtml}
    ${notesHtml}
    ${task.source_email_id ? '<div id="task-source-placeholder" class="task-source-tag"><span class="task-source-icon">✉️</span><span class="task-source-info"><span class="task-source-subject">Loading source email…</span></span></div>' : ''}
    <button class="task-detail-edit-btn" id="task-detail-edit-btn">Edit via Chat</button>
  `;

  if (task.source_email_id) {
    _loadTaskSourceEmail(task.source_email_id);
  }

  document.getElementById('task-detail-edit-btn').addEventListener('click', () => {
    closeTaskDetailDrawer();
    openChat();
    setTimeout(() => {
      const input = document.getElementById('msg-input');
      input.value = `I'd like to edit the task: "${task.title}"`;
      input.focus();
    }, 300);
  });

  document.getElementById('task-detail-overlay').classList.remove('hidden');
  document.getElementById('task-detail-drawer').classList.remove('hidden');
}

async function _loadTaskSourceEmail(emailId) {
  try {
    const res = await fetch(`${BACKEND_URL}/emails/${encodeURIComponent(emailId)}`);
    const data = await res.json();
    const placeholder = document.getElementById('task-source-placeholder');
    if (!placeholder) return;
    if (data.email) {
      const e = data.email;
      placeholder.innerHTML = `
        <span class="task-source-icon">✉️</span>
        <span class="task-source-info">
          <span class="task-source-subject">${escapeHtml(e.subject || '(No Subject)')}</span>
          <span class="task-source-sender">${escapeHtml(e.sender)} · ${escapeHtml(formatEmailDate(e.date))}</span>
        </span>
      `;
    } else {
      placeholder.remove();
    }
  } catch {
    const placeholder = document.getElementById('task-source-placeholder');
    if (placeholder) placeholder.remove();
  }
}

function closeTaskDetailDrawer() {
  document.getElementById('task-detail-overlay').classList.add('hidden');
  document.getElementById('task-detail-drawer').classList.add('hidden');
}

// ── Right-swipe task → Add to Calendar ───────────────────────────────────────

let _pendingCalendarTask = null;

function addTaskToCalendar(task) {
  const due = task.due && task.due !== 'none' ? task.due : null;
  if (due) {
    _doAddTaskToCalendar(task.title, due);
  } else {
    openDatePickerModal(task);
  }
}

async function _doAddTaskToCalendar(title, dateStr) {
  try {
    const res = await fetch(`${BACKEND_URL}/calendar/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, date: dateStr })
    });
    const data = await res.json();
    if (data.ok) {
      showToast('Added to calendar ✓');
    } else {
      showToast(`Error: ${data.error || 'Failed'}`);
    }
  } catch (err) {
    showToast(`Error: ${err.message}`);
  }
}

function openDatePickerModal(task) {
  _pendingCalendarTask = task;
  const today = new Date().toISOString().slice(0, 10);
  document.getElementById('date-picker-task-title').textContent = task.title;
  document.getElementById('date-picker-input').value = today;
  document.getElementById('date-picker-overlay').classList.remove('hidden');
  document.getElementById('date-picker-modal').classList.remove('hidden');

  const confirmBtn = document.getElementById('date-picker-confirm-btn');
  confirmBtn.onclick = async () => {
    const date = document.getElementById('date-picker-input').value;
    if (!date) return;
    closeDatePickerModal();
    await _doAddTaskToCalendar(_pendingCalendarTask.title, date);
    _pendingCalendarTask = null;
  };
}

function closeDatePickerModal() {
  document.getElementById('date-picker-overlay').classList.add('hidden');
  document.getElementById('date-picker-modal').classList.add('hidden');
  _pendingCalendarTask = null;
}
