const BACKEND_URL = 'https://saucer-backend-987132498395.us-central1.run.app';

let activeUser = null;
let conversationHistory = [];

const userSelect  = document.getElementById('user-select');
const chatPanel   = document.getElementById('chat-panel');
const activeLabel = document.getElementById('active-user-label');
const messages    = document.getElementById('messages');
const msgInput    = document.getElementById('msg-input');
const sendBtn     = document.getElementById('send-btn');

document.querySelectorAll('.user-btn').forEach(btn => {
  btn.addEventListener('click', () => selectUser(btn.dataset.user));
});

document.getElementById('switch-user').addEventListener('click', () => {
  chatPanel.classList.add('hidden');
  userSelect.classList.remove('hidden');
  activeUser = null;
  conversationHistory = [];
});

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
