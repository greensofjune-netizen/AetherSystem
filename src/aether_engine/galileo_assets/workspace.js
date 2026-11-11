(() => {
  'use strict';

  const maxBytes = 1_500_000;
  const maxRecords = 100;
  const input = document.getElementById('workspace-json');
  const fileInput = document.getElementById('workspace-file');
  const byteCount = document.getElementById('workspace-byte-count');
  const status = document.getElementById('workspace-status');
  const results = document.getElementById('workspace-results');
  const resultHeading = document.getElementById('workspace-result-heading');
  const resultRows = document.getElementById('workspace-result-rows');
  const previewButton = document.getElementById('workspace-preview');
  const importButton = document.getElementById('workspace-import');

  function showStatus(message, isError = false) {
    status.textContent = message;
    status.classList.toggle('workspace-error', isError);
  }

  function updateByteCount() {
    const bytes = new TextEncoder().encode(input.value).length;
    byteCount.textContent = `${bytes.toLocaleString()} / ${maxBytes.toLocaleString()} bytes`;
    input.setAttribute('aria-invalid', String(bytes > maxBytes));
    if (bytes > maxBytes) showStatus('The JSON input exceeds the 1.5 MB limit.', true);
    return bytes;
  }

  function parseRecords() {
    if (updateByteCount() > maxBytes) {
      throw new Error('The JSON input exceeds the 1.5 MB limit.');
    }
    let records;
    try {
      records = JSON.parse(input.value);
    } catch (error) {
      throw new Error(`Invalid JSON: ${error.message}`);
    }
    if (!Array.isArray(records) || records.length === 0) {
      throw new Error('Enter a non-empty JSON array of records.');
    }
    if (records.length > maxRecords) {
      throw new Error(`Imports may contain at most ${maxRecords} records.`);
    }
    if (records.some((record) => record === null || typeof record !== 'object' || Array.isArray(record))) {
      throw new Error('Every array item must be a JSON object.');
    }
    return records;
  }

  function renderResults(data) {
    resultRows.replaceChildren();
    for (const event of data.events) {
      const row = document.createElement('tr');
      const outcome = document.createElement('td');
      const identifier = document.createElement('td');
      const summary = document.createElement('td');
      outcome.textContent = event.ethical_clearance ? 'Cleared' : 'Blocked';
      identifier.textContent = event.event_id;
      summary.textContent = event.payload_summary;
      row.append(outcome, identifier, summary);
      resultRows.append(row);
    }
    resultHeading.textContent = `${data.cleared_count} cleared · ${data.blocked_count} blocked`;
    results.hidden = false;
  }

  async function processRecords(dryRun) {
    previewButton.disabled = true;
    importButton.disabled = true;
    showStatus(dryRun ? 'Checking records locally…' : 'Saving cleared summaries locally…');
    results.hidden = true;
    try {
      const response = await fetch('/api/workspace/import', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify({ records: parseRecords(), dry_run: dryRun })
      });
      let data;
      try {
        data = await response.json();
      } catch (_) {
        throw new Error(`The server returned an invalid response (HTTP ${response.status}).`);
      }
      if (!response.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (HTTP ${response.status}).`);
      }
      if (!Array.isArray(data.events) || typeof data.cleared_count !== 'number' || typeof data.blocked_count !== 'number') {
        throw new Error('The server returned an invalid import result.');
      }
      renderResults(data);
      showStatus(dryRun
        ? 'Preview complete. No records were written.'
        : `${data.cleared_count} cleared record(s) stored in the local Aether database; blocked records were not stored.`);
    } catch (error) {
      showStatus(error.message || 'The import could not be completed.', true);
    } finally {
      previewButton.disabled = false;
      importButton.disabled = false;
    }
  }

  input.addEventListener('input', () => {
    updateByteCount();
    results.hidden = true;
  });

  fileInput.addEventListener('change', async () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    if (file.size > maxBytes) {
      showStatus('The selected JSON file exceeds the 1.5 MB limit.', true);
      fileInput.value = '';
      return;
    }
    try {
      input.value = await file.text();
      updateByteCount();
      results.hidden = true;
      showStatus(`${file.name} loaded into the editor. Nothing has been sent or saved.`);
    } catch (error) {
      showStatus(`Could not read the selected file: ${error.message}`, true);
    }
  });

  previewButton.addEventListener('click', () => void processRecords(true));
  importButton.addEventListener('click', () => void processRecords(false));
  document.getElementById('workspace-clear').addEventListener('click', () => {
    input.value = '';
    fileInput.value = '';
    results.hidden = true;
    resultRows.replaceChildren();
    updateByteCount();
    showStatus('Editor cleared. No records were imported.');
    input.focus();
  });

  updateByteCount();
})();
