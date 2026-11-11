(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  async function get(path) {
    const response = await fetch(path, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status}).`);
    return data;
  }
  $('history-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    $('history-status').textContent = 'Searching local archive…';
    $('history-results').replaceChildren();
    try {
      const data = await get(`/api/aristotle/history?q=${encodeURIComponent($('history-query').value)}`);
      for (const record of data.records) {
        const item = document.createElement('li');
        const heading = document.createElement('strong');
        heading.textContent = `${record.name} · ${record.region} · ${record.start_year}${record.end_year === null ? '' : ` to ${record.end_year}`}`;
        const description = document.createElement('p');
        description.textContent = record.description;
        item.append(heading, description);
        $('history-results').append(item);
      }
      $('history-status').textContent = `${data.records.length} records found. Historical records are unverified.`;
    } catch (error) {
      $('history-status').textContent = `Archive search failed: ${error.message}`;
    }
  });
  async function refreshMatrix() {
    $('matrix-overview').textContent = 'Loading Matrix overview…';
    try {
      const data = await get('/api/aristotle/matrix');
      const latest = data.latest_simulation;
      $('matrix-overview').textContent = latest
        ? `Latest simulated state: ${latest.system_status || 'unknown'} · epoch ${latest.epoch ?? 'unknown'}.`
        : 'No simulated telemetry recorded.';
      const chart = data.allocations;
      $('governor-allocations').replaceChildren();
      chart.labels.forEach((name, index) => {
        const row = document.createElement('tr');
        const label = document.createElement('th');
        label.scope = 'row';
        label.textContent = name;
        const value = document.createElement('td');
        value.textContent = String(chart.datasets[0].data[index].value_raw);
        row.append(label, value);
        $('governor-allocations').append(row);
      });
      $('governor-summary').textContent = `Estimated total ${chart.metadata.estimated_total_gb} GB; reference ${chart.metadata.reference_threshold_gb} GB. Not measured or enforced.`;
    } catch (error) {
      $('matrix-overview').textContent = `Matrix overview unavailable: ${error.message}`;
    }
  }
  $('matrix-refresh').addEventListener('click', refreshMatrix);
  document.querySelector('[data-tab="matrix"]').addEventListener('click', refreshMatrix);
  $('governor-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    $('governor-result').textContent = 'Simulating route…';
    try {
      const response = await fetch('/api/aristotle/governor/route', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ task_description: $('governor-task').value, domain: $('governor-domain').value, execution_payload: {} }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : `Request failed (${response.status}).`);
      $('governor-result').textContent = `${result.status} · ${result.assigned_node}: ${result.message}`;
    } catch (error) {
      $('governor-result').textContent = `Routing simulation failed: ${error.message}`;
    }
  });
})();
