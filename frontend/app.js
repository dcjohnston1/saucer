const BACKEND_URL = 'https://saucer-backend-987132498395.us-central1.run.app';

let activeUser = null;
let conversationHistory = [];

const userSelect  = document.getElementById('user-select');
const chatPanel   = document.getElementById('chat-panel');
const activeLabel = document.getElementById('active-user-label');
const messages    = document.getElementById('messages');
const msgInput    = document.getElementById('msg-input');
const sendBtn     = document.getElementById('send-btn');
const homeDocContent = document.getElementById('home-doc-content');

document.querySelectorAll('.user-btn').forEach(btn => {
  btn.addEventListener('click', () => selectUser(btn.dataset.user));
});

document.getElementById('switch-user').addEventListener('click', () => {
  chatPanel.classList.add('hidden');
  userSelect.classList.remove('hidden');
  activeUser = null;
  conversationHistory = [];
  loadHomeList();
});

async function loadHomeList() {
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
      const card = document.createElement('div');
      card.className = 'task-card';
      
      let dateHtml = '';
      if (task.due && task.due !== 'none') {
        dateHtml = `<span class="task-due">📅 ${task.due}</span>`;
      }

      card.innerHTML = `
        <div class="task-main">
          <div class="task-title">${task.title}</div>
          ${dateHtml}
        </div>
        ${task.notes ? `<div class="task-notes">${task.notes}</div>` : ''}
      `;
      homeDocContent.appendChild(card);
    });
  } catch (err) {
    homeDocContent.textContent = `Error: ${err.message}`;
  }
}

// Initial load
loadHomeList();

sendBtn.addEventListener('click', sendMessage);
msgInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

function selectUser(user) {
  activeUser = user;
  activeLabel.textContent = user.charAt(0).toUpperCase() + user.slice(1);
  userSelect.classList.add('hidden');
  chatPanel.classList.remove('hidden');
  msgInput.focus();
}

async function sendMessage() {
  const text = msgInput.value.trim();
  if (!text) return;

  appendMessage(activeUser, text);
  msgInput.value = '';
  sendBtn.disabled = true;

  const typing = appendMessage('saucer', '…', true);

  try {
    const res = await fetch(`${BACKEND_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user: activeUser, message: text, history: conversationHistory })
    });

    if (!res.ok) throw new Error(`Server error ${res.status}`);
    const data = await res.json();
    typing.remove();
    appendMessage('saucer', data.reply);
    
    if (data.model) {
      document.getElementById('model-info').textContent = `Powered by ${data.model}`;
    }

    conversationHistory.push(
      { role: 'user',      content: `${activeUser}: ${text}` },
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
  const bubble = document.createElement('div');
  bubble.className = `bubble ${sender === 'saucer' ? 'saucer' : 'user'}`;
  if (isTyping) bubble.classList.add('typing');
  bubble.textContent = text;
  messages.appendChild(bubble);
  messages.scrollTop = messages.scrollHeight;
  return bubble;
}
