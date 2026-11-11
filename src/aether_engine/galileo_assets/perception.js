(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const video = $('camera-preview');
  const start = $('camera-start');
  const stop = $('camera-stop');
  const status = $('camera-status');
  let stream = null;
  let generation = 0;
  let timer = null;
  let controller = null;

  async function request(path, options = {}) {
    const response = await fetch(path, {
      method: options.method || 'GET',
      credentials: 'same-origin',
      headers: options.body === undefined ? { Accept: 'application/json' } :
        { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal
    });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status}).`);
    return data;
  }

  function stopCamera(message = 'Camera off.') {
    generation += 1;
    clearTimeout(timer);
    if (controller) controller.abort();
    controller = null;
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stream = null;
    video.srcObject = null;
    start.disabled = false;
    stop.disabled = true;
    status.textContent = message;
  }

  async function observe(current) {
    if (!stream || current !== generation) return;
    if (!video.videoWidth || !video.videoHeight) {
      timer = setTimeout(() => observe(current), 500);
      return;
    }
    const canvas = document.createElement('canvas');
    const ratio = Math.min(1, 640 / video.videoWidth);
    canvas.width = Math.max(1, Math.round(video.videoWidth * ratio));
    canvas.height = Math.max(1, Math.round(video.videoHeight * ratio));
    const context = canvas.getContext('2d');
    if (!context) { stopCamera('Camera image processing is unavailable.'); return; }
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const data = canvas.toDataURL('image/jpeg', 0.7).split(',')[1];
    controller = new AbortController();
    try {
      const result = await request('/api/perception/analyze', {
        method: 'POST', signal: controller.signal,
        body: { image: { name: 'camera.jpg', media_type: 'image/jpeg', data } }
      });
      if (current !== generation) return;
      $('camera-observation').textContent = `${result.observation} (Updated ${new Date(result.observed_at).toLocaleTimeString()})`;
      status.textContent = 'Camera on. Observations update after each analysis.';
      timer = setTimeout(() => observe(current), 10000);
    } catch (error) {
      if (current !== generation) return;
      stopCamera(`Camera stopped: ${error.message}`);
    } finally {
      if (current === generation) controller = null;
    }
  }

  start.addEventListener('click', async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      status.textContent = 'Camera access is not available in this webview. Try the browser preview.';
      return;
    }
    start.disabled = true;
    stop.disabled = false;
    const current = ++generation;
    try {
      const acquired = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      if (current !== generation) { acquired.getTracks().forEach((track) => track.stop()); return; }
      stream = acquired;
      video.srcObject = stream;
      stream.getVideoTracks().forEach((track) => track.addEventListener('ended', () => {
        if (current === generation) stopCamera('Camera disconnected or permission was revoked.');
      }));
      status.textContent = 'Camera on. Starting local analysis.';
      await video.play();
      void observe(current);
    } catch (error) {
      if (current === generation) stopCamera(`Camera could not start: ${error.message}`);
    }
  });
  stop.addEventListener('click', () => stopCamera());
  window.addEventListener('galileo-camera-stop', () => stopCamera());
  window.addEventListener('pagehide', () => stopCamera());

  async function loadFeedback() {
    const list = $('camera-feedback-list');
    try {
      const entries = await request('/api/perception/feedback');
      list.replaceChildren();
      entries.forEach((entry) => {
        const row = document.createElement('li');
        const text = document.createElement('span');
        text.textContent = entry.content;
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.textContent = 'Delete';
        remove.setAttribute('aria-label', `Delete preference: ${entry.content}`);
        remove.addEventListener('click', async () => {
          try {
            await request(`/api/perception/feedback/${entry.id}`, { method: 'DELETE', body: {} });
            await loadFeedback();
            $('camera-feedback-status').textContent = 'Preference deleted.';
          } catch (error) { $('camera-feedback-status').textContent = `Delete failed: ${error.message}`; }
        });
        row.append(text, remove);
        list.append(row);
      });
    } catch (error) { $('camera-feedback-status').textContent = `Preferences unavailable: ${error.message}`; }
  }
  window.addEventListener('galileo-camera-open', () => { void loadFeedback(); });
  $('camera-feedback-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await request('/api/perception/feedback', { method: 'POST', body: { content: $('camera-feedback').value } });
      $('camera-feedback').value = '';
      await loadFeedback();
      $('camera-feedback-status').textContent = 'Preference saved locally.';
    } catch (error) { $('camera-feedback-status').textContent = `Save failed: ${error.message}`; }
  });
})();
