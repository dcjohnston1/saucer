const BACKEND_URL = 'https://saucer-backend-987132498395.us-central1.run.app';
const ALLOWED_EMAILS = ['dcjohnston1@gmail.com', 'emily.osteen.johnston@gmail.com'];
const GOOGLE_CLIENT_ID = '987132498395-o9ldqc2vqu1b36d7d8leh8d56f4eu83a.apps.googleusercontent.com';

let currentUser = null;
let conversationHistory = [];
let conversationId = crypto.randomUUID();
let sessionPrevSeenAt = 0;
let onboardingHistory = [];
let _currentBriefingId = null;
let _currentBriefingMessage = '';
// Holds the morning briefing text to inject as Hana's first chat history entry
// when the user opens chat from the briefing modal. Cleared after first sendMessage().
let _briefingContextMessage = '';

const _highlightsCache = new Map();

function _highlightPhrase(container, phrase) {
  if (!phrase || phrase.length < 4) return;
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null, false);
  const nodes = [];
  let node;
  while ((node = walker.nextNode())) nodes.push(node);
  const lower = phrase.toLowerCase();
  nodes.forEach(textNode => {
    const idx = textNode.textContent.toLowerCase().indexOf(lower);
    if (idx === -1) return;
    const mark = document.createElement('mark');
    mark.className = 'ai-highlight';
    const after = textNode.splitText(idx);
    after.splitText(phrase.length);
    textNode.parentNode.insertBefore(mark, after);
    mark.appendChild(after);
  });
}

function _applyHighlights(el, highlights) {
  (highlights || []).forEach(phrase => _highlightPhrase(el, phrase));
}

const _SEEN_PILLS_KEY = 'saucer_seen_pills';
function _getSeenPills() {
  try { return new Set(JSON.parse(localStorage.getItem(_SEEN_PILLS_KEY) || '[]')); } catch { return new Set(); }
}
function _markPillSeen(id) {
  const seen = _getSeenPills();
  seen.add(id);
  localStorage.setItem(_SEEN_PILLS_KEY, JSON.stringify([...seen]));
}
function _updatePillNewIndicators() {
  const seen = _getSeenPills();
  document.querySelectorAll('.shortcut-pill[data-pill-id]').forEach(pill => {
    const id = pill.dataset.pillId;
    pill.querySelector('.pill-new-dot')?.remove();
    if (!seen.has(id)) {
      const dot = document.createElement('span');
      dot.className = 'pill-new-dot';
      pill.appendChild(dot);
    }
  });
}

const _splashStart = Date.now();
const _SPLASH_MIN_MS = 2800;
let _splashDismissed = false;

function dismissSplash() {
  if (_splashDismissed) return;
  _splashDismissed = true;
  const splash = document.getElementById('splash-screen');
  if (!splash) return;
  const elapsed = Date.now() - _splashStart;
  const delay = Math.max(0, _SPLASH_MIN_MS - elapsed);
  setTimeout(() => {
    splash.classList.add('splash-fadeout');
    setTimeout(() => splash.remove(), 600);
  }, delay);
}

function getUserEmail() {
  if (currentUser?.email) return currentUser.email;
  try { return JSON.parse(localStorage.getItem('saucer_user') || '{}').email || ''; } catch { return ''; }
}

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
  document.getElementById('avatar-btn').classList.add('hidden');
  document.getElementById('account-popover').classList.add('hidden');
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

  if (_pendingQuestion) {
    const q = _pendingQuestion;
    _pendingQuestion = null;
    document.getElementById('chat-btn').classList.remove('chat-btn--has-question');
    // Snooze defensively so the pulse doesn't fire again for 3 days.
    // Hana will call clear_question via tool if she gets her answer.
    fetch(`${BACKEND_URL}/hana/question/snooze`, { method: 'POST' }).catch(() => {});
    setTimeout(() => _injectQuestionContext(q), 200);
  }
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
  loadEmailIntent();
}

function closeSendersScreen() {
  document.getElementById('senders-screen').classList.add('hidden');
}

window.addEventListener('DOMContentLoaded', () => {
  requestAnimationFrame(() => {
    const splash = document.getElementById('splash-screen');
    if (splash) splash.classList.add('splash-visible');
  });
  setTimeout(dismissSplash, 5000); // safety net: dismiss if auth never fires

  // Wire up static elements
  document.getElementById('sign-out-btn').addEventListener('click', signOut);
  document.getElementById('chat-btn').addEventListener('click', openChat);
  document.getElementById('chat-overlay').addEventListener('click', closeChat);
  document.getElementById('chat-close-btn').addEventListener('click', closeChat);
  document.querySelectorAll('.accordion-header').forEach(btn => {
    btn.addEventListener('click', () => {
      const body = document.getElementById(btn.dataset.target);
      const open = !body.classList.contains('hidden');
      body.classList.toggle('hidden', open);
      btn.setAttribute('aria-expanded', String(!open));
    });
  });

  document.getElementById('topic-block-close-btn').addEventListener('click', closeTopicBlockDrawer);
  document.getElementById('topic-block-overlay').addEventListener('click', closeTopicBlockDrawer);
  document.getElementById('topic-block-confirm-btn').addEventListener('click', confirmTopicBlock);

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
  document.getElementById('msg-input').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  document.getElementById('msg-input').addEventListener('input', _updateSendBtn);
  document.getElementById('input-plus-btn').addEventListener('click', () => {
    document.getElementById('msg-input').focus();
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

  // Hana's notes screen
  document.getElementById('menu-notes').addEventListener('click', () => {
    closeDrawer();
    openNotesScreen();
  });
  document.getElementById('notes-back-btn').addEventListener('click', closeNotesScreen);
  document.getElementById('note-detail-close-btn').addEventListener('click', closeNoteDetailDrawer);
  document.getElementById('note-detail-overlay').addEventListener('click', closeNoteDetailDrawer);
  document.getElementById('note-delete-btn').addEventListener('click', deleteCurrentNote);
  document.getElementById('note-chat-btn').addEventListener('click', chatAboutCurrentNote);
  document.getElementById('add-role-btn').addEventListener('click', addRole);
  document.getElementById('new-role-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') addRole();
  });
  document.getElementById('add-preference-btn').addEventListener('click', addPref);
  document.getElementById('new-preference-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') addPref();
  });

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
  document.getElementById('menu-future-events').addEventListener('click', () => {
    closeDrawer();
    openFutureEventsScreen();
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
  document.getElementById('email-excerpt-close-btn').addEventListener('click', closeEmailExcerptDrawer);
  document.getElementById('email-excerpt-overlay').addEventListener('click', closeEmailExcerptDrawer);

  // Date picker modal (right-swipe to calendar)
  document.getElementById('date-picker-close-btn').addEventListener('click', closeDatePickerModal);
  document.getElementById('date-picker-overlay').addEventListener('click', closeDatePickerModal);

  // Morning briefing modal
  document.getElementById('briefing-overlay').addEventListener('click', dismissBriefing);
  document.getElementById('briefing-thumbs-up-btn').addEventListener('click', () => sendBriefingFeedback('positive'));
  document.getElementById('briefing-chat-btn').addEventListener('click', openBriefingChat);

  // Resync button inside Email Filters screen
  document.getElementById('resync-btn').addEventListener('click', () => resyncEmails());

  // Intent description
  document.getElementById('intent-save-btn').addEventListener('click', saveEmailIntent);

  // Review dismissed emails
  document.getElementById('review-dismissed-btn').addEventListener('click', openDismissedReview);
  document.getElementById('dismissed-review-close-btn').addEventListener('click', closeDismissedReview);
  document.getElementById('dismissed-review-overlay').addEventListener('click', closeDismissedReview);

  // Dismiss feedback drawer
  document.getElementById('dismiss-feedback-close-btn').addEventListener('click', closeDismissFeedbackDrawer);
  document.getElementById('dismiss-feedback-overlay').addEventListener('click', closeDismissFeedbackDrawer);
  document.getElementById('dismiss-feedback-confirm-btn').addEventListener('click', confirmDismissFeedback);

  // Relevant Files screen
  document.getElementById('menu-files').addEventListener('click', () => { closeDrawer(); openFilesScreen(); });
  document.getElementById('files-back-btn').addEventListener('click', closeFilesScreen);

  // Emails Hana dismissed screen
  document.getElementById('menu-hana-dismissed').addEventListener('click', () => { closeDrawer(); openHanaDismissedScreen(); });
  document.getElementById('open-hana-dismissed-btn').addEventListener('click', openHanaDismissedScreen);
  document.getElementById('hana-dismissed-back-btn').addEventListener('click', closeHanaDismissedScreen);
  document.getElementById('files-upload-btn').addEventListener('click', () => document.getElementById('files-upload-input').click());
  document.getElementById('files-upload-input').addEventListener('change', handleFileUpload);
  document.getElementById('files-search').addEventListener('input', filterFilesList);

  // Avatar button toggles account popover
  document.getElementById('avatar-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    document.getElementById('account-popover').classList.toggle('hidden');
  });
  document.addEventListener('click', () => {
    document.getElementById('account-popover').classList.add('hidden');
  });

  // Reviewed email viewer drawer
  document.getElementById('reviewed-email-drawer-close').addEventListener('click', closeReviewedEmailDrawer);
  document.getElementById('reviewed-email-overlay').addEventListener('click', closeReviewedEmailDrawer);

  // Avatar crop modal
  document.getElementById('avatar-change-btn').addEventListener('click', () => {
    document.getElementById('account-popover').classList.add('hidden');
    openAvatarCropModal();
  });
  document.getElementById('avatar-crop-close').addEventListener('click', closeAvatarCropModal);
  document.getElementById('avatar-crop-overlay').addEventListener('click', closeAvatarCropModal);
  document.getElementById('avatar-choose-btn').addEventListener('click', () => document.getElementById('avatar-file-input').click());
  document.getElementById('avatar-file-input').addEventListener('change', onAvatarFileChosen);
  document.getElementById('avatar-save-btn').addEventListener('click', saveAvatarCrop);

  // Shortcut pills
  document.getElementById('pill-this-week').addEventListener('click', () => { _markPillSeen('pill-this-week'); document.getElementById('pill-this-week').querySelector('.pill-new-dot')?.remove(); openCalendarScreen(0); });
  document.getElementById('pill-todos').addEventListener('click', () => { _markPillSeen('pill-todos'); document.getElementById('pill-todos').querySelector('.pill-new-dot')?.remove(); openListScreen(); });
  document.getElementById('pill-dismissed').addEventListener('click', () => { _markPillSeen('pill-dismissed'); document.getElementById('pill-dismissed').querySelector('.pill-new-dot')?.remove(); openHanaDismissedScreen(); });

  // Scan for tasks button
  document.getElementById('scan-todos-btn').addEventListener('click', runScanTodos);

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
  dismissSplash();
  sessionPrevSeenAt = getLastSeenAt();
  setLastSeenAt(Date.now());
  document.getElementById('login-screen').classList.add('hidden');
  document.getElementById('main-app').classList.remove('hidden');
  document.getElementById('hamburger-btn').classList.remove('hidden');
  document.getElementById('chat-btn').classList.remove('hidden');
  const avatarBtn = document.getElementById('avatar-btn');
  avatarBtn.classList.remove('hidden');
  document.getElementById('avatar-initial').textContent = (user.name || user.email)[0].toUpperCase();
  document.getElementById('account-popover-name').textContent = user.name || '';
  document.getElementById('account-popover-email').textContent = user.email || '';

  fetch(`${BACKEND_URL}/avatar?user=${encodeURIComponent(user.email)}`)
    .then(res => { if (res.ok) return res.blob(); throw new Error('no avatar'); })
    .then(blob => {
      const url = URL.createObjectURL(blob);
      const btn = document.getElementById('avatar-btn');
      btn.style.backgroundImage = `url(${url})`;
      btn.style.backgroundSize = 'cover';
      btn.style.backgroundPosition = 'center';
      document.getElementById('avatar-initial').style.display = 'none';
    })
    .catch(() => {});

  loadEmailFilters();
  loadKeywordFilters();
  loadExcludeKeywordFilters();
  initVoice();
  initHanaVoice();
  initPullToRefresh();
  checkMorningBriefing();
  startQuestionPolling();
  _updatePillNewIndicators();
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

// ── My Profile (roles & preferences) ─────────────────────────────────────────

let _ctxRoles = [];
let _ctxPrefs = [];

async function openContextScreen() {
  document.getElementById('context-screen').classList.remove('hidden');
  const rolesEl = document.getElementById('roles-list');
  const prefsEl = document.getElementById('preferences-list');
  rolesEl.innerHTML = '<p class="empty-state" style="font-size:0.85rem">Loading…</p>';
  prefsEl.innerHTML = '';
  try {
    const data = await fetch(`${BACKEND_URL}/user-settings/${encodeURIComponent(currentUser.email)}`).then(r => r.json());
    _ctxRoles = data.roles || [];
    _ctxPrefs = data.preferences || [];
    _renderContextItems('roles-list', _ctxRoles, removeRole);
    _renderContextItems('preferences-list', _ctxPrefs, removePref);
  } catch {
    rolesEl.innerHTML = '<p class="empty-state" style="font-size:0.85rem">Could not load.</p>';
  }
}

function closeContextScreen() {
  document.getElementById('context-screen').classList.add('hidden');
}

function _renderContextItems(containerId, items, removeFn) {
  const list = document.getElementById(containerId);
  list.innerHTML = '';
  if (items.length === 0) {
    list.innerHTML = '<p class="empty-state" style="padding:4px 0 8px;font-size:0.85rem">None added yet.</p>';
    return;
  }
  items.forEach((text, idx) => {
    const row = document.createElement('div');
    row.className = 'sender-row';
    row.innerHTML = `<span>${text}</span><button class="remove-sender-btn">Remove</button>`;
    row.querySelector('.remove-sender-btn').addEventListener('click', () => removeFn(idx));
    list.appendChild(row);
  });
}

async function _saveContext() {
  await fetch(`${BACKEND_URL}/user-settings/${encodeURIComponent(currentUser.email)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ roles: _ctxRoles, preferences: _ctxPrefs }),
  });
}

async function addRole() {
  const input = document.getElementById('new-role-input');
  const val = input.value.trim();
  if (!val) return;
  _ctxRoles.push(val);
  input.value = '';
  await _saveContext();
  _renderContextItems('roles-list', _ctxRoles, removeRole);
}

async function removeRole(idx) {
  _ctxRoles.splice(idx, 1);
  await _saveContext();
  _renderContextItems('roles-list', _ctxRoles, removeRole);
}

async function addPref() {
  const input = document.getElementById('new-preference-input');
  const val = input.value.trim();
  if (!val) return;
  _ctxPrefs.push(val);
  input.value = '';
  await _saveContext();
  _renderContextItems('preferences-list', _ctxPrefs, removePref);
}

async function removePref(idx) {
  _ctxPrefs.splice(idx, 1);
  await _saveContext();
  _renderContextItems('preferences-list', _ctxPrefs, removePref);
}

// ── Email Filters ─────────────────────────────────────────────────────────────

async function loadEmailFilters() {
  try {
    const [filtersRes, blockedRes, topicsRes] = await Promise.all([
      fetch(`${BACKEND_URL}/email-filters`),
      fetch(`${BACKEND_URL}/blocked-senders`),
      fetch(`${BACKEND_URL}/blocked-topics`)
    ]);
    const filtersData = await filtersRes.json();
    const blockedData = await blockedRes.json();
    const topicsData = await topicsRes.json();
    renderSenders(filtersData.filters || []);
    renderBlockedSenders(blockedData.addresses || []);
    renderBlockedTopics(topicsData.topics || []);
    await loadCachedEmails(filtersData.filters || []);
    backgroundSync(filtersData.filters || []);
  } catch (err) {
    document.getElementById('emails-content').textContent = `Error loading filters: ${err.message}`;
  }
}

async function loadCachedEmails(filters) {
  const emailsContent = document.getElementById('emails-content');
  if (!filters || filters.length === 0) {
    emailsContent.innerHTML = '<div class="empty-state">Add a sender via the menu to see their emails here.</div>';
    return;
  }
  try {
    const res = await fetch(`${BACKEND_URL}/emails/cached`);
    if (!res.ok) throw new Error('Failed to fetch cached emails');
    const data = await res.json();
    const emails = data.emails || [];
    emailsContent.innerHTML = '';
    if (emails.length === 0) {
      emailsContent.innerHTML = '<div class="empty-state">No recent emails found.</div>';
      return;
    }
    emails.sort((a, b) => new Date(b.date) - new Date(a.date));
    _renderEmailsWithGroups(emailsContent, emails);
    wireSearchInput(emailsContent);
  } catch (err) {
    emailsContent.textContent = `Error: ${err.message}`;
  }
}

function _renderEmailsWithGroups(container, emails) {
  const permittedEmails = emails.filter(e => (e.verdict || 'permitted') !== 'uncertain');
  const uncertainEmails = emails.filter(e => e.verdict === 'uncertain');
  permittedEmails.forEach(email => {
    const isNew = sessionPrevSeenAt > 0 && new Date(email.date).getTime() > sessionPrevSeenAt;
    container.appendChild(buildEmailCard(email, isNew));
  });
  if (uncertainEmails.length > 0) {
    const header = document.createElement('div');
    header.className = 'uncertain-section-header';
    header.dataset.uncertainHeader = '1';
    header.innerHTML = `<span class="uncertain-section-title">Emails Hana flagged for review</span><span class="uncertain-count-badge">${uncertainEmails.length}</span>`;
    container.appendChild(header);
    uncertainEmails.forEach(email => {
      const isNew = sessionPrevSeenAt > 0 && new Date(email.date).getTime() > sessionPrevSeenAt;
      container.appendChild(buildEmailCard(email, isNew));
    });
  }
  // Show the suggested tasks section once emails are loaded
  const tasksSection = document.getElementById('suggested-tasks-section');
  if (tasksSection && emails.length > 0) {
    tasksSection.classList.remove('hidden');
    // Auto-trigger scan on first load (content is empty). Avoids re-scanning on every refresh.
    const tasksContent = document.getElementById('suggested-tasks-content');
    if (tasksContent && tasksContent.children.length === 0) {
      runScanTodos();
    }
  }
}

async function backgroundSync(filters) {
  if (!filters || filters.length === 0) return;
  try {
    const res = await fetch(`${BACKEND_URL}/emails`);
    if (!res.ok) return;
    const data = await res.json();
    const emails = data.emails || [];
    const emailsContent = document.getElementById('emails-content');
    const currentIds = new Set(
      [...emailsContent.querySelectorAll('.email-card-wrapper[data-email-id]')]
        .map(el => el.dataset.emailId)
    );
    const newEmails = emails.filter(e => !currentIds.has(e.id));
    if (newEmails.length === 0) return;
    newEmails.sort((a, b) => new Date(b.date) - new Date(a.date));
    // Insert permitted ones at top, then re-render uncertain section
    const newPermitted = newEmails.filter(e => (e.verdict || 'permitted') !== 'uncertain');
    const newUncertain = newEmails.filter(e => e.verdict === 'uncertain');
    const firstChild = emailsContent.firstChild;
    newPermitted.forEach(email => {
      emailsContent.insertBefore(buildEmailCard(email, true), firstChild);
    });
    if (newUncertain.length > 0) {
      let header = emailsContent.querySelector('[data-uncertain-header]');
      if (!header) {
        header = document.createElement('div');
        header.className = 'uncertain-section-header';
        header.dataset.uncertainHeader = '1';
        emailsContent.appendChild(header);
      }
      newUncertain.forEach(email => emailsContent.appendChild(buildEmailCard(email, true)));
      const count = emailsContent.querySelectorAll('.email-card--uncertain').length;
      header.innerHTML = `<span class="uncertain-section-title">Emails Hana flagged for review</span><span class="uncertain-count-badge">${count}</span>`;
    }
    wireSearchInput(emailsContent);
    const label = newEmails.length === 1 ? '1 new email' : `${newEmails.length} new emails`;
    showToast(label);
  } catch {
    // silent — background sync failure is non-fatal
  }
}

function renderSenders(filters) {
  document.getElementById('badge-permitted').textContent = filters.length;
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
      body: JSON.stringify({ email, user: getUserEmail() })
    });
    input.value = '';
    loadEmailFilters();
  } catch (err) {
    alert(`Failed to add sender: ${err.message}`);
  }
}

async function removeSender(email) {
  try {
    const userParam = getUserEmail() ? `?user=${encodeURIComponent(getUserEmail())}` : '';
    await fetch(`${BACKEND_URL}/email-filters/${encodeURIComponent(email)}${userParam}`, { method: 'DELETE' });
    loadEmailFilters();
  } catch (err) {
    alert(`Failed to remove sender: ${err.message}`);
  }
}

function renderBlockedSenders(addresses) {
  document.getElementById('badge-blocked').textContent = addresses.length;
  const list = document.getElementById('blocked-senders-list');
  list.innerHTML = '';
  if (addresses.length === 0) {
    list.innerHTML = '<p class="empty-state" style="padding: 4px 0 8px; font-size: 0.85rem;">No blocked senders.</p>';
    return;
  }
  addresses.forEach(email => {
    const row = document.createElement('div');
    row.className = 'sender-row blocked-sender-row';
    row.innerHTML = `
      <span>${email}</span>
      <button class="remove-sender-btn" data-email="${email}">Remove</button>
    `;
    row.querySelector('.remove-sender-btn').addEventListener('click', () => removeBlockedSender(email));
    list.appendChild(row);
  });
}

async function removeBlockedSender(email) {
  try {
    const userParam = getUserEmail() ? `?user=${encodeURIComponent(getUserEmail())}` : '';
    await fetch(`${BACKEND_URL}/blocked-senders/${encodeURIComponent(email)}${userParam}`, { method: 'DELETE' });
    loadEmailFilters();
  } catch (err) {
    alert(`Failed to remove blocked sender: ${err.message}`);
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
  document.getElementById('badge-keywords').textContent = keywords.length;
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
      body: JSON.stringify({ keyword, user: getUserEmail() })
    });
    input.value = '';
    loadKeywordFilters();
  } catch (err) {
    alert(`Failed to add keyword: ${err.message}`);
  }
}

async function removeKeyword(keyword) {
  try {
    const userParam = getUserEmail() ? `?user=${encodeURIComponent(getUserEmail())}` : '';
    await fetch(`${BACKEND_URL}/keyword-filters/${encodeURIComponent(keyword)}${userParam}`, { method: 'DELETE' });
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
  const summary = email.summary
    ? (email.summary.length > 140 ? email.summary.slice(0, 140) + '…' : email.summary)
    : null;
  const previewText = summary !== null ? summary : bodyText.slice(0, 140);
  const hasMore = bodyText.length > 220 || email.html_body;
  const isUncertain = email.verdict === 'uncertain';

  const wrapper = document.createElement('div');
  wrapper.className = 'email-card-wrapper';
  wrapper.dataset.emailId = email.id;
  wrapper.dataset.emailSender = email.sender;
  wrapper.dataset.verdict = email.verdict || 'permitted';
  wrapper.innerHTML = '<div class="swipe-email-action-bg swipe-dismiss-bg">Dismiss ✕</div>';

  const card = document.createElement('div');
  card.className = 'email-card';
  if (isNew) card.classList.add('is-new');
  if (isUncertain) card.classList.add('email-card--uncertain');
  const accountBadge = email.account ? `<span class="email-account-badge">${escapeHtml(email.account)}</span>` : '';
  const newBadge = isNew ? '<span class="email-new-badge" title="New"></span>' : '';
  const previewClass = summary ? 'email-preview email-preview-summary' : 'email-preview';
  const rawReason = email.verdict_reason || '';
  const truncatedReason = rawReason.length > 120 ? rawReason.slice(0, 120) + '…' : rawReason;
  const uncertainBadge = isUncertain ? `<span class="uncertain-badge">Hana wasn't sure: ${escapeHtml(truncatedReason || 'reason not recorded')}</span>` : '';
  // Show the first source span as a highlighted quote block on the card (Item 3).
  // source_spans are written by scan-todos and stored on the Firestore email doc.
  const firstSpan = (email.source_spans && email.source_spans.length > 0) ? email.source_spans[0] : null;
  const spanQuote = firstSpan
    ? `<div class="email-card-highlight-quote">"${escapeHtml(firstSpan)}"</div>`
    : '';
  card.innerHTML = `
    <div class="email-meta">
      <span class="email-sender">${escapeHtml(email.sender)}</span>
      <div class="email-meta-right-group">${newBadge}<span class="email-date">${escapeHtml(formatEmailDate(email.date))}</span></div>
    </div>
    ${accountBadge}
    <div class="email-subject">${escapeHtml(email.subject || '(No Subject)')}</div>
    ${uncertainBadge}
    <div class="${previewClass}">${escapeHtml(previewText)}${(!summary && bodyText.length > 220) ? '…' : ''}</div>
    ${spanQuote}
    ${hasMore ? '<button class="email-expand-btn">Show more ▾</button>' : ''}
  `;

  if (hasMore) {
    const expandBtn = card.querySelector('.email-expand-btn');
    let expandedEl = null;
    expandBtn.addEventListener('click', async () => {
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
      expandBtn.after(expandedEl);
      expandBtn.textContent = 'Show less ▴';
      // Highlight source spans from proposals first (most accurate)
      const proposalSpans = (email.proposals || []).flatMap(p => p.source_spans || []);
      if (proposalSpans.length > 0) {
        _applyHighlights(expandedEl, proposalSpans);
      }
      if (_highlightsCache.has(email.id)) {
        _applyHighlights(expandedEl, _highlightsCache.get(email.id));
      } else {
        try {
          const res = await fetch(`${BACKEND_URL}/emails/${encodeURIComponent(email.id)}/highlights`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ body_text: bodyText.slice(0, 3000) }),
          });
          if (res.ok) {
            const data = await res.json();
            const highlights = data.highlights || [];
            _highlightsCache.set(email.id, highlights);
            _applyHighlights(expandedEl, highlights);
          }
        } catch {}
      }
    });
  }

  if (email.attachments && email.attachments.length > 0) {
    const chips = document.createElement('div');
    chips.className = 'email-attachments';
    email.attachments.forEach(a => {
      const chip = document.createElement('span');
      chip.className = 'attachment-chip';
      chip.textContent = `📎 ${a.filename}`;

      const isPdf = /\.pdf$/i.test(a.filename);
      const isImage = /\.(jpg|jpeg|png|gif|webp)$/i.test(a.filename);

      if (isPdf || isImage) {
        chip.classList.add('attachment-chip--expandable');
        let inlineEl = null;
        chip.addEventListener('click', async () => {
          // Toggle if already rendered
          if (inlineEl) {
            const hidden = inlineEl.classList.toggle('hidden');
            chip.classList.toggle('attachment-chip--open', !hidden);
            return;
          }
          chip.textContent = `📎 ${a.filename} (loading…)`;
          try {
            // Get or fetch file_id
            if (!a.file_id) {
              const r = await fetch(`${BACKEND_URL}/emails/${encodeURIComponent(email.id)}/attachment-file-id?filename=${encodeURIComponent(a.filename)}`);
              if (!r.ok) throw new Error('file_id fetch failed');
              const d = await r.json();
              if (!d.file_id) throw new Error('no file_id returned');
              a.file_id = d.file_id;
            }
            // Fetch bytes as blob
            const r2 = await fetch(`${BACKEND_URL}/files/${encodeURIComponent(a.file_id)}/download`);
            if (!r2.ok) throw new Error('download failed');
            const blob = await r2.blob();
            const url = URL.createObjectURL(blob);

            inlineEl = document.createElement('div');
            inlineEl.className = 'attachment-inline';
            if (isImage) {
              const img = document.createElement('img');
              img.src = url;
              img.className = 'attachment-inline-img';
              inlineEl.appendChild(img);
            } else {
              const iframe = document.createElement('iframe');
              iframe.src = url;
              iframe.className = 'attachment-inline-pdf';
              iframe.title = a.filename;
              inlineEl.appendChild(iframe);
            }
            chip.after(inlineEl);
            chip.classList.add('attachment-chip--open');
          } catch {
            if (a.extracted_text) {
              inlineEl = document.createElement('div');
              inlineEl.className = 'attachment-text';
              inlineEl.textContent = a.extracted_text;
              chip.after(inlineEl);
              chip.classList.add('attachment-chip--open');
            } else {
              showToast('Could not open attachment');
            }
          } finally {
            chip.textContent = `📎 ${a.filename}`;
          }
        });
        chips.appendChild(chip);
      } else if (a.extracted_text) {
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
        // Unknown file type — trigger download
        chip.style.cursor = 'pointer';
        chip.addEventListener('click', async () => {
          if (!a.file_id) {
            showToast('No download available for this file type');
            return;
          }
          const r = await fetch(`${BACKEND_URL}/files/${encodeURIComponent(a.file_id)}/download`);
          if (!r.ok) { showToast('Could not download attachment'); return; }
          const blob = await r.blob();
          const url = URL.createObjectURL(blob);
          const anchor = document.createElement('a');
          anchor.href = url;
          anchor.download = a.filename;
          anchor.click();
          URL.revokeObjectURL(url);
        });
        chips.appendChild(chip);
      }
    });
    card.appendChild(chips);
  }

  buildProposalsSection(card, email);

  const blockOverlay = document.createElement('div');
  blockOverlay.className = 'email-block-overlay hidden';
  blockOverlay.innerHTML = `
    <button class="email-block-opt email-block-opt--sender">Block Sender — hide all emails from this address</button>
    <button class="email-block-opt email-block-opt--topic">Block this type — let AI identify the category and block it</button>
    <button class="email-block-cancel">Cancel</button>
  `;
  blockOverlay.querySelector('.email-block-opt--sender').addEventListener('click', onBlockSenderChosen);
  blockOverlay.querySelector('.email-block-opt--topic').addEventListener('click', onBlockTopicChosen);
  blockOverlay.querySelector('.email-block-cancel').addEventListener('click', closeBlockOptions);
  card.appendChild(blockOverlay);

  wrapper.appendChild(card);
  const bodyPreview = (email.body || email.snippet || '').slice(0, 300);
  addSwipeToDismiss(wrapper, card, email.id, email.sender, email.subject || '', bodyPreview, email.verdict || 'permitted');
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
  let startX = 0, startY = 0, deltaX = 0;
  let dragging = false, snapped = false, axisLocked = false, axisIsHorizontal = false;
  const SNAP_WIDTH = 196;

  function snapBack() {
    row.style.transition = 'transform 0.25s ease';
    row.style.transform = 'translateX(0)';
    snapped = false;
  }

  row.addEventListener('touchstart', (e) => {
    if (row.classList.contains('proposal-row--handled')) return;
    e.stopPropagation();
    if (snapped) { snapBack(); return; }
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
    dragging = true;
    axisLocked = false;
    axisIsHorizontal = false;
    row.style.transition = 'none';
  }, { passive: true });

  row.addEventListener('touchmove', (e) => {
    if (!dragging) return;
    const dx = e.touches[0].clientX - startX;
    const dy = e.touches[0].clientY - startY;
    if (!axisLocked) {
      if (Math.abs(dx) < 5 && Math.abs(dy) < 5) return;
      axisLocked = true;
      axisIsHorizontal = Math.abs(dx) >= Math.abs(dy);
    }
    if (!axisIsHorizontal) return;
    e.preventDefault();
    deltaX = dx;
    if (deltaX > 0) row.style.transform = `translateX(${Math.min(deltaX, SNAP_WIDTH)}px)`;
  }, { passive: false });

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
      body: JSON.stringify({ assignee: assigneeEmail, user: getUserEmail() })
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
    const userParam = getUserEmail() ? `?user=${encodeURIComponent(getUserEmail())}` : '';
    await fetch(`${BACKEND_URL}/proposals/${proposalId}${userParam}`, { method: 'DELETE' });
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
    const userParam = getUserEmail() ? `?user=${encodeURIComponent(getUserEmail())}` : '';
    await fetch(`${BACKEND_URL}/emails/${encodeURIComponent(emailId)}/review${userParam}`, { method: 'POST' });
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
  emailsContent.innerHTML = '<div class="loading">Hana is reviewing your emails…</div>';
  try {
    const res = await fetch(`${BACKEND_URL}/emails/resync`, { method: 'POST' });
    if (!res.ok) throw new Error('Resync failed');
    const data = await res.json();
    const counts = data.eval_counts || {};
    emailsContent.innerHTML = '';
    if (!data.emails || data.emails.length === 0) {
      const blocked = counts.blocked || 0;
      emailsContent.innerHTML = `<div class="empty-state">Hana filtered out everything in the last 90 days based on your intent.${blocked > 0 ? ` Check "Emails Hana dismissed" if something looks missing, or "Review dismissed emails" to reconsider anything you removed yourself.` : ''}</div>`;
      return;
    }
    const emails = data.emails;
    emails.sort((a, b) => new Date(b.date) - new Date(a.date));
    _renderEmailsWithGroups(emailsContent, emails);
    wireSearchInput(emailsContent);
    if (counts.blocked > 0) {
      showToast(`Filtered ${counts.blocked} email${counts.blocked === 1 ? '' : 's'} — check "Emails Hana dismissed" to review`);
    }
  } catch (err) {
    emailsContent.textContent = `Error: ${err.message}`;
  }
}

async function loadEmails(filters, preserveExisting = false) {
  const emailsContent = document.getElementById('emails-content');
  if (!filters || filters.length === 0) {
    emailsContent.innerHTML = '<div class="empty-state">Add a sender via the menu to see their emails here.</div>';
    return;
  }

  let refreshBanner = null;
  let currentIds = null;
  if (preserveExisting) {
    currentIds = new Set(
      [...emailsContent.querySelectorAll('.email-card-wrapper[data-email-id]')]
        .map(el => el.dataset.emailId)
    );
    refreshBanner = document.createElement('div');
    refreshBanner.className = 'email-refresh-banner';
    refreshBanner.textContent = 'Refreshing…';
    emailsContent.insertBefore(refreshBanner, emailsContent.firstChild);
  }

  try {
    const res = await fetch(`${BACKEND_URL}/emails`);
    if (!res.ok) throw new Error('Failed to fetch emails');
    const data = await res.json();

    const emails = data.emails || [];

    if (preserveExisting && currentIds && emails.length === currentIds.size &&
        emails.every(e => currentIds.has(e.id))) {
      refreshBanner.remove();
      showToast("You're all caught up");
      return;
    }

    emailsContent.innerHTML = '';
    if (emails.length === 0) {
      emailsContent.innerHTML = '<div class="empty-state">No recent emails found.</div>';
      return;
    }
    emails.sort((a, b) => new Date(b.date) - new Date(a.date));
    _renderEmailsWithGroups(emailsContent, emails);
    wireSearchInput(emailsContent);
  } catch (err) {
    if (refreshBanner) {
      refreshBanner.remove();
    } else {
      emailsContent.textContent = `Error: ${err.message}`;
    }
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
    const emails = (data.emails || []).sort((a, b) => {
      const tsA = a._action_timestamp || a.date || '';
      const tsB = b._action_timestamp || b.date || '';
      return new Date(tsB) - new Date(tsA);
    });
    const windowDays = data.window_days || 30;

    if (emails.length === 0) {
      content.innerHTML = `<p class="empty-state">No activity in the last ${windowDays} days.</p>`;
      return;
    }

    content.innerHTML = `<p class="reviewed-window-note">Showing last ${windowDays} days</p>`;

    emails.forEach(email => {
      const card = document.createElement('div');
      card.className = 'reviewed-email-card';
      card.style.cursor = 'pointer';

      const actionLabel = email._action_label || 'Reviewed';
      const actionTs = email._action_timestamp ? formatEmailDate(email._action_timestamp) : '';

      card.innerHTML = `
        <div class="reviewed-email-meta">
          <span class="reviewed-email-sender">${escapeHtml(email.sender || '')}</span>
          <span class="reviewed-email-date">${escapeHtml(formatEmailDate(email.date))}</span>
        </div>
        <div class="reviewed-email-subject">${escapeHtml(email.subject || '(No Subject)')}</div>
        <div class="reviewed-email-action-label">${escapeHtml(actionLabel)}${actionTs ? ' · ' + actionTs : ''}</div>
      `;

      card.addEventListener('click', () => openReviewedEmailDrawer(email));
      content.appendChild(card);
    });
  } catch (err) {
    content.innerHTML = '<div class="empty-state">Error loading reviewed emails.</div>';
  }
}

function openReviewedEmailDrawer(email) {
  document.getElementById('reviewed-email-drawer-subject').textContent = email.subject || '(No Subject)';
  const body = document.getElementById('reviewed-email-drawer-body');
  const meta = `<div class="email-excerpt-meta">${escapeHtml(email.sender || '')} · ${escapeHtml(formatEmailDate(email.date))}</div>`;
  if (email.html_body) {
    body.innerHTML = meta + `<div class="email-html-body">${sanitizeEmailHtml(email.html_body)}</div>`;
  } else {
    const text = (email.body || email.snippet || '').trim();
    body.innerHTML = meta + `<div class="email-excerpt-body">${escapeHtml(text)}</div>`;
  }
  document.getElementById('reviewed-email-overlay').classList.remove('hidden');
  document.getElementById('reviewed-email-drawer').classList.remove('hidden');
}

function closeReviewedEmailDrawer() {
  document.getElementById('reviewed-email-overlay').classList.add('hidden');
  document.getElementById('reviewed-email-drawer').classList.add('hidden');
}

// NOTE: Proposals screen removed in Hana sprint (Task 5). Inline proposal rows on email
// cards and the proposals endpoints are deprecated; to be removed in the next sprint.

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
  container.innerHTML = '<div class="loading">Loading to-do list...</div>';
  try {
    await fetch(`${BACKEND_URL}/doc/dedup`, { method: 'POST' }).catch(() => {});
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
        wrapper.innerHTML = '<div class="swipe-task-action-bg"></div>';

        const card = document.createElement('div');
        card.className = 'task-card';
        const dateHtml = task.due && task.due !== 'none' ? `<span class="task-due">📅 ${task.due}</span>` : '';
        const assigneeHtml = task.assignee === 'both'
          ? `<div class="task-assignee-both"><div class="task-assignee task-assignee--${DAN[0].toLowerCase()}">${DAN[0].toUpperCase()}</div><div class="task-assignee task-assignee--${EMILY[0].toLowerCase()}">${EMILY[0].toUpperCase()}</div></div>`
          : task.assignee && task.assignee !== 'none'
            ? `<div class="task-assignee task-assignee--${task.assignee[0].toLowerCase()}">${task.assignee[0].toUpperCase()}</div>`
            : '';
        const aiSourceHtml = task.source === 'ai-suggested'
          ? '<div class="task-ai-source">Hana noticed this</div>'
          : '';
        card.innerHTML = `
          <div class="task-main">
            <div class="task-title">${escapeHtml(task.title)}</div>
            <div class="task-meta-right">${dateHtml}${assigneeHtml}</div>
          </div>
          ${task.notes ? `<div class="task-notes">${escapeHtml(task.notes)}</div>` : ''}
          ${aiSourceHtml}
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
  let startX = 0, startY = 0, deltaX = 0;
  let dragging = false, didSwipe = false, axisLocked = false, axisIsHorizontal = false;
  const bgEl = wrapper.querySelector('.swipe-task-action-bg');

  card.addEventListener('touchstart', (e) => {
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
    dragging = true;
    didSwipe = false;
    axisLocked = false;
    axisIsHorizontal = false;
    deltaX = 0;
    card.style.transition = 'none';
  }, { passive: true });

  card.addEventListener('touchmove', (e) => {
    if (!dragging) return;
    const dx = e.touches[0].clientX - startX;
    const dy = e.touches[0].clientY - startY;
    if (!axisLocked) {
      if (Math.abs(dx) < 5 && Math.abs(dy) < 5) return;
      axisLocked = true;
      axisIsHorizontal = Math.abs(dx) >= Math.abs(dy);
    }
    if (!axisIsHorizontal) return;
    e.preventDefault();
    deltaX = dx;
    if (Math.abs(deltaX) > 10) didSwipe = true;
    card.style.transform = `translateX(${deltaX}px)`;
    if (bgEl) {
      if (deltaX < 0) {
        bgEl.textContent = '📅 Add to Calendar';
        bgEl.className = 'swipe-task-action-bg action-cal';
      } else {
        bgEl.textContent = 'Done ✓';
        bgEl.className = 'swipe-task-action-bg action-done';
      }
    }
  }, { passive: false });

  card.addEventListener('touchend', () => {
    if (!dragging) return;
    dragging = false;
    if (deltaX < -80 && task) {
      // Left swipe = Add to Calendar
      addTaskToCalendar(task, card, wrapper);
    } else if (deltaX > 80) {
      // Right swipe = Done
      card.style.transition = 'transform 0.3s ease, opacity 0.3s ease';
      card.style.transform = 'translateX(100%)';
      card.style.opacity = '0';
      card.addEventListener('transitionend', () => wrapper.remove(), { once: true });
      completeTask(title);
    } else {
      // Partial swipe — snap back
      card.style.transition = 'transform 0.25s ease';
      card.style.transform = 'translateX(0)';
      if (bgEl) bgEl.textContent = '';
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
      body: JSON.stringify({ title, user: getUserEmail() })
    });
  } catch (err) {
    console.error('Failed to complete task:', err);
  }
}

// ── Swipe to dismiss (emails) ─────────────────────────────────────────────────

function addSwipeToDismiss(wrapper, card, emailId, senderEmail, emailSubject, bodyPreview, verdict = 'permitted') {
  let startX = 0, startY = 0, deltaX = 0;
  let dragging = false, axisLocked = false, axisIsHorizontal = false;
  const bgEl = wrapper.querySelector('.swipe-email-action-bg');

  card.addEventListener('touchstart', (e) => {
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
    dragging = true;
    axisLocked = false;
    axisIsHorizontal = false;
    deltaX = 0;
    card.style.transition = 'none';
  }, { passive: true });

  card.addEventListener('touchmove', (e) => {
    if (!dragging) return;
    const dx = e.touches[0].clientX - startX;
    const dy = e.touches[0].clientY - startY;
    if (!axisLocked) {
      if (Math.abs(dx) < 5 && Math.abs(dy) < 5) return;
      axisLocked = true;
      axisIsHorizontal = Math.abs(dx) >= Math.abs(dy);
    }
    if (!axisIsHorizontal) return;
    e.preventDefault();
    deltaX = dx;
    if (bgEl) {
      if (deltaX > 0) { bgEl.textContent = 'Block 🚫'; bgEl.className = 'swipe-email-action-bg swipe-block-bg'; }
      else { bgEl.textContent = 'Dismiss ✕'; bgEl.className = 'swipe-email-action-bg swipe-dismiss-bg'; }
    }
    card.style.transform = `translateX(${deltaX}px)`;
  }, { passive: false });

  card.addEventListener('touchend', () => {
    if (!dragging) return;
    dragging = false;
    const unhandled = card.querySelectorAll('.proposal-row:not(.proposal-row--handled)');
    if (deltaX < -80 && unhandled.length === 0) {
      if (verdict === 'uncertain') {
        card.style.transition = 'transform 0.25s ease';
        card.style.transform = 'translateX(0)';
        if (bgEl) { bgEl.textContent = 'Dismiss ✕'; bgEl.className = 'swipe-email-action-bg swipe-dismiss-bg'; }
        openDismissFeedbackDrawer(emailId, emailSubject, wrapper);
      } else {
        card.style.transition = 'transform 0.3s ease, opacity 0.3s ease';
        card.style.transform = 'translateX(-100%)';
        card.style.opacity = '0';
        card.addEventListener('transitionend', () => wrapper.remove(), { once: true });
        dismissEmail(emailId);
      }
    } else if (deltaX > 80 && senderEmail) {
      card.style.transition = 'transform 0.25s ease';
      card.style.transform = 'translateX(0)';
      if (bgEl) { bgEl.textContent = 'Dismiss ✕'; bgEl.className = 'swipe-email-action-bg swipe-dismiss-bg'; }
      showBlockOptions(wrapper, card, emailId, senderEmail, emailSubject, bodyPreview);
    } else {
      if (bgEl) { bgEl.textContent = 'Dismiss ✕'; bgEl.className = 'swipe-email-action-bg swipe-dismiss-bg'; }
      card.style.transition = 'transform 0.25s ease';
      card.style.transform = 'translateX(0)';
    }
    deltaX = 0;
  });
}

async function blockSender(senderEmail) {
  showToast('Sender blocked');
  try {
    await fetch(`${BACKEND_URL}/blocked-senders`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: senderEmail, user: getUserEmail() })
    });
    const blockedRes = await fetch(`${BACKEND_URL}/blocked-senders`);
    const blockedData = await blockedRes.json();
    renderBlockedSenders(blockedData.addresses || []);
  } catch (err) {
    console.error('Failed to block sender:', err);
  }
}

function removeEmailsBySender(senderEmail) {
  document.querySelectorAll('.email-card-wrapper').forEach(wrapper => {
    if (wrapper.dataset.emailSender === senderEmail) wrapper.remove();
  });
}

// ── Block options sheet ───────────────────────────────────────────────────────

let _blockOptionsContext = null;

function showBlockOptions(wrapper, card, emailId, senderEmail, emailSubject, bodyPreview) {
  _blockOptionsContext = { wrapper, card, emailId, senderEmail, emailSubject, bodyPreview };
  const overlay = card.querySelector('.email-block-overlay');
  if (overlay) overlay.classList.remove('hidden');
}

function closeBlockOptions() {
  if (_blockOptionsContext) {
    const overlay = _blockOptionsContext.card.querySelector('.email-block-overlay');
    if (overlay) overlay.classList.add('hidden');
  }
  _blockOptionsContext = null;
}

async function onBlockSenderChosen() {
  if (!_blockOptionsContext) return;
  const { wrapper, card, senderEmail } = _blockOptionsContext;
  closeBlockOptions();
  card.style.transition = 'transform 0.3s ease, opacity 0.3s ease';
  card.style.transform = 'translateX(100%)';
  card.style.opacity = '0';
  card.addEventListener('transitionend', () => {
    wrapper.remove();
    removeEmailsBySender(senderEmail);
  }, { once: true });
  blockSender(senderEmail);
}

async function onBlockTopicChosen() {
  if (!_blockOptionsContext) return;
  const { senderEmail, emailSubject, bodyPreview } = _blockOptionsContext;
  closeBlockOptions();
  showTopicBlockDrawer(senderEmail, emailSubject, bodyPreview);
}

// ── Topic block drawer ────────────────────────────────────────────────────────

let _topicBlockContext = null;

async function showTopicBlockDrawer(senderEmail, emailSubject, bodyPreview) {
  _topicBlockContext = { senderEmail, emailSubject, bodyPreview };
  const input = document.getElementById('topic-block-label-input');
  input.value = '';
  input.placeholder = 'Generating label…';
  document.getElementById('topic-block-confirm-btn').disabled = true;
  document.getElementById('topic-block-sender-label').textContent = senderEmail;
  document.getElementById('topic-block-overlay').classList.remove('hidden');
  document.getElementById('topic-block-drawer').classList.remove('hidden');

  try {
    const res = await fetch(`${BACKEND_URL}/generate-topic-label`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subject: emailSubject, body_preview: bodyPreview })
    });
    const data = await res.json();
    input.value = data.label || '';
    input.placeholder = 'e.g. Home Depot promotional offers';
  } catch (err) {
    input.placeholder = 'Enter a label for this type of email';
    console.error('Failed to generate topic label:', err);
  }
  document.getElementById('topic-block-confirm-btn').disabled = false;
}

function closeTopicBlockDrawer() {
  document.getElementById('topic-block-overlay').classList.add('hidden');
  document.getElementById('topic-block-drawer').classList.add('hidden');
  _topicBlockContext = null;
}

async function confirmTopicBlock() {
  if (!_topicBlockContext) return;
  const { senderEmail, emailSubject, bodyPreview } = _topicBlockContext;
  const label = document.getElementById('topic-block-label-input').value.trim();
  if (!label) return;

  const btn = document.getElementById('topic-block-confirm-btn');
  btn.disabled = true;
  btn.textContent = 'Saving…';

  try {
    await fetch(`${BACKEND_URL}/blocked-topics`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sender: senderEmail,
        label,
        description: label,
        user: getUserEmail()
      })
    });
    closeTopicBlockDrawer();
    showToast(`Blocking: "${label}"`);
    if (_blockOptionsContext) removeEmailsBySender(senderEmail);
    const topicsRes = await fetch(`${BACKEND_URL}/blocked-topics`);
    const topicsData = await topicsRes.json();
    renderBlockedTopics(topicsData.topics || []);
  } catch (err) {
    console.error('Failed to save blocked topic:', err);
    btn.disabled = false;
    btn.textContent = 'Block this type';
  }
}

function renderBlockedTopics(topics) {
  document.getElementById('badge-topics').textContent = topics.length;
  const list = document.getElementById('blocked-topics-list');
  list.innerHTML = '';
  if (topics.length === 0) {
    list.innerHTML = '<p class="empty-state" style="padding: 4px 0 8px; font-size: 0.85rem;">No blocked topics yet.</p>';
    return;
  }
  topics.forEach(topic => {
    const row = document.createElement('div');
    row.className = 'sender-row blocked-sender-row';
    row.innerHTML = `
      <div class="blocked-topic-text">
        <span class="blocked-topic-label">${escapeHtml(topic.label)}</span>
        <span class="blocked-topic-sender">${escapeHtml(topic.sender)}</span>
      </div>
      <button class="remove-sender-btn">Remove</button>
    `;
    row.querySelector('.remove-sender-btn').addEventListener('click', () => removeBlockedTopic(topic.id));
    list.appendChild(row);
  });
}

async function removeBlockedTopic(topicId) {
  try {
    const userParam = getUserEmail() ? `?user=${encodeURIComponent(getUserEmail())}` : '';
    await fetch(`${BACKEND_URL}/blocked-topics/${encodeURIComponent(topicId)}${userParam}`, { method: 'DELETE' });
    const res = await fetch(`${BACKEND_URL}/blocked-topics`);
    const data = await res.json();
    renderBlockedTopics(data.topics || []);
  } catch (err) {
    alert(`Failed to remove blocked topic: ${err.message}`);
  }
}

async function dismissEmail(emailId) {
  try {
    const userParam = getUserEmail() ? `?user=${encodeURIComponent(getUserEmail())}` : '';
    await fetch(`${BACKEND_URL}/emails/${emailId}/dismiss${userParam}`, { method: 'DELETE' });
  } catch (err) {
    console.error('Failed to dismiss email:', err);
  }
}

function addSwipeToAssign(wrapper, card, proposalId) {
  let startX = 0, startY = 0, deltaX = 0;
  let dragging = false, snapped = false, axisLocked = false, axisIsHorizontal = false;
  const SNAP_WIDTH = 164;

  function snapBack() {
    card.style.transition = 'transform 0.25s ease';
    card.style.transform = 'translateX(0)';
    snapped = false;
  }

  card.addEventListener('touchstart', (e) => {
    e.stopPropagation();
    if (snapped) { snapBack(); return; }
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
    dragging = true;
    axisLocked = false;
    axisIsHorizontal = false;
    card.style.transition = 'none';
  }, { passive: true });

  card.addEventListener('touchmove', (e) => {
    if (!dragging) return;
    const dx = e.touches[0].clientX - startX;
    const dy = e.touches[0].clientY - startY;
    if (!axisLocked) {
      if (Math.abs(dx) < 5 && Math.abs(dy) < 5) return;
      axisLocked = true;
      axisIsHorizontal = Math.abs(dx) >= Math.abs(dy);
    }
    if (!axisIsHorizontal) return;
    e.preventDefault();
    deltaX = dx;
    if (deltaX > 0) card.style.transform = `translateX(${Math.min(deltaX, SNAP_WIDTH)}px)`;
  }, { passive: false });

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
      body: JSON.stringify({ assignee: assigneeEmail, user: getUserEmail() })
    });
  } catch (err) {
    console.error('Failed to accept proposal:', err);
  }
}

async function dismissProposal(proposalId, wrapperEl) {
  wrapperEl.remove();
  try {
    const userParam = getUserEmail() ? `?user=${encodeURIComponent(getUserEmail())}` : '';
    await fetch(`${BACKEND_URL}/proposals/${proposalId}${userParam}`, { method: 'DELETE' });
  } catch (err) {
    console.error('Failed to dismiss proposal:', err);
  }
}

// ── Voice ─────────────────────────────────────────────────────────────────────

let voiceModeActive = localStorage.getItem('hana_voice_mode') === 'true';
let recognition = null;
let recognitionFired = false;
let _voiceTranscript = '';    // accumulated final chunks for current session
let _voiceSilenceTimer = null; // fires after 1.8s of silence to auto-submit

function initVoice() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const sendBtn = document.getElementById('send-btn');
  const micBtn = document.getElementById('mic-btn');

  // Wire send-btn: voice-to-voice toggle when empty, text send when textarea has content
  sendBtn.addEventListener('click', () => {
    if (sendBtn.dataset.mode === 'send' || !SpeechRecognition) {
      sendMessage();
      return;
    }
    if (voiceModeActive) {
      // Turn off voice-to-voice
      voiceModeActive = false;
      localStorage.setItem('hana_voice_mode', false);
      window.speechSynthesis.cancel();
      try { recognition.stop(); } catch (e) {}
      micBtn.classList.remove('mic-btn--recording', 'hana-speaking');
      _applyVoiceModeBtnState();
    } else {
      // Turn on voice-to-voice and start listening
      voiceModeActive = true;
      localStorage.setItem('hana_voice_mode', true);
      _applyVoiceModeBtnState();
      _unlockSpeechSynthesis();
      _voiceTranscript = '';
      recognitionFired = false;
      micBtn.classList.add('mic-btn--recording');
      try { recognition.start(); } catch (e) {}
    }
  });

  if (!SpeechRecognition) return;

  if (!document.getElementById('hana-voice-btn')) micBtn.classList.remove('hidden');
  _applyVoiceModeBtnState();

  recognition = new SpeechRecognition();
  recognition.lang = 'en-US';
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;

  recognition.onresult = (e) => {
    let finalChunk = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {
      if (e.results[i].isFinal) finalChunk += e.results[i][0].transcript;
    }
    if (!finalChunk) return;

    _voiceTranscript += (_voiceTranscript ? ' ' : '') + finalChunk.trim();
    document.getElementById('msg-input').value = _voiceTranscript;
    recognitionFired = true;

    clearTimeout(_voiceSilenceTimer);
    _voiceSilenceTimer = setTimeout(() => recognition.stop(), 1800);
  };

  recognition.onerror = () => {
    clearTimeout(_voiceSilenceTimer);
    if (micBtn) micBtn.classList.remove('mic-btn--recording');
    recognitionFired = false;
    _voiceTranscript = '';
  };

  recognition.onend = () => {
    clearTimeout(_voiceSilenceTimer);
    if (micBtn) micBtn.classList.remove('mic-btn--recording');
    if (recognitionFired && _voiceTranscript.trim()) {
      document.getElementById('msg-input').value = _voiceTranscript.trim();
      _voiceTranscript = '';
      recognitionFired = false;
      sendMessage();
    } else {
      _voiceTranscript = '';
      recognitionFired = false;
      // If voice mode is still active and Hana isn't speaking, restart listening
      if (voiceModeActive && !window.speechSynthesis.speaking) {
        setTimeout(() => {
          if (!voiceModeActive) return;
          try { if (micBtn) micBtn.classList.add('mic-btn--recording'); recognition.start(); } catch (e) {}
        }, 300);
      }
    }
  };

  // Mic button: speech-to-text only (voiceModeActive stays false)
  micBtn.addEventListener('click', () => {
    // If voice-to-voice is running, interrupt and switch to text mode
    if (voiceModeActive) {
      voiceModeActive = false;
      localStorage.setItem('hana_voice_mode', false);
      window.speechSynthesis.cancel();
      micBtn.classList.remove('hana-speaking');
      _applyVoiceModeBtnState();
    }

    if (micBtn.classList.contains('mic-btn--recording')) {
      clearTimeout(_voiceSilenceTimer);
      recognition.stop(); // onend sends as text
    } else {
      _voiceTranscript = '';
      recognitionFired = false;
      micBtn.classList.add('mic-btn--recording');
      try { recognition.start(); } catch (e) {}
    }
  });
}

// ── Hana Voice (Google Cloud STT/TTS — hold to speak) ────────────────────────

function initHanaVoice() {
  const btn = document.getElementById('hana-voice-btn');
  if (!btn) return;

  let mediaRecorder = null;
  let audioChunks = [];
  let recordingTimer = null;
  let timerInterval = null;
  let recordingStartMs = 0;
  let currentAudio = null;  // currently playing Audio element
  let _voiceStream = null;  // persistent mic stream — avoids repeated permission prompts

  // Inject timer label inside the button
  const timerEl = document.createElement('span');
  timerEl.id = 'hana-voice-timer';
  btn.style.position = 'relative';
  btn.appendChild(timerEl);

  function _setState(state) {
    btn.classList.remove('hana-voice-recording', 'hana-voice-processing', 'hana-voice-speaking', 'hana-voice-error');
    if (state) btn.classList.add(`hana-voice-${state}`);
    btn.setAttribute('aria-label',
      state === 'recording'  ? 'Recording — release to send' :
      state === 'processing' ? 'Hana is thinking…' :
      state === 'speaking'   ? 'Hana is speaking — tap to stop' :
      state === 'error'      ? "Didn't catch that — try again" :
                               'Hold to speak to Hana'
    );
  }

  function _startTimer() {
    recordingStartMs = Date.now();
    timerInterval = setInterval(() => {
      const secs = Math.floor((Date.now() - recordingStartMs) / 1000);
      timerEl.textContent = `${secs}s`;
    }, 500);
  }

  function _stopTimer() {
    clearInterval(timerInterval);
    timerInterval = null;
    timerEl.textContent = '';
  }

  // Earcon — soft rising tone played during processing to fill the latency gap
  let _earconCtx = null;
  let _earconOsc = null;
  let _earconGain = null;

  function _playEarcon() {
    try {
      if (!window.AudioContext && !window.webkitAudioContext) return; // not supported
      _stopEarcon(); // ensure clean state
      _earconCtx = new (window.AudioContext || window.webkitAudioContext)();
      _earconGain = _earconCtx.createGain();
      _earconGain.gain.setValueAtTime(0.06, _earconCtx.currentTime);
      _earconGain.connect(_earconCtx.destination);

      _earconOsc = _earconCtx.createOscillator();
      _earconOsc.type = 'sine';
      _earconOsc.frequency.setValueAtTime(440, _earconCtx.currentTime);         // start A4
      _earconOsc.frequency.linearRampToValueAtTime(880, _earconCtx.currentTime + 0.2); // ramp to A5
      _earconOsc.connect(_earconGain);
      _earconOsc.start();
    } catch (e) {
      // fail silently — earcon is a UX enhancement, never a hard dependency
    }
  }

  function _stopEarcon() {
    try {
      if (_earconOsc) { _earconOsc.stop(); _earconOsc.disconnect(); _earconOsc = null; }
      if (_earconGain) { _earconGain.disconnect(); _earconGain = null; }
      if (_earconCtx) { _earconCtx.close(); _earconCtx = null; }
    } catch (e) {
      // fail silently
    }
  }

  async function _ensureVoiceStream() {
    if (_voiceStream && _voiceStream.active) return _voiceStream;
    _voiceStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    return _voiceStream;
  }

  async function _startRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') return;

    // Stop any playing audio response first
    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
      _setState(null);
    }

    try {
      const stream = await _ensureVoiceStream();
      // Use WebM/Opus — accepted natively by Google Cloud STT WEBM_OPUS encoding
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm';
      audioChunks = [];
      mediaRecorder = new MediaRecorder(stream, { mimeType });
      mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
      mediaRecorder.start(100); // collect data every 100ms for smoother chunks
      _setState('recording');
      _startTimer();
    } catch (err) {
      console.error('[hana-voice] getUserMedia failed:', err);
      showToast('Microphone access denied. Please allow microphone in browser settings.');
    }
  }

  async function _stopRecordingAndSend() {
    if (!mediaRecorder || mediaRecorder.state === 'inactive') {
      _setState(null);
      _stopTimer();
      return;
    }

    _stopTimer();

    const duration = Date.now() - recordingStartMs;
    if (duration < 500) {
      // Too short — likely an accidental tap
      mediaRecorder.stop();
      mediaRecorder = null;
      audioChunks = [];
      _setState(null);
      return;
    }

    return new Promise(resolve => {
      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
        mediaRecorder = null;
        audioChunks = [];
        await _sendToHana(audioBlob);
        resolve();
      };
      mediaRecorder.stop();
    });
  }

  async function _sendToHana(audioBlob) {
    _setState('processing');
    _playEarcon();

    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');
    formData.append('user', currentUser ? currentUser.email : '');
    formData.append('user_email', currentUser ? currentUser.email : '');
    formData.append('conversation_id', conversationId);

    try {
      const res = await fetch(`${BACKEND_URL}/voice/run`, {
        method: 'POST',
        body: formData,
      });

      if (res.ok && res.headers.get('Content-Type')?.startsWith('audio/')) {
        // Success — play the MP3 response
        const mp3Blob = await res.blob();
        const audioUrl = URL.createObjectURL(mp3Blob);
        currentAudio = new Audio(audioUrl);
        _stopEarcon();
        _setState('speaking');

        currentAudio.onended = () => {
          URL.revokeObjectURL(audioUrl);
          currentAudio = null;
          _setState(null);
        };
        currentAudio.onerror = () => {
          URL.revokeObjectURL(audioUrl);
          currentAudio = null;
          _setState(null);
          showToast("Couldn't play Hana's response.");
        };

        currentAudio.play().catch(() => {
          // Autoplay blocked — show tap-to-hear button
          _setState(null);
          showToast('Tap to hear Hana\'s response.');
          btn.addEventListener('click', () => {
            if (currentAudio) { currentAudio.play(); _setState('speaking'); }
          }, { once: true });
        });
      } else {
        // API returned an error JSON
        const data = await res.json().catch(() => ({}));
        _stopEarcon();
        if (data.error === 'low_confidence' || data.error === 'no_transcript') {
          _setState('error');
          setTimeout(() => _setState(null), 2000);
        } else {
          _setState(null);
          showToast(data.message || 'Something went wrong. Please try again.');
        }
      }
    } catch (err) {
      console.error('[hana-voice] fetch error:', err);
      _stopEarcon();
      _setState(null);
      showToast('Voice request failed. Please check your connection.');
    }
  }

  // Hold-to-record: pointerdown starts, pointerup/pointerleave stops
  btn.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    btn.setPointerCapture(e.pointerId);
    // If speaking, stop playback instead of starting a new recording
    if (currentAudio && btn.classList.contains('hana-voice-speaking')) {
      currentAudio.pause();
      currentAudio = null;
      _setState(null);
      return;
    }
    if (!btn.classList.contains('hana-voice-processing')) {
      _startRecording();
    }
  });

  btn.addEventListener('pointerup', (e) => {
    e.preventDefault();
    _stopRecordingAndSend();
  });

  btn.addEventListener('pointercancel', (e) => {
    e.preventDefault();
    // Cancel cleanly without sending
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
      mediaRecorder.stream.getTracks().forEach(t => t.stop());
      mediaRecorder = null;
      audioChunks = [];
    }
    _stopTimer();
    _setState(null);
  });
}

function _unlockSpeechSynthesis() {
  if (window.speechSynthesis) {
    const unlock = new SpeechSynthesisUtterance('');
    window.speechSynthesis.speak(unlock);
  }
}

function _applyVoiceModeBtnState() {
  const sendBtn = document.getElementById('send-btn');
  if (!sendBtn || sendBtn.dataset.mode === 'send') return;
  if (voiceModeActive) {
    sendBtn.classList.add('voice-active');
    sendBtn.setAttribute('aria-label', 'Stop voice conversation');
  } else {
    sendBtn.classList.remove('voice-active');
    sendBtn.setAttribute('aria-label', 'Start voice conversation');
  }
}

function stripMarkdown(text) {
  return text
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*(.*?)\*/g, '$1')
    .replace(/#{1,6}\s/g, '')
    .replace(/`{1,3}[^`]*`{1,3}/g, '')
    .replace(/\|/g, ', ')
    .replace(/\n+/g, '. ')
    .trim();
}

function speakReply(text, bubbleEl) {
  if (!voiceModeActive || !window.speechSynthesis) return;
  _doSpeak(text, bubbleEl);
}

// Plays a silent 50ms AudioContext buffer, then calls cb. On iOS this forces the
// audio session to reroute to the current output device (Bluetooth headphones)
// before speechSynthesis.speak() fires, fixing the first-utterance speaker bug.
function _primeAudioRoute(cb) {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) { cb(); return; }
    const ctx = new Ctx();
    const buf = ctx.createBuffer(1, Math.ceil(ctx.sampleRate * 0.05), ctx.sampleRate);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    src.onended = () => { try { ctx.close(); } catch (e) {} cb(); };
    src.start();
  } catch (e) { cb(); }
}

function _doSpeak(text, bubbleEl) {
  window.speechSynthesis.cancel();
  const micBtn = document.getElementById('mic-btn');

  const isIOS = /iP(hone|od|ad)/.test(navigator.userAgent);
  let speechStarted = false;

  const utt = new SpeechSynthesisUtterance(stripMarkdown(text));
  utt.lang = 'en-US';
  utt.rate = 0.92;
  utt.pitch = 1.0;
  utt.volume = 1.0;

  // Safety net for the iOS bug where utt.onend stops firing after several turns
  const safetyMs = Math.max(4000, text.length * 75) + 2000;
  const safetyTimer = setTimeout(() => {
    if (voiceModeActive && recognition) {
      try { recognitionFired = false; _voiceTranscript = ''; recognition.start(); } catch (e) {}
    }
  }, safetyMs);

  utt.onstart = () => {
    speechStarted = true;
    if (micBtn) micBtn.classList.add('hana-speaking');
  };

  utt.onend = () => {
    clearTimeout(safetyTimer);
    speechStarted = true;
    if (micBtn) {
      micBtn.classList.remove('hana-speaking');
      micBtn.classList.add('ready-pulse');
      setTimeout(() => micBtn.classList.remove('ready-pulse'), 1500);
    }
    if (voiceModeActive && recognition) {
      setTimeout(() => {
        if (!voiceModeActive) return;
        try {
          recognitionFired = false;
          _voiceTranscript = '';
          if (micBtn) micBtn.classList.add('mic-btn--recording');
          recognition.start();
        } catch (e) {}
      }, 400);
    }
  };

  function _speak() {
    const voices = window.speechSynthesis.getVoices();
    if (voices.length > 0) {
      _setPreferredVoice(utt, voices);
      window.speechSynthesis.speak(utt);
    } else {
      window.speechSynthesis.onvoiceschanged = () => {
        window.speechSynthesis.onvoiceschanged = null;
        _setPreferredVoice(utt, window.speechSynthesis.getVoices());
        window.speechSynthesis.speak(utt);
      };
      setTimeout(() => {
        const v = window.speechSynthesis.getVoices();
        if (v.length > 0 && !utt.voice) {
          _setPreferredVoice(utt, v);
          window.speechSynthesis.speak(utt);
        }
      }, 100);
    }
  }

  // Prime audio route before speaking (fixes iOS Bluetooth first-utterance bug)
  _primeAudioRoute(_speak);

  // iOS PWA fallback: if synthesis never starts within 700ms, show tap-to-hear
  if (isIOS) {
    setTimeout(() => {
      if (!speechStarted) {
        clearTimeout(safetyTimer);
        window.speechSynthesis.cancel();
        _addTapToHearBtn(text, bubbleEl);
      }
    }, 700);
  }
}

function _setPreferredVoice(utt, voices) {
  const preferred = voices.find(v =>
    v.lang.startsWith('en') && (
      v.name.includes('Samantha') ||
      v.name.includes('Google US English') ||
      v.name.includes('Microsoft Aria') ||
      v.name.includes('Karen')
    )
  ) || voices.find(v => v.lang.startsWith('en')) || voices[0];
  if (preferred) utt.voice = preferred;
}

function _addTapToHearBtn(text, bubbleEl) {
  if (!bubbleEl || !window.speechSynthesis) return;
  const btn = document.createElement('button');
  btn.className = 'tap-to-hear-btn';
  btn.textContent = '▶ Tap to hear';
  btn.addEventListener('click', () => {
    btn.remove();
    _doSpeak(text, bubbleEl);
  });
  bubbleEl.appendChild(btn);
}

// ── Chat ──────────────────────────────────────────────────────────────────────

function _hideEmptyState() {
  const el = document.getElementById('chat-empty-state');
  if (el) el.style.display = 'none';
}

const _waveformSVG = `<svg width="18" height="18" viewBox="0 0 20 20" fill="white"><rect x="1" y="6" width="3" height="8" rx="1.5"/><rect x="6" y="2" width="3" height="16" rx="1.5"/><rect x="11" y="5" width="3" height="10" rx="1.5"/><rect x="16" y="3" width="3" height="14" rx="1.5"/></svg>`;
const _arrowSVG = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M12 20V4M5 11l7-7 7 7" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

function _updateSendBtn() {
  const sendBtn = document.getElementById('send-btn');
  if (!sendBtn) return;
  const hasText = document.getElementById('msg-input').value.trim().length > 0;
  if (hasText) {
    sendBtn.innerHTML = _arrowSVG;
    sendBtn.dataset.mode = 'send';
    sendBtn.setAttribute('aria-label', 'Send message');
    sendBtn.classList.remove('voice-active');
  } else {
    sendBtn.innerHTML = _waveformSVG;
    sendBtn.dataset.mode = 'voice';
    sendBtn.setAttribute('aria-label', voiceModeActive ? 'Stop voice conversation' : 'Start voice conversation');
    if (voiceModeActive) sendBtn.classList.add('voice-active');
    else sendBtn.classList.remove('voice-active');
  }
}

async function sendMessage() {
  const msgInput = document.getElementById('msg-input');
  const sendBtn = document.getElementById('send-btn');
  const text = msgInput.value.trim();
  if (!text || !currentUser) return;

  appendMessage('user', text);
  msgInput.value = '';
  _updateSendBtn();
  sendBtn.disabled = true;
  const typing = appendMessage('saucer', '…', true);

  // If opening from morning briefing, prepend the briefing as Hana's first history entry
  // so the backend has full briefing context for this conversation. Clear after first use.
  let historyToSend = conversationHistory;
  if (_briefingContextMessage) {
    historyToSend = [
      { role: 'assistant', content: _briefingContextMessage },
      ...conversationHistory,
    ];
    _briefingContextMessage = '';
  }

  try {
    const res = await fetch(`${BACKEND_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user: currentUser.name, user_email: currentUser.email, message: text, history: historyToSend, conversation_id: conversationId, voice_mode: voiceModeActive })
    });
    if (!res.ok) throw new Error(`Server error ${res.status}`);
    const data = await res.json();
    typing.remove();
    const replyBubble = appendMessage('saucer', data.reply);
    if (data.actions && data.actions.includes('noted')) appendActionChip('Noted');
    speakReply(data.reply, replyBubble);
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
  _hideEmptyState();
  const messages = document.getElementById('messages');
  const bubble = document.createElement('div');
  bubble.className = `bubble ${sender === 'saucer' ? 'saucer' : 'user'}`;
  if (isTyping) bubble.classList.add('typing');
  bubble.textContent = text;
  messages.appendChild(bubble);
  messages.scrollTop = messages.scrollHeight;
  return bubble;
}

function appendActionChip(label) {
  _hideEmptyState();
  const messages = document.getElementById('messages');
  const chip = document.createElement('div');
  chip.className = 'action-chip';
  chip.textContent = label;
  messages.appendChild(chip);
  messages.scrollTop = messages.scrollHeight;
}

// ── Onboarding ────────────────────────────────────────────────────────────────

function openOnboarding() {
  closeDrawer();
  onboardingHistory = [];
  document.getElementById('onboarding-messages').innerHTML = '';
  document.getElementById('onboarding-input').value = '';
  document.getElementById('onboarding-input-row').classList.remove('hidden');
  document.getElementById('onboarding-success').classList.add('hidden');
  document.getElementById('onboarding-screen').classList.remove('hidden');
  _sendOnboardingTurn('');
}

function closeOnboarding() {
  document.getElementById('onboarding-screen').classList.add('hidden');
  onboardingHistory = [];
}

function _appendOnboardingBubble(sender, text, isTyping = false) {
  const messages = document.getElementById('onboarding-messages');
  const bubble = document.createElement('div');
  bubble.className = `bubble ${sender === 'saucer' ? 'saucer' : 'user'}`;
  if (isTyping) bubble.classList.add('typing');
  bubble.textContent = text;
  messages.appendChild(bubble);
  messages.scrollTop = messages.scrollHeight;
  return bubble;
}

async function _sendOnboardingTurn(text) {
  const sendBtn = document.getElementById('onboarding-send-btn');
  sendBtn.disabled = true;
  const typing = _appendOnboardingBubble('saucer', '…', true);

  try {
    const res = await fetch(`${BACKEND_URL}/onboarding`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_email: currentUser.email,
        message: text,
        history: onboardingHistory,
      }),
    });
    if (!res.ok) throw new Error(`Server error ${res.status}`);
    const data = await res.json();
    typing.remove();
    _appendOnboardingBubble('saucer', data.reply);

    onboardingHistory.push(
      { role: 'user', content: text },
      { role: 'assistant', content: data.reply },
    );

    if (data.complete) {
      document.getElementById('onboarding-input-row').classList.add('hidden');
      document.getElementById('onboarding-success').classList.remove('hidden');
    }
  } catch (err) {
    typing.remove();
    _appendOnboardingBubble('saucer', `Something went wrong: ${err.message}`);
  } finally {
    sendBtn.disabled = false;
  }
}

function submitOnboardingMessage() {
  const input = document.getElementById('onboarding-input');
  const text = input.value.trim();
  if (!text) return;
  _appendOnboardingBubble('user', text);
  input.value = '';
  _sendOnboardingTurn(text);
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
  const wrapper = document.createElement('div');
  wrapper.className = 'cal-event-wrapper';

  const bg = document.createElement('div');
  bg.className = 'cal-event-action-bg';
  bg.innerHTML = `
    <button class="cal-action-btn cal-action-btn--d"  data-assignee-label="Daniel" title="Assign to Dan">D</button>
    <button class="cal-action-btn cal-action-btn--e"  data-assignee-label="Emily"  title="Assign to Emily">E</button>
    <button class="cal-action-btn cal-action-btn--de" data-assignee-label="Both"   title="Assign to both">DE</button>
    <button class="cal-action-btn cal-action-btn--x"  data-assignee-label=""       title="Delete event">✕</button>
  `;
  wrapper.appendChild(bg);

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
    ${e.source_email_id ? `<span class="cal-source-email-link" data-email-id="${escapeHtml(e.source_email_id)}">View email ↗</span>` : ''}
  `;
  if (e.source_email_id) {
    row.querySelector('.cal-source-email-link').addEventListener('click', ev => {
      ev.stopPropagation();
      _openEmailFromId(e.source_email_id);
    });
  }

  row.addEventListener('click', () => openCalendarEventEditDrawer(e));
  wrapper.appendChild(row);

  addSwipeToCalendarEvent(wrapper, row, bg, e);
  return wrapper;
}

function addSwipeToCalendarEvent(wrapper, row, bg, event) {
  const SNAP_WIDTH = 196;
  let startX = 0, startY = 0, deltaX = 0;
  let dragging = false, snapped = false, axisLocked = false, axisIsHorizontal = false;

  function snapBack() {
    row.style.transition = 'transform 0.25s ease';
    row.style.transform = 'translateX(0)';
    snapped = false;
  }

  row.addEventListener('touchstart', (e) => {
    e.stopPropagation();
    if (snapped) { snapBack(); return; }
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
    dragging = true;
    axisLocked = false;
    axisIsHorizontal = false;
    row.style.transition = 'none';
  }, { passive: true });

  row.addEventListener('touchmove', (e) => {
    if (!dragging) return;
    const dx = e.touches[0].clientX - startX;
    const dy = e.touches[0].clientY - startY;
    if (!axisLocked) {
      if (Math.abs(dx) < 5 && Math.abs(dy) < 5) return;
      axisLocked = true;
      axisIsHorizontal = Math.abs(dx) >= Math.abs(dy);
    }
    if (!axisIsHorizontal) return;
    e.preventDefault();
    e.stopPropagation();
    deltaX = dx;
    if (deltaX > 0) row.style.transform = `translateX(${Math.min(deltaX, SNAP_WIDTH)}px)`;
  }, { passive: false });

  row.addEventListener('touchend', (e) => {
    if (!dragging) return;
    dragging = false;
    e.stopPropagation();
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

  bg.querySelectorAll('.cal-action-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const assigneeLabel = btn.dataset.assigneeLabel;
      snapBack();

      if (btn.classList.contains('cal-action-btn--x')) {
        if (!confirm(`Delete "${event.title}"?`)) return;
        try {
          const userParam = getUserEmail() ? `?user=${encodeURIComponent(getUserEmail())}` : '';
          await fetch(`${BACKEND_URL}/calendar/events/${encodeURIComponent(event.id)}${userParam}`, { method: 'DELETE' });
          wrapper.remove();
          showToast('Event deleted');
        } catch (err) {
          showToast('Could not delete event');
        }
      } else {
        try {
          await fetch(`${BACKEND_URL}/calendar/events/${encodeURIComponent(event.id)}/assignee`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ assignee_label: assigneeLabel, user: getUserEmail() }),
          });
          showToast(`Assigned to ${assigneeLabel}`);
          const { start, end } = getWeekRange(calendarWeekOffset);
          const content = document.getElementById('calendar-content');
          content.innerHTML = '<p class="empty-state">Loading…</p>';
          await _loadCalendarContent(content, start, end);
          _attachCalendarSwipe(content);
        } catch (err) {
          showToast('Could not update assignee');
        }
      }
    });
  });
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

// Opens a calendar view showing events from 14 days out to 180 days out.
// Gives the user assurance that Hana is tracking events that are beyond the weekly view.
async function openFutureEventsScreen() {
  const now = new Date();
  const start = new Date(now.getTime() + 14 * 24 * 60 * 60 * 1000);   // +14 days
  const end   = new Date(now.getTime() + 180 * 24 * 60 * 60 * 1000);  // +180 days
  document.getElementById('calendar-screen-title').textContent = 'Future Events';
  const content = document.getElementById('calendar-content');
  content.innerHTML = '<p class="empty-state">Loading…</p>';
  document.getElementById('calendar-screen').classList.remove('hidden');
  try {
    await _loadCalendarContent(content, start, end);
  } catch (err) {
    content.innerHTML = `<p class="empty-state">Could not load calendar events: ${escapeHtml(err.message)}</p>`;
  }
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
      content.innerHTML = '<p class="empty-state">No events found in this period.</p>';
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

    // Notify the user about events Hana added from emails (silent background trigger).
    // Only show the toast once per session per event to avoid repetitive notifications.
    const newHanaEvents = events.filter(e => e.source_email_id && !_hanaCalendarNotified.has(e.id));
    if (newHanaEvents.length > 0) {
      newHanaEvents.forEach(e => _hanaCalendarNotified.add(e.id));
      const label = newHanaEvents.length === 1
        ? `Hana added "${newHanaEvents[0].title}" from your emails`
        : `Hana added ${newHanaEvents.length} events from your emails`;
      showToast(label, 4000);
    }
  } catch (err) {
    content.innerHTML = `<p class="empty-state">Could not load calendar: ${err.message}</p>`;
  }
}

let _calSwipeController = null;
// Tracks event IDs for which the user has already seen a "Hana added this" toast this session.
const _hanaCalendarNotified = new Set();

function _attachCalendarSwipe(content) {
  if (_calSwipeController) _calSwipeController.abort();
  _calSwipeController = new AbortController();
  const signal = _calSwipeController.signal;
  let startX = 0, startY = 0, active = false, axisLocked = false, axisIsHorizontal = false;

  content.addEventListener('touchstart', (e) => {
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
    active = true;
    axisLocked = false;
    axisIsHorizontal = false;
  }, { passive: true, signal });

  content.addEventListener('touchmove', (e) => {
    if (!active || axisLocked) return;
    const dx = e.touches[0].clientX - startX;
    const dy = e.touches[0].clientY - startY;
    if (Math.abs(dx) < 5 && Math.abs(dy) < 5) return;
    axisLocked = true;
    axisIsHorizontal = Math.abs(dx) >= Math.abs(dy) * 1.5;
  }, { passive: true, signal });

  content.addEventListener('touchend', async (e) => {
    if (!active) return;
    active = false;
    if (!axisIsHorizontal) return;
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
  document.getElementById('badge-exclude').textContent = keywords.length;
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
      body: JSON.stringify({ keyword, user: getUserEmail() })
    });
    input.value = '';
    loadExcludeKeywordFilters();
    loadEmailFilters();
  } catch (err) {
    alert(`Failed to add exclude keyword: ${err.message}`);
  }
}

async function removeExcludeKeyword(keyword) {
  try {
    const userParam = getUserEmail() ? `?user=${encodeURIComponent(getUserEmail())}` : '';
    await fetch(`${BACKEND_URL}/exclude-keyword-filters/${encodeURIComponent(keyword)}${userParam}`, { method: 'DELETE' });
    loadExcludeKeywordFilters();
    loadEmailFilters();
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
      const res = await fetch(`${BACKEND_URL}/email-filters`);
      const data = await res.json();
      renderSenders(data.filters || []);
      await loadEmails(data.filters || [], true);
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
      body: JSON.stringify({ title, date, time, notes, user: getUserEmail() })
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
      body: JSON.stringify({ title, start_date, time, notes, user: getUserEmail() })
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
    const userParam = getUserEmail() ? `?user=${encodeURIComponent(getUserEmail())}` : '';
    const res = await fetch(`${BACKEND_URL}/calendar/events/${_editingCalEvent.id}${userParam}`, { method: 'DELETE' });
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
    const res = await fetch(`${BACKEND_URL}/email/${encodeURIComponent(emailId)}/excerpt`);
    const data = await res.json();
    const placeholder = document.getElementById('task-source-placeholder');
    if (!placeholder) return;
    if (!data.error) {
      placeholder.innerHTML = `
        <span class="task-source-icon">✉️</span>
        <span class="task-source-info">
          <span class="task-source-subject">${escapeHtml(data.subject || '(No Subject)')}</span>
          <span class="task-source-sender">${escapeHtml(data.sender)} · ${escapeHtml(formatEmailDate(data.date))}</span>
        </span>
      `;
      placeholder.style.cursor = 'pointer';
      placeholder.addEventListener('click', () => openEmailExcerptDrawer(data));
    } else {
      placeholder.remove();
    }
  } catch {
    const placeholder = document.getElementById('task-source-placeholder');
    if (placeholder) placeholder.remove();
  }
}

function openEmailExcerptDrawer(email) {
  document.getElementById('email-excerpt-subject').textContent = email.subject || '(No Subject)';
  document.getElementById('email-excerpt-meta').textContent =
    `${email.sender}  ·  ${formatEmailDate(email.date)}`;
  const bodyEl = document.getElementById('email-excerpt-body');
  bodyEl.textContent = email.body || '(No body)';
  if (email.source_spans && email.source_spans.length > 0) {
    _applyHighlights(bodyEl, email.source_spans);
  }
  document.getElementById('email-excerpt-overlay').classList.remove('hidden');
  document.getElementById('email-excerpt-drawer').classList.remove('hidden');
}

async function _openEmailFromId(emailId) {
  try {
    const res = await fetch(`${BACKEND_URL}/email/${encodeURIComponent(emailId)}/excerpt`);
    if (!res.ok) { showToast('Email not found'); return; }
    const data = await res.json();
    if (data.error) { showToast('Email not found'); return; }
    openEmailExcerptDrawer(data);
  } catch {
    showToast('Could not load email');
  }
}

function closeEmailExcerptDrawer() {
  document.getElementById('email-excerpt-overlay').classList.add('hidden');
  document.getElementById('email-excerpt-drawer').classList.add('hidden');
}

function closeTaskDetailDrawer() {
  document.getElementById('task-detail-overlay').classList.add('hidden');
  document.getElementById('task-detail-drawer').classList.add('hidden');
}

// ── Left-swipe task → Add to Calendar ────────────────────────────────────────

let _pendingCalendarTask = null;
let _pendingCalendarCard = null;
let _pendingCalendarWrapper = null;

function addTaskToCalendar(task, card, wrapper) {
  const due = task.due && task.due !== 'none' ? task.due : null;
  if (due) {
    _doAddTaskToCalendar(task.title, due, card, wrapper);
  } else {
    openDatePickerModal(task, card, wrapper);
  }
}

async function _doAddTaskToCalendar(title, dateStr, card, wrapper) {
  try {
    const res = await fetch(`${BACKEND_URL}/calendar/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, date: dateStr, user: getUserEmail() })
    });
    const data = await res.json();
    if (data.ok) {
      showToast('Added to calendar ✓');
      if (card && wrapper) {
        card.style.transition = 'transform 0.35s ease, opacity 0.35s ease';
        card.style.transform = 'translateX(-100%)';
        card.style.opacity = '0';
        card.addEventListener('transitionend', () => wrapper.remove(), { once: true });
      }
    } else {
      showToast(`Error: ${data.error || 'Failed'}`);
      if (card) { card.style.transition = 'transform 0.25s ease'; card.style.transform = 'translateX(0)'; }
    }
  } catch (err) {
    showToast(`Error: ${err.message}`);
    if (card) { card.style.transition = 'transform 0.25s ease'; card.style.transform = 'translateX(0)'; }
  }
}

function openDatePickerModal(task, card, wrapper) {
  _pendingCalendarTask = task;
  _pendingCalendarCard = card || null;
  _pendingCalendarWrapper = wrapper || null;
  const today = new Date().toISOString().slice(0, 10);
  document.getElementById('date-picker-task-title').textContent = task.title;
  document.getElementById('date-picker-input').value = today;
  document.getElementById('date-picker-overlay').classList.remove('hidden');
  document.getElementById('date-picker-modal').classList.remove('hidden');

  const confirmBtn = document.getElementById('date-picker-confirm-btn');
  confirmBtn.onclick = async () => {
    const date = document.getElementById('date-picker-input').value;
    if (!date) return;
    const t = _pendingCalendarTask;
    const c = _pendingCalendarCard;
    const w = _pendingCalendarWrapper;
    closeDatePickerModal();
    await _doAddTaskToCalendar(t.title, date, c, w);
  };
}

function closeDatePickerModal() {
  document.getElementById('date-picker-overlay').classList.add('hidden');
  document.getElementById('date-picker-modal').classList.add('hidden');
  _pendingCalendarTask = null;
  _pendingCalendarCard = null;
  _pendingCalendarWrapper = null;
}

// ── Scan for Tasks (Todo Proposals with Swipe) ───────────────────────────────

async function runScanTodos() {
  const btn = document.getElementById('scan-todos-btn');
  const content = document.getElementById('suggested-tasks-content');
  if (!btn || !content) return;

  btn.disabled = true;
  btn.textContent = 'Scanning…';
  content.innerHTML = '<div class="loading">Analyzing emails for action items…</div>';

  try {
    // Collect visible email IDs from the current email list
    const emailIds = [];
    document.querySelectorAll('.email-card-wrapper[data-email-id]').forEach(el => {
      emailIds.push(el.dataset.emailId);
    });

    const res = await fetch(`${BACKEND_URL}/emails/scan-todos`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email_ids: emailIds }),
    });
    if (!res.ok) throw new Error(`Server error ${res.status}`);
    const data = await res.json();
    const todos = data.todos || [];

    content.innerHTML = '';
    if (todos.length === 0) {
      const scanCount = data.scan_count != null ? data.scan_count : emailIds.length;
      content.innerHTML = `<div class="empty-state">Scanned ${scanCount} email${scanCount !== 1 ? 's' : ''} — no action items found.</div>`;
      btn.textContent = 'Scan again';
      btn.disabled = false;
      return;
    }

    todos.forEach(todo => buildTodoProposalCard(content, todo));
    btn.textContent = 'Scan again';
  } catch (err) {
    content.innerHTML = `<div class="empty-state">Scan failed: ${escapeHtml(err.message)}</div>`;
    btn.textContent = 'Try again';
  } finally {
    btn.disabled = false;
  }
}

function buildTodoProposalCard(container, todo) {
  const wrapper = document.createElement('div');
  wrapper.className = 'todo-proposal-wrapper';
  wrapper.innerHTML = '<div class="swipe-todo-action-bg swipe-todo-reject-bg">Dismiss ✕</div>';

  const card = document.createElement('div');
  card.className = 'todo-proposal-card';

  const firstSpan = (todo.source_spans && todo.source_spans.length > 0) ? todo.source_spans[0] : null;
  const spanHtml = firstSpan
    ? `<div class="todo-source-span">"${escapeHtml(firstSpan)}"</div>`
    : '';
  const subjectHtml = todo.email_subject
    ? `<div class="todo-source-email">From: ${escapeHtml(todo.email_subject)}</div>`
    : '';
  const dateHtml = todo.date_expression
    ? `<div class="todo-date">${escapeHtml(todo.date_expression)}</div>`
    : '';

  card.innerHTML = `
    <div class="todo-proposal-title">${escapeHtml(todo.title)}</div>
    ${todo.notes ? `<div class="todo-proposal-notes">${escapeHtml(todo.notes)}</div>` : ''}
    ${dateHtml}
    ${subjectHtml}
    ${spanHtml}
    <div class="todo-proposal-hint">Swipe right to add → | ← Swipe left to dismiss</div>
  `;

  wrapper.appendChild(card);
  container.appendChild(wrapper);
  addSwipeToTodoProposal(wrapper, card, todo);
}

function addSwipeToTodoProposal(wrapper, card, todo) {
  let startX = 0, startY = 0, deltaX = 0;
  let dragging = false, didSwipe = false, axisLocked = false, axisIsHorizontal = false;
  const bgEl = wrapper.querySelector('.swipe-todo-action-bg');

  card.addEventListener('touchstart', (e) => {
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
    dragging = true;
    didSwipe = false;
    axisLocked = false;
    axisIsHorizontal = false;
    deltaX = 0;
    card.style.transition = 'none';
  }, { passive: true });

  card.addEventListener('touchmove', (e) => {
    if (!dragging) return;
    const dx = e.touches[0].clientX - startX;
    const dy = e.touches[0].clientY - startY;
    if (!axisLocked) {
      if (Math.abs(dx) < 5 && Math.abs(dy) < 5) return;
      axisLocked = true;
      axisIsHorizontal = Math.abs(dx) >= Math.abs(dy) * 1.5; // 1.5x threshold prevents diagonal from triggering swipe-to-accept
    }
    if (!axisIsHorizontal) return;
    e.preventDefault();
    deltaX = dx;
    if (Math.abs(deltaX) > 10) didSwipe = true;
    card.style.transform = `translateX(${deltaX}px)`;
    if (bgEl) {
      if (deltaX > 0) {
        bgEl.textContent = 'Add to tasks ✓';
        bgEl.className = 'swipe-todo-action-bg swipe-todo-accept-bg';
      } else {
        bgEl.textContent = 'Dismiss ✕';
        bgEl.className = 'swipe-todo-action-bg swipe-todo-reject-bg';
      }
    }
  }, { passive: false });

  card.addEventListener('touchend', () => {
    if (!dragging) return;
    dragging = false;
    if (deltaX > 80) {
      // Right swipe = Accept — add to tasks
      card.style.transition = 'transform 0.3s ease, opacity 0.3s ease';
      card.style.transform = 'translateX(110%)';
      card.style.opacity = '0';
      card.addEventListener('transitionend', () => wrapper.remove(), { once: true });
      acceptTodoProposal(todo);
    } else if (deltaX < -80) {
      // Left swipe = Reject — dismiss
      card.style.transition = 'transform 0.3s ease, opacity 0.3s ease';
      card.style.transform = 'translateX(-110%)';
      card.style.opacity = '0';
      card.addEventListener('transitionend', () => wrapper.remove(), { once: true });
      rejectTodoProposal(todo);
    } else {
      // Snap back
      card.style.transition = 'transform 0.25s ease';
      card.style.transform = 'translateX(0)';
      if (bgEl) {
        bgEl.textContent = 'Dismiss ✕';
        bgEl.className = 'swipe-todo-action-bg swipe-todo-reject-bg';
      }
    }
    deltaX = 0;
  });

  // Tap (no swipe) on a todo proposal card → open source email excerpt with highlights
  card.addEventListener('click', () => {
    if (didSwipe) return;
    if (todo.email_id) {
      _openEmailFromId(todo.email_id);
    }
  });
}

async function acceptTodoProposal(todo) {
  try {
    await fetch(`${BACKEND_URL}/emails/${encodeURIComponent(todo.email_id)}/accept-todo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        todo_id: todo.id,
        title: todo.title,
        notes: todo.notes || '',
        date_expression: todo.date_expression || null,
        user: currentUser ? currentUser.email : '',
      }),
    });
    showToast('Task added ✓');
  } catch (err) {
    console.error('acceptTodo error:', err);
  }
}

async function rejectTodoProposal(todo) {
  try {
    await fetch(`${BACKEND_URL}/emails/${encodeURIComponent(todo.email_id)}/reject-todo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ todo_id: todo.id }),
    });
  } catch (err) {
    // Rejection is best-effort
  }
}

// ── Morning Briefing ──────────────────────────────────────────────────────────

async function checkMorningBriefing() {
  try {
    const email = currentUser.email;
    const res = await fetch(`${BACKEND_URL}/briefing/latest?user_email=${encodeURIComponent(email)}`);
    const data = await res.json();
    if (data.briefing && !data.briefing.seen && data.briefing.message) {
      showBriefingModal(data.briefing);
    }
  } catch (e) {
    console.error('Briefing check failed:', e);
  }
}

function showBriefingModal(briefing) {
  _currentBriefingId = briefing.id;
  _currentBriefingMessage = briefing.message || '';
  document.getElementById('briefing-body').textContent = _currentBriefingMessage;
  document.getElementById('briefing-overlay').classList.remove('hidden');
  document.getElementById('briefing-modal').classList.remove('hidden');
}

function _closeBriefingModal() {
  document.getElementById('briefing-overlay').classList.add('hidden');
  document.getElementById('briefing-modal').classList.add('hidden');
}

async function _markBriefingSeen(briefingId) {
  if (!briefingId || !currentUser) return;
  try {
    await fetch(`${BACKEND_URL}/briefing/${briefingId}/seen`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_email: currentUser.email }),
    });
  } catch {}
}

async function dismissBriefing() {
  const id = _currentBriefingId;
  _currentBriefingId = null;
  _closeBriefingModal();
  await _markBriefingSeen(id);
}

async function sendBriefingFeedback(rating) {
  const id = _currentBriefingId;
  _currentBriefingId = null;
  _closeBriefingModal();
  if (id && currentUser) {
    try {
      await fetch(`${BACKEND_URL}/briefing/${id}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rating, user_email: currentUser.email }),
      });
    } catch {}
  }
}

function openBriefingChat() {
  const id = _currentBriefingId;
  const message = _currentBriefingMessage;
  _currentBriefingId = null;
  _currentBriefingMessage = '';
  _closeBriefingModal();
  _markBriefingSeen(id);

  // Store briefing message for injection into chat history on the first send
  _briefingContextMessage = message || '';

  // Open chat panel
  openChat();

  // Display the briefing message as Hana's first bubble in the chat
  if (message) {
    setTimeout(() => {
      appendMessage('saucer', message);
      const input = document.getElementById('msg-input');
      if (input) input.focus();
    }, 200);
  }
}

// ── Question Queue Polling ────────────────────────────────────────────────────

let _questionPollingTimer = null;
let _pendingQuestion = null;

async function checkQuestionQueue() {
  try {
    const res = await fetch(`${BACKEND_URL}/hana/question`);
    const data = await res.json();
    const btn = document.getElementById('chat-btn');
    if (data.has_question) {
      _pendingQuestion = data.question;
      btn.classList.add('chat-btn--has-question');
    } else {
      _pendingQuestion = null;
      btn.classList.remove('chat-btn--has-question');
    }
  } catch (e) {
    // Silently ignore — question polling is best-effort
  }
}

function startQuestionPolling() {
  checkQuestionQueue();
  _questionPollingTimer = setInterval(checkQuestionQueue, 5 * 60 * 1000);
}


function _injectQuestionContext(question) {
  // Display Hana's question as a primed assistant message
  const messages = document.getElementById('messages');
  if (!messages) return;
  const bubble = document.createElement('div');
  bubble.className = 'message assistant';
  bubble.textContent = question;
  messages.appendChild(bubble);
  messages.scrollTop = messages.scrollHeight;
  // Add to conversation history so Gemini sees it
  conversationHistory.push({ role: 'assistant', content: question });
}

// ── Hana's Notes Screen ───────────────────────────────────────────────────────

let _currentNoteSlug = null;
let _currentNoteTopic = null;
let _currentNoteContent = null;

async function openNotesScreen() {
  document.getElementById('notes-screen').classList.remove('hidden');
  const body = document.getElementById('notes-screen-body');
  body.innerHTML = '<div class="loading">Loading notes...</div>';

  try {
    const res = await fetch(`${BACKEND_URL}/hana/notes`);
    const data = await res.json();
    const notes = data.notes || [];

    if (notes.length === 0) {
      body.innerHTML = '<p class="notes-empty-state">Nothing here yet — Hana will add notes as she gets to know your household.</p>';
      return;
    }

    body.innerHTML = '';
    notes.forEach(note => {
      const card = document.createElement('div');
      card.className = 'note-card';

      const updated = note.updated_at ? new Date(note.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '';
      const excerpt = (note.content || '').slice(0, 120);

      card.innerHTML = `
        <div class="note-card-topic">${escapeHtml(note.topic)}</div>
        <div class="note-card-excerpt">${escapeHtml(excerpt)}${note.content && note.content.length > 120 ? '…' : ''}</div>
        ${updated ? `<div class="note-card-date">Updated ${updated}</div>` : ''}
      `;
      card.addEventListener('click', () => openNoteDetail(note));
      body.appendChild(card);
    });
  } catch (e) {
    body.innerHTML = '<p class="notes-empty-state">Couldn\'t load notes right now.</p>';
  }
}

function closeNotesScreen() {
  document.getElementById('notes-screen').classList.add('hidden');
}

function openNoteDetail(note) {
  _currentNoteSlug = note.slug;
  _currentNoteTopic = note.topic;
  _currentNoteContent = note.content;

  document.getElementById('note-detail-title').textContent = note.topic;
  const body = document.getElementById('note-detail-body');
  body.innerHTML = `<div class="note-detail-content">${escapeHtml(note.content || '')}</div>`;

  document.getElementById('note-detail-overlay').classList.remove('hidden');
  document.getElementById('note-detail-drawer').classList.remove('hidden');
}

function closeNoteDetailDrawer() {
  document.getElementById('note-detail-overlay').classList.add('hidden');
  document.getElementById('note-detail-drawer').classList.add('hidden');
  _currentNoteSlug = null;
  _currentNoteTopic = null;
  _currentNoteContent = null;
}

async function deleteCurrentNote() {
  if (!_currentNoteSlug) return;
  const topic = _currentNoteTopic || _currentNoteSlug;
  if (!confirm(`Delete note "${topic}"?`)) return;

  try {
    await fetch(`${BACKEND_URL}/hana/notes/${encodeURIComponent(_currentNoteSlug)}`, { method: 'DELETE' });
    closeNoteDetailDrawer();
    showToast('Note deleted');
    openNotesScreen(); // Refresh the list
  } catch (e) {
    showToast('Error deleting note');
  }
}

function chatAboutCurrentNote() {
  const topic = _currentNoteTopic;
  const content = _currentNoteContent;
  closeNoteDetailDrawer();
  closeNotesScreen();
  openChat();

  setTimeout(() => {
    const primedMsg = `[context: user is reviewing the note titled "${topic}". Content: "${(content || '').slice(0, 500)}"]`;
    // Inject Hana's opening as a primed assistant message
    const openingText = `I've been keeping some notes on "${topic}" based on things I've picked up. Want to add anything, correct something, or just talk through it?`;
    const messages = document.getElementById('messages');
    if (messages) {
      const bubble = document.createElement('div');
      bubble.className = 'message assistant';
      bubble.textContent = openingText;
      messages.appendChild(bubble);
      messages.scrollTop = messages.scrollHeight;
    }
    conversationHistory.push({ role: 'user', content: primedMsg });
    conversationHistory.push({ role: 'assistant', content: openingText });
  }, 200);
}

// ── Email Intent ──────────────────────────────────────────────────────────────

async function loadEmailIntent() {
  try {
    const res = await fetch(`${BACKEND_URL}/email-intent`);
    const data = await res.json();
    const input = document.getElementById('intent-input');
    if (input) input.value = data.intent || '';
  } catch (e) {
    console.error('Failed to load intent:', e);
  }
}

async function saveEmailIntent() {
  const input = document.getElementById('intent-input');
  const btn = document.getElementById('intent-save-btn');
  const intent = input ? input.value.trim() : '';
  btn.disabled = true;
  btn.textContent = 'Saving…';
  try {
    await fetch(`${BACKEND_URL}/email-intent`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ intent, user: getUserEmail() }),
    });
    showToast('Intent saved');
    btn.textContent = 'Saved ✓';
    setTimeout(() => { btn.textContent = 'Save'; btn.disabled = false; }, 2000);
  } catch (e) {
    showToast('Error saving intent');
    btn.textContent = 'Save';
    btn.disabled = false;
  }
}

// ── Dismiss Feedback Drawer ───────────────────────────────────────────────────

let _dismissFeedbackEmailId = null;
let _dismissFeedbackWrapper = null;

async function openDismissFeedbackDrawer(emailId, emailSubject, wrapper) {
  _dismissFeedbackEmailId = emailId;
  _dismissFeedbackWrapper = wrapper;

  // Reset form
  document.querySelectorAll('input[name="dismiss-reason"]').forEach(r => r.checked = false);
  document.getElementById('dismiss-feedback-text').value = '';

  // Load topic noun phrase async
  const topicLabel = document.getElementById('dismiss-feedback-topic-label');
  topicLabel.textContent = 'We don\'t do this';

  document.getElementById('dismiss-feedback-overlay').classList.remove('hidden');
  document.getElementById('dismiss-feedback-drawer').classList.remove('hidden');

  // Try to fetch topic label from backend
  try {
    const emails = await fetch(`${BACKEND_URL}/emails/cached`).then(r => r.json()).then(d => d.emails || []);
    const email = emails.find(e => e.id === emailId);
    if (email) {
      const res = await fetch(`${BACKEND_URL}/emails/${encodeURIComponent(emailId)}/topic-phrase`);
      if (res.ok) {
        const data = await res.json();
        if (data.phrase) topicLabel.textContent = `We don't do ${data.phrase}`;
      }
    }
  } catch (e) {
    // Best-effort — label stays as default
  }
}

function closeDismissFeedbackDrawer() {
  document.getElementById('dismiss-feedback-overlay').classList.add('hidden');
  document.getElementById('dismiss-feedback-drawer').classList.add('hidden');
  _dismissFeedbackEmailId = null;
  _dismissFeedbackWrapper = null;
}

async function confirmDismissFeedback() {
  const emailId = _dismissFeedbackEmailId;
  const wrapper = _dismissFeedbackWrapper;
  if (!emailId) return;

  const selected = document.querySelector('input[name="dismiss-reason"]:checked');
  const reasonType = selected ? selected.value : 'free_text';
  const reasonText = reasonType === 'free_text'
    ? document.getElementById('dismiss-feedback-text').value.trim()
    : (reasonType === 'doesnt_apply'
        ? document.getElementById('dismiss-feedback-topic-label').textContent
        : 'We opted out');

  const btn = document.getElementById('dismiss-feedback-confirm-btn');
  btn.disabled = true;

  try {
    await fetch(`${BACKEND_URL}/emails/${encodeURIComponent(emailId)}/dismiss-feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason_type: reasonType, reason_text: reasonText, user: getUserEmail() }),
    });
    closeDismissFeedbackDrawer();
    if (wrapper) {
      const card = wrapper.querySelector('.email-card');
      if (card) {
        card.style.transition = 'transform 0.3s ease, opacity 0.3s ease';
        card.style.transform = 'translateX(-100%)';
        card.style.opacity = '0';
        card.addEventListener('transitionend', () => wrapper.remove(), { once: true });
      } else {
        wrapper.remove();
      }
    }
    showToast('Dismissed');
  } catch (e) {
    showToast('Error dismissing email');
  } finally {
    btn.disabled = false;
  }
}

// ── Dismissed Email Review ────────────────────────────────────────────────────

async function openDismissedReview() {
  document.getElementById('dismissed-review-overlay').classList.remove('hidden');
  document.getElementById('dismissed-review-modal').classList.remove('hidden');
  const body = document.getElementById('dismissed-review-body');
  body.innerHTML = '<p class="empty-state">Re-evaluating against current intent…</p>';

  try {
    const res = await fetch(`${BACKEND_URL}/emails/dismissed-review`);
    const data = await res.json();

    if (data.message) {
      body.innerHTML = `<p class="empty-state">${escapeHtml(data.message)}</p>`;
      return;
    }

    const emails = data.emails || [];
    if (emails.length === 0) {
      body.innerHTML = '<p class="empty-state">No dismissed emails match your current intent. You\'re all good.</p>';
      return;
    }

    body.innerHTML = `<p style="font-size:0.82rem;color:#888;margin-bottom:12px">These emails were dismissed but may match what you care about now. Review and restore anything you want back.</p>`;
    emails.forEach(email => {
      const card = document.createElement('div');
      card.className = 'dismissed-review-card';
      card.dataset.emailId = email.id;
      const dateStr = email.date ? formatEmailDate(email.date) : '';
      card.innerHTML = `
        <div class="dismissed-review-card-meta">${escapeHtml(dateStr)}</div>
        <div class="dismissed-review-card-subject">${escapeHtml(email.subject || '(No Subject)')}</div>
        <div class="dismissed-review-card-sender">${escapeHtml(email.sender || '')}</div>
        <div class="dismissed-review-card-reason">Hana thinks: ${escapeHtml(email.review_reason || email.review_verdict || '')}</div>
        <div class="dismissed-review-actions">
          <button class="dismissed-review-restore-btn">Restore</button>
          <button class="dismissed-review-keep-btn">Keep dismissed</button>
        </div>
      `;
      card.querySelector('.dismissed-review-restore-btn').addEventListener('click', async () => {
        await fetch(`${BACKEND_URL}/emails/${encodeURIComponent(email.id)}/restore`, { method: 'POST' });
        card.remove();
        showToast('Email restored');
        if (!body.querySelector('.dismissed-review-card')) {
          body.innerHTML = '<p class="empty-state">All caught up!</p>';
        }
      });
      card.querySelector('.dismissed-review-keep-btn').addEventListener('click', () => {
        card.remove();
        if (!body.querySelector('.dismissed-review-card')) {
          body.innerHTML = '<p class="empty-state">All caught up!</p>';
        }
      });
      body.appendChild(card);
    });
  } catch (e) {
    body.innerHTML = '<p class="empty-state">Could not load dismissed emails.</p>';
  }
}

function closeDismissedReview() {
  document.getElementById('dismissed-review-overlay').classList.add('hidden');
  document.getElementById('dismissed-review-modal').classList.add('hidden');
}

// ── Relevant Files ────────────────────────────────────────────────────────────

let _allFiles = [];

async function openFilesScreen() {
  document.getElementById('files-screen').classList.remove('hidden');
  await loadFilesList();
}

function closeFilesScreen() {
  document.getElementById('files-screen').classList.add('hidden');
}

function openHanaDismissedScreen() {
  document.querySelectorAll('.screen').forEach(s => s.classList.add('hidden'));
  document.getElementById('hana-dismissed-screen').classList.remove('hidden');
  loadHanaDismissedEmails();
}

function closeHanaDismissedScreen() {
  document.getElementById('hana-dismissed-screen').classList.add('hidden');
}

async function loadHanaDismissedEmails() {
  const list = document.getElementById('hana-dismissed-list');
  list.innerHTML = '<div class="loading">Loading…</div>';
  try {
    const res = await fetch(`${BACKEND_URL}/emails/hana-dismissed`);
    const data = await res.json();
    const emails = (data.emails || []).sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0));
    if (emails.length === 0) {
      list.innerHTML = '<div class="empty-state">Nothing here — Hana hasn\'t dismissed anything recently, or everything looks right.</div>';
      return;
    }
    list.innerHTML = '';
    emails.forEach(email => {
      const card = document.createElement('div');
      card.className = 'hana-dismissed-card';
      card.style.cursor = 'pointer';
      const dateStr = email.date ? formatEmailDate(email.date) : '';
      const reasonText = email.reason || '';
      const truncatedReason = reasonText.length > 120 ? reasonText.slice(0, 120) + '…' : reasonText;
      card.innerHTML = `
        <div class="hana-dismissed-card-meta">${escapeHtml(dateStr)}</div>
        <div class="hana-dismissed-card-subject">${escapeHtml(email.subject || '(No Subject)')}</div>
        <div class="hana-dismissed-card-sender">${escapeHtml(email.sender || '')}</div>
        ${truncatedReason ? `<span class="hana-dismissed-reason-pill">${escapeHtml(truncatedReason)}</span>` : ''}
        <div style="margin-top:8px">
          <button class="dismissed-review-restore-btn" style="width:100%">Restore to inbox</button>
        </div>
      `;
      card.querySelector('.dismissed-review-restore-btn').addEventListener('click', async (e) => {
        e.stopPropagation();
        await fetch(`${BACKEND_URL}/emails/${encodeURIComponent(email.id)}/restore`, { method: 'POST' });
        card.remove();
        showToast('Email restored to inbox');
        if (!list.querySelector('.hana-dismissed-card')) {
          list.innerHTML = '<div class="empty-state">Nothing here — Hana hasn\'t dismissed anything recently, or everything looks right.</div>';
        }
      });
      card.addEventListener('click', async () => {
        try {
          const res = await fetch(`${BACKEND_URL}/email/${encodeURIComponent(email.id)}/excerpt`);
          const data = await res.json();
          openReviewedEmailDrawer({ ...email, ...data });
        } catch {
          openReviewedEmailDrawer(email);
        }
      });
      list.appendChild(card);
    });
  } catch (e) {
    list.innerHTML = '<div class="empty-state">Could not load dismissed emails.</div>';
  }
}

async function loadFilesList() {
  const content = document.getElementById('files-list-content');
  content.innerHTML = '<p class="empty-state">Loading files…</p>';
  try {
    const res = await fetch(`${BACKEND_URL}/files`);
    const data = await res.json();
    _allFiles = data.files || [];
    renderFilesList(_allFiles);
  } catch (e) {
    content.innerHTML = '<p class="empty-state">Could not load files.</p>';
  }
}

function renderFilesList(files) {
  const content = document.getElementById('files-list-content');
  content.innerHTML = '';
  if (files.length === 0) {
    content.innerHTML = '<p class="empty-state">No files yet. Upload one or attach a PDF from an email.</p>';
    return;
  }
  files.forEach(file => {
    const row = document.createElement('div');
    row.className = 'file-row';
    const icon = file.filename.match(/\.pdf$/i) ? '📄' : file.filename.match(/\.(jpg|jpeg|png)$/i) ? '🖼️' : '📎';
    const size = file.size_bytes > 1024 * 1024
      ? `${(file.size_bytes / 1024 / 1024).toFixed(1)} MB`
      : `${Math.round(file.size_bytes / 1024)} KB`;
    const date = file.uploaded_at ? new Date(file.uploaded_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '';
    const source = file.source === 'email' ? 'from email' : 'uploaded';
    row.innerHTML = `
      <span class="file-row-icon">${icon}</span>
      <div class="file-row-info">
        <div class="file-row-name" title="${escapeHtml(file.filename)}">${escapeHtml(file.filename)}</div>
        <div class="file-row-meta">${source} · ${size}${date ? ' · ' + date : ''}</div>
      </div>
      <div class="file-row-actions">
        <button class="file-view-btn">View</button>
        <button class="file-delete-btn">Delete</button>
      </div>
    `;
    row.querySelector('.file-view-btn').addEventListener('click', () => {
      window.open(`${BACKEND_URL}/files/${encodeURIComponent(file.file_id)}/download`, '_blank');
    });
    row.querySelector('.file-delete-btn').addEventListener('click', async () => {
      if (!confirm(`Delete "${file.filename}"?`)) return;
      try {
        await fetch(`${BACKEND_URL}/files/${encodeURIComponent(file.file_id)}`, { method: 'DELETE' });
        showToast('File deleted');
        loadFilesList();
      } catch (e) { showToast('Error deleting file'); }
    });
    content.appendChild(row);
  });
}

function filterFilesList() {
  const q = (document.getElementById('files-search').value || '').toLowerCase();
  if (!q) { renderFilesList(_allFiles); return; }
  const filtered = _allFiles.filter(f =>
    f.filename.toLowerCase().includes(q) ||
    (f.content_text || '').toLowerCase().includes(q)
  );
  renderFilesList(filtered);
}

async function handleFileUpload(e) {
  const file = e.target.files[0];
  if (!file) return;
  e.target.value = '';

  const formData = new FormData();
  formData.append('file', file);

  showToast('Uploading…');
  try {
    const res = await fetch(`${BACKEND_URL}/files/upload`, { method: 'POST', body: formData });
    const data = await res.json();
    if (data.error) { showToast(`Error: ${data.error}`); return; }
    showToast(`Uploaded: ${data.filename}`);
    loadFilesList();
  } catch (e) {
    showToast('Upload failed');
  }
}

// ── Avatar crop ────────────────────────────────────────────────────────────────────────────

let _avatarCropState = null;

function openAvatarCropModal() {
  document.getElementById('avatar-crop-overlay').classList.remove('hidden');
  document.getElementById('avatar-crop-modal').classList.remove('hidden');
}

function closeAvatarCropModal() {
  document.getElementById('avatar-crop-overlay').classList.add('hidden');
  document.getElementById('avatar-crop-modal').classList.add('hidden');
  _avatarCropState = null;
  document.getElementById('avatar-crop-img').src = '';
  document.getElementById('avatar-save-btn').disabled = true;
}

function onAvatarFileChosen(e) {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (ev) => {
    const img = document.getElementById('avatar-crop-img');
    img.onload = () => {
      const vp = 260;
      const scale = Math.max(vp / img.naturalWidth, vp / img.naturalHeight);
      _avatarCropState = { scale, offsetX: 0, offsetY: 0 };
      _applyAvatarTransform();
      document.getElementById('avatar-save-btn').disabled = false;
      _wireAvatarDrag();
    };
    img.src = ev.target.result;
  };
  reader.readAsDataURL(file);
  e.target.value = '';
}

function _applyAvatarTransform() {
  const { scale, offsetX, offsetY } = _avatarCropState;
  document.getElementById('avatar-crop-img').style.transform =
    `translate(${offsetX}px, ${offsetY}px) scale(${scale})`;
}

function _wireAvatarDrag() {
  const vpEl = document.getElementById('avatar-crop-viewport');
  let dragging = false, lastX = 0, lastY = 0;

  vpEl.addEventListener('pointerdown', (e) => {
    dragging = true; lastX = e.clientX; lastY = e.clientY;
    vpEl.setPointerCapture(e.pointerId);
  });
  vpEl.addEventListener('pointermove', (e) => {
    if (!dragging || !_avatarCropState) return;
    _avatarCropState.offsetX += e.clientX - lastX;
    _avatarCropState.offsetY += e.clientY - lastY;
    lastX = e.clientX; lastY = e.clientY;
    _applyAvatarTransform();
  });
  vpEl.addEventListener('pointerup', () => { dragging = false; });

  vpEl.addEventListener('wheel', (e) => {
    if (!_avatarCropState) return;
    e.preventDefault();
    _avatarCropState.scale = Math.max(0.5, Math.min(5, _avatarCropState.scale - e.deltaY * 0.002));
    _applyAvatarTransform();
  }, { passive: false });
}

async function saveAvatarCrop() {
  if (!_avatarCropState) return;
  const saveBtn = document.getElementById('avatar-save-btn');
  saveBtn.disabled = true;
  saveBtn.textContent = 'Saving…';

  try {
    const canvas = document.createElement('canvas');
    canvas.width = 260; canvas.height = 260;
    const ctx = canvas.getContext('2d');
    ctx.beginPath();
    ctx.arc(130, 130, 130, 0, Math.PI * 2);
    ctx.clip();
    const img = document.getElementById('avatar-crop-img');
    const { scale, offsetX, offsetY } = _avatarCropState;
    ctx.drawImage(img, offsetX, offsetY, img.naturalWidth * scale, img.naturalHeight * scale);

    const blob = await new Promise(res => canvas.toBlob(res, 'image/jpeg', 0.88));
    const formData = new FormData();
    formData.append('file', blob, 'avatar.jpg');
    formData.append('user', getUserEmail());

    const res = await fetch(`${BACKEND_URL}/avatar`, { method: 'POST', body: formData });
    if (!res.ok) throw new Error('Upload failed');

    const reader = new FileReader();
    reader.onload = (ev) => {
      const btn = document.getElementById('avatar-btn');
      btn.style.backgroundImage = `url(${ev.target.result})`;
      btn.style.backgroundSize = 'cover';
      btn.style.backgroundPosition = 'center';
      document.getElementById('avatar-initial').style.display = 'none';
    };
    reader.readAsDataURL(blob);

    showToast('Photo saved');
    closeAvatarCropModal();
  } catch (err) {
    showToast('Could not save photo');
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = 'Save';
  }
}

