(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const allowedExtensions = new Set(['txt', 'md', 'py', 'js', 'ts', 'json', 'csv', 'log', 'html', 'css', 'yaml', 'yml', 'toml']);
  const maxMessageChars = 8000;
  const maxFileBytes = 60000;
  const maxTotalBytes = 120000;
  const maxFiles = 10;
  const maxImages = 4;
  const maxImageBytes = 2000000;
  const maxTotalImageBytes = 6000000;
  const encoder = new TextEncoder();
  const state = { conversation: null, conversations: [], attachments: [], images: [], visionModels: new Set(), messageImageUrls: [], busy: false, reading: false, loadingChat: false, loadVersion: 0, modelStatusPolls: 0, voiceUnsupported: false, controller: null, stopped: false, dictating: false, desktop: false };
  const elements = {
    list: $('conversation-list'), title: $('chat-title'), messages: $('messages'), model: $('model'),
    form: $('chat-form'), message: $('message'), send: $('send'), files: $('files'), attachments: $('attachments'),
    images: $('images'), imageLabel: $('image-label'), imageHint: $('image-hint'), voiceInput: $('voice-input'),
    voiceStatus: $('voice-status'), modelStatus: $('model-status'),
    error: $('chat-error'), attachmentError: $('attachment-error'), clearInvalid: $('clear-invalid-files'),
    messageCount: $('message-count'),
    newChat: $('new-chat'), refresh: $('refresh'), stop: $('stop-response'),
    retry: $('retry'), progress: $('chat-progress'), nativeVoice: $('native-voice-input')
  };

  function showError(element, message) {
    element.textContent = message || '';
    element.hidden = !message;
  }

  async function api(path, options = {}) {
    const controller = options.controller || new AbortController();
    const timer = options.timeout ? setTimeout(() => controller.abort(), options.timeout) : null;
    try {
      const response = await fetch(path, {
        method: options.method || 'GET',
        credentials: 'same-origin',
        headers: options.body === undefined ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: controller.signal
      });
      let data;
      try { data = await response.json(); } catch (_) { throw new Error(`The server returned an invalid response (HTTP ${response.status}).`); }
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (HTTP ${response.status}).`);
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('The request timed out. Your draft and attachments are still here; the server may still finish the request.');
      throw error;
    } finally {
      if (timer !== null) clearTimeout(timer);
    }
  }

  function updateControls() {
    const blocked = state.busy || state.reading || state.loadingChat || state.dictating;
    const hasImages = state.images.length > 0 || state.conversation?.messages?.some((message) => message.images?.length);
    const incompatibleImages = hasImages && !state.visionModels.has(elements.model.value);
    elements.send.disabled = blocked || !elements.clearInvalid.hidden || !elements.model.value || incompatibleImages;
    elements.send.textContent = state.busy ? 'Sending…' : 'Send ↑';
    elements.form.setAttribute('aria-busy', String(state.busy));
    elements.message.disabled = state.busy || state.loadingChat;
    elements.model.disabled = blocked || !elements.model.options.length || !elements.model.options[0].value;
    elements.files.disabled = blocked;
    const supportsVision = state.visionModels.has(elements.model.value);
    elements.images.disabled = blocked || !supportsVision;
    elements.imageLabel.setAttribute('aria-disabled', String(blocked || !supportsVision));
    elements.imageHint.textContent = supportsVision
      ? 'Vision model · up to 4 images, 2 MB each.'
      : hasImages ? 'This conversation contains images; select a vision model to continue.' : 'Select a model with vision support to attach images.';
    elements.voiceInput.disabled = blocked || state.voiceUnsupported;
    elements.nativeVoice.disabled = (blocked && !state.dictating) || !state.desktop;
    elements.nativeVoice.textContent = state.dictating ? 'Finish voice input' : 'Start on-device voice';
    elements.stop.hidden = !state.busy;
    elements.stop.disabled = !state.controller || state.stopped;
    elements.retry.disabled = blocked;
    elements.newChat.disabled = blocked;
    document.body.classList.toggle('busy', state.busy || state.loadingChat);
    document.body.classList.toggle('reading', state.reading);
    elements.list.querySelectorAll('button').forEach((button) => { button.disabled = blocked; });
    elements.attachments.querySelectorAll('button').forEach((button) => { button.disabled = blocked; });
  }

  function revokeImageUrls(images) {
    for (const image of images) {
      if (image.previewUrl) URL.revokeObjectURL(image.previewUrl);
    }
  }

  function imageBytes(data) {
    const binary = atob(data);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return bytes;
  }

  async function fileToBase64(file) {
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = '';
    for (let offset = 0; offset < bytes.length; offset += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
    }
    return btoa(binary);
  }

  function updateMessageCount() {
    const characters = Array.from(elements.message.value);
    if (characters.length > maxMessageChars) {
      elements.message.value = characters.slice(0, maxMessageChars).join('');
    }
    elements.messageCount.textContent = `${Math.min(characters.length, maxMessageChars).toLocaleString()} / 8,000 characters`;
    updateControls();
  }

  function renderList() {
    elements.list.replaceChildren();
    if (!state.conversations.length) {
      const empty = document.createElement('p');
      empty.className = 'sidebar-hint';
      empty.textContent = 'No saved conversations yet.';
      elements.list.append(empty);
    }
    for (const conversation of state.conversations) {
      const row = document.createElement('div');
      row.className = 'conversation-row';
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'conversation';
      button.textContent = conversation.title || 'New conversation';
      button.title = conversation.title || 'New conversation';
      if (state.conversation && state.conversation.id === conversation.id) {
        button.classList.add('active');
        button.setAttribute('aria-current', 'true');
      }
      button.addEventListener('click', () => openConversation(conversation.id));
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'conversation-delete';
      remove.textContent = '×';
      remove.setAttribute('aria-label', `Delete ${conversation.title || 'New conversation'}`);
      remove.title = 'Delete conversation';
      remove.addEventListener('click', () => deleteConversation(conversation));
      row.append(button, remove);
      elements.list.append(row);
    }
    updateControls();
  }

  async function deleteConversation(conversation) {
    if (state.busy || state.reading || state.loadingChat) return;
    const title = conversation.title || 'New conversation';
    if (!window.confirm(`Delete "${title}"? This cannot be undone.`)) return;
    state.loadingChat = true;
    updateControls();
    showError(elements.error, '');
    try {
      await api(`/api/conversations/${encodeURIComponent(conversation.id)}`, {
        method: 'DELETE',
        body: {}
      });
      state.conversations = state.conversations.filter((item) => item.id !== conversation.id);
      if (state.conversation && state.conversation.id === conversation.id) {
        state.conversation = null;
      }
      renderConversation();
      try {
        await refreshList();
      } catch (error) {
        showError(elements.error, `Conversation deleted, but the list could not be refreshed: ${error.message}`);
      }
    } catch (error) {
      showError(elements.error, `Could not delete conversation: ${error.message}`);
    } finally {
      state.loadingChat = false;
      updateControls();
    }
  }

  function renderConversation() {
    const conversation = state.conversation;
    state.messageImageUrls.forEach((url) => URL.revokeObjectURL(url));
    state.messageImageUrls = [];
    elements.title.textContent = conversation ? (conversation.title || 'New conversation') : 'A little more clarity.';
    elements.messages.replaceChildren();
    const messages = conversation && Array.isArray(conversation.messages) ? conversation.messages : [];
    if (!messages.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      const symbol = document.createElement('div');
      symbol.className = 'empty-symbol';
      symbol.setAttribute('aria-hidden', 'true');
      symbol.textContent = '✦';
      const heading = document.createElement('h3');
      heading.textContent = 'Where shall we begin?';
      const description = document.createElement('p');
      description.textContent = 'Bring a question, an idea, or a little curiosity.';
      empty.append(symbol, heading, description);
      elements.messages.append(empty);
    }
    for (const message of messages) {
      if (message.role !== 'user' && message.role !== 'assistant') continue;
      const row = document.createElement('article');
      row.className = `message ${message.role}`;
      const avatar = document.createElement('span');
      avatar.className = 'avatar';
      avatar.setAttribute('aria-hidden', 'true');
      avatar.textContent = message.role === 'user' ? 'Y' : '✦';
      const bubble = document.createElement('div');
      bubble.className = 'bubble';
      const label = document.createElement('span');
      label.className = 'message-label';
      label.textContent = message.role === 'user' ? 'YOU' : document.title.toUpperCase();
      const text = document.createElement('div');
      text.className = 'message-text';
      text.textContent = message.content;
      bubble.append(label, text);
      for (const image of Array.isArray(message.images) ? message.images : []) {
        if (typeof image.data !== 'string' || typeof image.media_type !== 'string') continue;
        const preview = document.createElement('img');
        preview.className = 'message-image';
        preview.alt = `Attached image: ${image.name || 'image'}`;
        preview.src = URL.createObjectURL(new Blob([imageBytes(image.data)], { type: image.media_type }));
        state.messageImageUrls.push(preview.src);
        bubble.append(preview);
      }
      if (message.role === 'assistant') {
        const actions = document.createElement('div');
        actions.className = 'message-actions';
        const speak = document.createElement('button');
        speak.type = 'button';
        speak.className = 'speak-button';
        speak.textContent = 'Read response aloud';
        speak.addEventListener('click', async () => {
          try {
            if (state.desktop) {
              const result = await window.pywebview.api.speak(message.content);
              if (!result.ok) throw new Error(result.error);
            } else if (!window.AetherSpeech.speak(message.content)) {
              throw new Error('Speech output is unavailable in this browser.');
            }
          } catch (error) {
            showError(elements.error, `Could not read response: ${error.message}`);
          }
        });
        const copy = document.createElement('button');
        copy.type = 'button';
        copy.className = 'speak-button';
        copy.textContent = 'Copy response';
        copy.addEventListener('click', async () => {
          try {
            await navigator.clipboard.writeText(message.content);
            elements.progress.textContent = 'Response copied.';
          } catch (error) {
            showError(elements.error, `Could not copy response: ${error.message}`);
          }
        });
        actions.append(speak, copy);
        bubble.append(actions);
      }
      row.append(avatar, bubble);
      elements.messages.append(row);
    }
    elements.messages.scrollTop = elements.messages.scrollHeight;
    renderList();
  }

  function renderAttachments() {
    elements.attachments.replaceChildren();
    state.attachments.forEach((attachment, index) => {
      const item = document.createElement('li');
      item.className = 'attachment';
      const name = document.createElement('span');
      name.className = 'attachment-name';
      name.textContent = `${attachment.name} (${attachment.bytes.toLocaleString()} bytes)`;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = '×';
      remove.setAttribute('aria-label', `Remove ${attachment.name}`);
      remove.addEventListener('click', () => {
        state.attachments.splice(index, 1);
        renderAttachments();
      });
      item.append(name, remove);
      elements.attachments.append(item);
    });
    state.images.forEach((image, index) => {
      const item = document.createElement('li');
      item.className = 'attachment image-attachment';
      const preview = document.createElement('img');
      preview.className = 'attachment-preview';
      preview.src = image.previewUrl;
      preview.alt = `Preview: ${image.name}`;
      const name = document.createElement('span');
      name.className = 'attachment-name';
      name.textContent = `${image.name} (${image.bytes.toLocaleString()} bytes)`;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = '×';
      remove.setAttribute('aria-label', `Remove ${image.name}`);
      remove.addEventListener('click', () => {
        URL.revokeObjectURL(image.previewUrl);
        state.images.splice(index, 1);
        renderAttachments();
      });
      item.append(preview, name, remove);
      elements.attachments.append(item);
    });
    updateControls();
  }

  async function refreshList() {
    const conversations = await api('/api/conversations');
    if (!Array.isArray(conversations)) throw new Error('The server returned an invalid conversation list.');
    state.conversations = conversations;
    renderList();
  }

  async function refreshModels() {
    const result = await api('/api/models');
    if (!Array.isArray(result.models)) throw new Error('The server returned an invalid model list.');
    state.visionModels = new Set(Array.isArray(result.vision_models) ? result.vision_models : []);
    const selected = elements.model.value;
    const availableModels = result.models.filter((model) => typeof model === 'string' && model);
    elements.model.replaceChildren();
    for (const model of availableModels) {
      const option = document.createElement('option');
      option.value = model;
      option.textContent = model;
      elements.model.append(option);
    }
    if (!elements.model.options.length) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = 'No models available';
      elements.model.append(option);
    } else if (availableModels.includes(selected)) {
      elements.model.value = selected;
    } else if (availableModels.includes(result.default_model)) {
      elements.model.value = result.default_model;
    }
    updateControls();
  }

  async function refreshModelStatus() {
    try {
      const result = await api('/api/model/status');
      const messages = {
        pending: 'Waiting for the local model to start…',
        loading: `Loading ${result.model || 'local model'} into memory…`,
        ready: `${result.model || 'Local model'} is ready.`,
        unavailable: `Local model unavailable: ${result.error || 'Ollama could not load the configured model.'}`,
      };
      elements.modelStatus.textContent = result.status === 'unavailable'
        ? `Local model unavailable: ${result.detail || 'Ollama could not load the configured model.'}`
        : messages[result.status] || `Local model status: ${result.status || 'unknown'}.`;
      if (['pending', 'loading'].includes(result.status) && state.modelStatusPolls < 150) {
        state.modelStatusPolls += 1;
        window.setTimeout(refreshModelStatus, 2000);
      }
    } catch (error) {
      elements.modelStatus.textContent = `Could not check local model status: ${error.message}`;
    }
  }

  async function refresh() {
    elements.refresh.disabled = true;
    $('connection-status').textContent = 'Checking connection';
    $('connection-dot').className = 'status-dot';
    const [health, models, conversations] = await Promise.allSettled([api('/health'), refreshModels(), refreshList()]);
    const online = health.status === 'fulfilled' && models.status === 'fulfilled';
    $('connection-status').textContent = online ? 'Connected locally' : 'Connection unavailable';
    $('connection-dot').className = `status-dot ${online ? 'online' : 'offline'}`;
    const errors = [];
    if (health.status === 'rejected') errors.push(`Connection: ${health.reason.message}`);
    if (models.status === 'rejected') errors.push(`Models: ${models.reason.message}`);
    if (conversations.status === 'rejected') errors.push(`Conversations: ${conversations.reason.message}`);
    showError(elements.error, errors.join(' '));
    elements.refresh.disabled = false;
  }

  async function openConversation(id) {
    if (state.busy || state.reading || state.loadingChat) return;
    const version = ++state.loadVersion;
    state.loadingChat = true;
    updateControls();
    showError(elements.error, '');
    try {
      const conversation = await api(`/api/conversations/${encodeURIComponent(id)}`);
      if (version === state.loadVersion) {
        state.conversation = conversation;
        renderConversation();
      }
    } catch (error) {
      showError(elements.error, `Could not open conversation: ${error.message}`);
    } finally {
      state.loadingChat = false;
      updateControls();
    }
  }

  elements.newChat.addEventListener('click', () => {
    if (state.busy || state.reading || state.loadingChat) return;
    state.conversation = null;
    showError(elements.error, '');
    renderConversation();
    elements.message.focus();
  });
  elements.refresh.addEventListener('click', refresh);
  elements.message.addEventListener('input', updateMessageCount);
  elements.message.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      if (event.isComposing || event.keyCode === 229) return;
      event.preventDefault();
      if (!elements.send.disabled) elements.form.requestSubmit();
    }
  });
  elements.model.addEventListener('change', updateControls);
  window.AetherSpeech.attachRecognition(elements.voiceInput, elements.message, elements.voiceStatus);
  state.voiceUnsupported = elements.voiceInput.disabled;
  elements.retry.addEventListener('click', () => elements.form.requestSubmit());
  elements.stop.addEventListener('click', async () => {
    if (!state.controller || !state.conversation || state.stopped) return;
    elements.stop.disabled = true;
    try {
      const result = await api(`/api/conversations/${encodeURIComponent(state.conversation.id)}/stop`, { method: 'POST', body: {} });
      if (result.cancelled) {
        state.stopped = true;
        state.controller.abort();
      } else {
        elements.progress.textContent = 'The response has finished or has not started yet.';
      }
    } catch (error) {
      showError(elements.error, `Could not stop response: ${error.message}`);
    } finally {
      updateControls();
    }
  });
  $('stop-speaking').addEventListener('click', async () => {
    try {
      if (state.desktop) {
        const result = await window.pywebview.api.stop_speaking();
        if (!result.ok) throw new Error(result.error);
      } else {
        window.AetherSpeech.stopSpeaking();
      }
      elements.voiceStatus.textContent = 'Reading aloud stopped.';
    } catch (error) {
      showError(elements.error, error.message);
    }
  });
  elements.nativeVoice.addEventListener('click', async () => {
    if (state.dictating) {
      elements.nativeVoice.disabled = true;
      try {
        const result = await window.pywebview.api.stop_dictation();
        if (!result.ok) throw new Error(result.error);
      } catch (error) {
        elements.voiceStatus.textContent = `Could not finish voice input: ${error.message}`;
        elements.nativeVoice.disabled = false;
      }
      return;
    }
    try {
      state.dictating = true;
      updateControls();
      elements.voiceStatus.textContent = 'Requesting on-device dictation. Speak after microphone permission; finish when ready.';
      const result = await window.pywebview.api.dictation();
      if (!result.ok) throw new Error(result.error);
      elements.message.value += `${elements.message.value ? ' ' : ''}${result.text}`;
      updateMessageCount();
      elements.voiceStatus.textContent = 'On-device transcript added. Review it before sending.';
    } catch (error) {
      elements.voiceStatus.textContent = `Voice input failed: ${error.message}`;
    } finally {
      state.dictating = false;
      updateControls();
    }
  });
  window.addEventListener('pywebviewready', async () => {
    state.desktop = true;
    elements.voiceInput.hidden = true;
    elements.nativeVoice.hidden = false;
    elements.voiceStatus.textContent = 'On-device dictation requires macOS microphone and speech permission.';
    updateControls();
    try {
      const result = await window.pywebview.api.matrix_status();
      $('matrix-status').textContent = result.available ? `MATRIX / Automator linked to ${result.project}` : `Linked project unavailable: ${result.project}`;
      $('matrix-test').disabled = !result.available;
      $('matrix-backup').disabled = !result.available;
    } catch (error) {
      $('matrix-status').textContent = `Could not connect desktop actions: ${error.message}`;
    }
  });
  for (const action of ['test', 'backup']) {
    $(`matrix-${action}`).addEventListener('click', async () => {
      $('matrix-test').disabled = true;
      $('matrix-backup').disabled = true;
      $('matrix-result').textContent = 'Waiting for macOS confirmation and the action result…';
      try {
        const result = await window.pywebview.api.run_matrix_action(action);
        if (!result.ok) throw new Error(result.error);
        $('matrix-result').textContent = `${action === 'test' ? 'Project tests' : 'Local backup'} completed; outcome recorded in Matrix.`;
      } catch (error) {
        $('matrix-result').textContent = `Action did not complete: ${error.message}`;
      } finally {
        $('matrix-test').disabled = false;
        $('matrix-backup').disabled = false;
      }
    });
  }
  elements.clearInvalid.addEventListener('click', () => {
    elements.files.value = '';
    elements.clearInvalid.hidden = true;
    showError(elements.attachmentError, '');
    updateControls();
  });

  elements.files.addEventListener('change', async () => {
    const files = Array.from(elements.files.files);
    if (!files.length) return;
    state.reading = true;
    updateControls();
    showError(elements.attachmentError, '');
    try {
      if (state.attachments.length + files.length > maxFiles) {
        throw new Error('Attachments exceed the 10-file limit.');
      }
      const additions = [];
      let total = state.attachments.reduce((sum, item) => sum + item.bytes, 0);
      for (const file of files) {
        const extension = file.name.includes('.') ? file.name.split('.').pop().toLowerCase() : '';
        if (!allowedExtensions.has(extension)) throw new Error(`${file.name}: unsupported file type. Choose a supported text file.`);
        if (file.size > maxFileBytes + 3) throw new Error(`${file.name}: exceeds the 60,000 UTF-8-byte per-file limit.`);
        const buffer = await file.arrayBuffer();
        let content;
        try { content = new TextDecoder('utf-8', { fatal: true }).decode(buffer); }
        catch (_) { throw new Error(`${file.name}: not valid UTF-8 text.`); }
        if (/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(content)) throw new Error(`${file.name}: appears to contain binary data.`);
        const bytes = encoder.encode(content).length;
        if (bytes > maxFileBytes) throw new Error(`${file.name}: exceeds the 60,000 UTF-8-byte per-file limit.`);
        total += bytes;
        if (total > maxTotalBytes) throw new Error('Attachments exceed the 120,000 UTF-8-byte total limit.');
        additions.push({ name: file.name, content, bytes });
      }
      state.attachments.push(...additions);
      elements.files.value = '';
      elements.clearInvalid.hidden = true;
      renderAttachments();
    } catch (error) {
      showError(elements.attachmentError, error.message || 'Could not read the selected files.');
      elements.clearInvalid.hidden = false;
    } finally {
      state.reading = false;
      updateControls();
    }
  });

  elements.images.addEventListener('change', async () => {
    const files = Array.from(elements.images.files || []);
    if (!files.length) return;
    state.reading = true;
    updateControls();
    showError(elements.attachmentError, '');
    const additions = [];
    try {
      if (!state.visionModels.has(elements.model.value)) {
        throw new Error('Select a model with vision support before attaching images.');
      }
      if (state.images.length + files.length > maxImages) {
        throw new Error(`Attach no more than ${maxImages} images.`);
      }
      let total = state.images.reduce((sum, image) => sum + image.bytes, 0);
      for (const file of files) {
        if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
          throw new Error(`${file.name}: choose a JPEG, PNG, or WebP image.`);
        }
        if (file.size < 1 || file.size > maxImageBytes) {
          throw new Error(`${file.name}: each image must be no larger than 2 MB.`);
        }
        total += file.size;
        if (total > maxTotalImageBytes) {
          throw new Error('Images exceed the 6 MB total limit.');
        }
        additions.push({
          name: file.name,
          media_type: file.type,
          data: await fileToBase64(file),
          bytes: file.size,
          previewUrl: URL.createObjectURL(file),
        });
      }
      state.images.push(...additions);
      elements.clearInvalid.hidden = true;
      renderAttachments();
    } catch (error) {
      revokeImageUrls(additions);
      showError(elements.attachmentError, error.message || 'Could not read the selected images.');
      elements.clearInvalid.hidden = false;
    } finally {
      elements.images.value = '';
      state.reading = false;
      updateControls();
    }
  });

  elements.form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const message = elements.message.value;
    const model = elements.model.value;
    if (state.busy || state.reading || state.loadingChat || state.dictating || !elements.clearInvalid.hidden || !message.trim() || !model || elements.send.disabled) return;
    if (Array.from(message).length > maxMessageChars) {
      showError(elements.error, 'Messages must be 8,000 characters or fewer.');
      return;
    }
    state.busy = true;
    state.stopped = false;
    elements.retry.hidden = true;
    elements.progress.textContent = 'Generating a local response…';
    updateControls();
    showError(elements.error, '');
    try {
      if (!state.conversation) {
        const created = await api('/api/conversations', { method: 'POST', body: { title: 'New conversation' } });
        state.conversation = { ...created, messages: [] };
        renderConversation();
      }
      state.controller = new AbortController();
      updateControls();
      const result = await api(`/api/conversations/${encodeURIComponent(state.conversation.id)}/messages`, {
        method: 'POST', controller: state.controller,
        body: {
          message,
          model,
          ...($('include-history') ? { include_history: $('include-history').checked } : {}),
          attachments: state.attachments.map(({ name, content }) => ({ name, content })),
          images: state.images.map(({ name, media_type, data }) => ({ name, media_type, data })),
        }
      });
      if (!result.conversation || !Array.isArray(result.conversation.messages)) throw new Error('The server returned an invalid conversation.');
      state.conversation = result.conversation;
      elements.message.value = '';
      updateMessageCount();
      elements.files.value = '';
      state.attachments = [];
      revokeImageUrls(state.images);
      state.images = [];
      showError(elements.attachmentError, '');
      renderAttachments();
      renderConversation();
      elements.progress.textContent = 'Response saved locally.';
      elements.modelStatus.textContent = `${model} is ready.`;
      try { await refreshList(); }
      catch (error) { showError(elements.error, `Message sent, but conversations could not be refreshed: ${error.message}`); }
    } catch (error) {
      elements.retry.hidden = false;
      elements.progress.textContent = state.stopped ? 'Response stopped. Your draft and attachments are preserved; retry when ready.' : 'Message failed. Your draft and attachments are preserved.';
      showError(elements.error, state.stopped ? '' : `Could not send message: ${error.message}`);
      // A conversation may have been created before the message failed.
      try { await refreshList(); } catch (_) { /* Keep the original error visible. */ }
    } finally {
      state.busy = false;
      state.controller = null;
      updateControls();
    }
  });

  function removeBootstrapTokenFromHistory() {
    const url = new URL(window.location.href);
    for (const key of Array.from(url.searchParams.keys())) {
      const normalizedKey = key.toLowerCase().replace(/[-_]/g, '');
      if (normalizedKey === 'token' || normalizedKey === 'bootstraptoken') url.searchParams.delete(key);
    }
    if (url.href !== window.location.href) {
      window.history.replaceState(window.history.state, document.title, `${url.pathname}${url.search}${url.hash}`);
    }
  }

  document.querySelectorAll('.tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      const selected = tab.dataset.tab;
      document.querySelectorAll('.tab').forEach((item) => {
        const active = item === tab;
        item.classList.toggle('active', active);
        if (active) item.setAttribute('aria-current', 'page');
        else item.removeAttribute('aria-current');
      });
      for (const name of ['chat', 'weather', 'stargazer', 'astrology', 'formula', 'workspace', 'propulsion', 'perception', 'matrix', 'history']) {
        const panel = $(`${name}-panel`);
        if (panel) panel.hidden = name !== selected;
      }
      if (selected !== 'perception') window.dispatchEvent(new Event('galileo-camera-stop'));
      else window.dispatchEvent(new Event('galileo-camera-open'));
      if (selected === 'weather' || selected === 'stargazer') {
        const frame = $(`${selected}-frame`);
        if (!frame.hasAttribute('src')) frame.src = `/${selected}`;
      }
      if (selected === 'propulsion' && !$('propulsion-results').dataset.loaded) {
        void loadPropulsion();
      }
    });
  });

  let propulsionRequest = 0;
  async function loadPropulsion() {
    const request = ++propulsionRequest;
    const query = $('propulsion-query').value;
    const results = $('propulsion-results');
    const links = $('propulsion-lineage');
    const status = $('propulsion-status');
    try {
      const data = await api(`/api/propulsion/references?q=${encodeURIComponent(query)}`);
      if (request !== propulsionRequest) return;
      results.replaceChildren();
      links.replaceChildren();
      for (const reference of data.references) {
        const row = document.createElement('li');
        const name = document.createElement('strong');
        name.textContent = reference.name;
        const description = document.createElement('p');
        description.textContent = reference.description;
        const source = document.createElement('p');
        source.textContent = reference.source_url
          ? `Source: ${reference.source_title} — ${reference.source_url}`
          : 'No source recorded; unverified.';
        row.append(name, description, source);
        results.append(row);
      }
      for (const link of data.lineage) {
        const row = document.createElement('li');
        row.textContent = `${link.parent_id} → ${link.child_id}: ${link.description} Source: ${link.source_url}`;
        links.append(row);
      }
      status.textContent = `${data.references.length} reference(s) found.`;
      results.dataset.loaded = 'true';
    } catch (error) {
      if (request !== propulsionRequest) return;
      status.textContent = `Unable to load references: ${error.message}`;
    }
  }

  $('propulsion-search').addEventListener('submit', (event) => {
    event.preventDefault();
    void loadPropulsion();
  });

  updateControls();
  updateMessageCount();
  void refreshModelStatus();
  if (document.readyState === 'complete') removeBootstrapTokenFromHistory();
  else window.addEventListener('load', removeBootstrapTokenFromHistory, { once: true });
  refresh();
})();
