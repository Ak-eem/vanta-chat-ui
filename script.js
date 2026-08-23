/* Socket-backed Vanta chat with an offline demo fallback. */
const BACKEND_URL = 'http://localhost:5000';

(() => {
  'use strict';

  const $ = (selector) => document.querySelector(selector);
  const messages = $('#messages');
  const form = $('#messageForm');
  const input = $('#messageInput');
  const sendButton = form.querySelector('.send-button');
  const brainStrip = $('#brainStrip');
  const brainDot = $('#brainDot');
  const brainStatus = $('#brainStatus');
  const statusSource = $('#statusSource');
  const connectionPill = $('#connectionPill');
  const connectionDot = connectionPill.querySelector('.connection-dot');
  const connectionText = $('#connectionText');
  const thinkingToggle = $('#thinkingToggle');
  const modeButtons = [...document.querySelectorAll('.mode-button')];
  const clearButton = $('#clearButton');

  let mode = 'chat';
  let socket = null;
  let demoMode = false;
  let demoTimers = new Set();
  const responseKeys = new Set();

  const timestamp = () => new Intl.DateTimeFormat([], { hour: '2-digit', minute: '2-digit' }).format(new Date());

  function setConnection(label, state) {
    connectionText.textContent = label;
    connectionDot.className = `connection-dot ${state}`;
  }

  function setBrainStatus(state, message, source = 'Socket.IO') {
    const safeState = ['online', 'idle'].includes(String(state).toLowerCase()) ? 'online'
      : ['thinking', 'busy'].includes(String(state).toLowerCase()) ? 'thinking' : 'fallback';
    brainStrip.className = `brain-strip ${safeState}`;
    brainDot.className = `status-dot ${safeState}`;
    brainStatus.textContent = message || (safeState === 'thinking' ? 'nemotron: thinking…' : safeState === 'fallback' ? 'r1: fallback' : 'idle');
    statusSource.textContent = source;
  }

  function clearDemoTimers() {
    demoTimers.forEach((timer) => window.clearTimeout(timer));
    demoTimers = new Set();
  }

  function addMessage(kind, text) {
    const article = document.createElement('article');
    article.className = `message ${kind === 'user' ? 'user-message' : 'vanta-message'}`;
    const meta = document.createElement('div');
    meta.className = 'message-meta';
    const avatar = document.createElement('span');
    avatar.className = 'avatar';
    avatar.textContent = kind === 'user' ? 'Y' : 'V';
    const author = document.createElement('strong');
    author.textContent = kind === 'user' ? 'You' : 'Vanta';
    const time = document.createElement('time');
    time.textContent = timestamp();
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = text;
    meta.append(avatar, author, time);
    article.append(meta, bubble);
    messages.append(article);
    article.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }

  function extractResponse(payload) {
    if (typeof payload === 'string') return payload;
    if (!payload || typeof payload !== 'object') return '';
    return payload.message || payload.response || payload.text || payload.content || payload.data?.message || '';
  }

  function responseKey(payload, text) {
    if (payload && typeof payload === 'object' && (payload.id || payload.requestId || payload.messageId)) {
      return String(payload.id || payload.requestId || payload.messageId);
    }
    return `${text}|${messages.children.length}`;
  }

  function renderResponse(payload) {
    const text = extractResponse(payload);
    if (!text) return;
    const key = responseKey(payload, text);
    if (responseKeys.has(key)) return;
    responseKeys.add(key);
    addMessage('vanta', text);
    setBrainStatus('idle', 'idle');
    sendButton.disabled = false;
  }

  function demoReply(message) {
    const lower = message.toLowerCase();
    const reply = lower.includes('hello') || lower.includes('hi')
      ? 'Hello. I am running in local demo mode, but the conversation flow is ready.'
      : mode === 'task'
        ? `Demo plan: I would break “${message}” into clear steps, validate the constraints, then report the result.`
        : mode === 'orchestrate'
          ? `Demo orchestration: I would route “${message}” through the available specialists and merge their strongest signals.`
          : `Demo response: I received “${message}”. Connect the Vanta backend at ${BACKEND_URL} for a live model response.`;
    const timer = window.setTimeout(() => {
      demoTimers.delete(timer);
      addMessage('vanta', reply);
      setBrainStatus('idle', 'offline — demo mode', 'Demo fallback');
      sendButton.disabled = false;
    }, 650);
    demoTimers.add(timer);
  }

  function useDemoMode() {
    demoMode = true;
    setConnection('offline · demo', 'offline');
    setBrainStatus('fallback', 'offline — demo mode', 'Demo fallback');
  }

  function connectSocket() {
    if (typeof window.io !== 'function') {
      useDemoMode();
      return;
    }
    socket = window.io(BACKEND_URL, { autoConnect: true, reconnection: true });
    socket.on('connect', () => {
      demoMode = false;
      clearDemoTimers();
      setConnection('connected', 'online');
      setBrainStatus('online', 'flash: online');
    });
    socket.on('disconnect', () => {
      useDemoMode();
    });
    socket.on('connect_error', () => {
      useDemoMode();
    });
    socket.on('status', (payload = {}) => {
      const state = payload.state || 'idle';
      setBrainStatus(state, payload.message);
    });
    socket.on('response', renderResponse);
  }

  function emitMessage(message) {
    const think = mode === 'task' ? true : thinkingToggle.checked;
    if (!socket || !socket.connected || demoMode) {
      useDemoMode();
      setBrainStatus('thinking', 'offline — demo mode', 'Demo fallback');
      demoReply(message);
      return;
    }
    sendButton.disabled = true;
    setBrainStatus('thinking', 'nemotron: thinking…');
    if (mode === 'orchestrate') {
      socket.emit('orchestrate', { message });
    } else {
      socket.emit('chat', { message, think });
    }
  }

  function resizeInput() {
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 130)}px`;
  }

  modeButtons.forEach((button) => {
    button.addEventListener('click', () => {
      mode = button.dataset.mode;
      modeButtons.forEach((item) => {
        const active = item === button;
        item.classList.toggle('active', active);
        item.setAttribute('aria-pressed', String(active));
      });
      const isTask = mode === 'task';
      thinkingToggle.disabled = isTask;
      thinkingToggle.closest('.thinking-control').setAttribute('aria-label', isTask ? 'Task mode always uses thinking' : 'Toggle thinking');
    });
  });

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message || sendButton.disabled) return;
    addMessage('user', message);
    input.value = '';
    resizeInput();
    emitMessage(message);
  });

  input.addEventListener('input', resizeInput);
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  clearButton.addEventListener('click', () => {
    clearDemoTimers();
    messages.replaceChildren();
    responseKeys.clear();
    setBrainStatus(demoMode ? 'fallback' : 'online', demoMode ? 'offline — demo mode' : 'idle', demoMode ? 'Demo fallback' : 'Socket.IO');
    sendButton.disabled = false;
  });

  connectSocket();
})();
