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
    } catch (error) {
      $('matrix-overview').textContent = `Matrix overview unavailable: ${error.message}`;
    }
  }
  $('run-academic-benchmark').addEventListener('click', async () => {
    const button = $('run-academic-benchmark');
    const status = $('academic-benchmark-status');
    button.disabled = true;
    status.textContent = 'Running local policy checks and a synthetic hash workload; physical measures are not included.';
    try {
      const response = await fetch('/api/aristotle/academic-benchmarks', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: '{}',
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status}).`);
      }
      if (!['LOCAL_POLICY_TESTS_PASS_NOT_CERTIFICATION', 'LOCAL_POLICY_TESTS_FAILED']
        .includes(data.benchmark_status)) {
        throw new Error('Benchmark returned an unrecognized status.');
      }
      $('academic-benchmark-report').textContent = JSON.stringify(data, null, 2);
      status.textContent = `${data.benchmark_status} · ${data.policy_cases_passed}/${data.policy_case_count} policy cases passed. Physical performance and recovery were not measured.`;
    } catch (error) {
      status.textContent = `Benchmark unavailable: ${error.message}`;
    } finally {
      button.disabled = false;
    }
  });
  $('matrix-refresh').addEventListener('click', refreshMatrix);
  document.querySelector('[data-tab="matrix"]').addEventListener('click', () => {
    void refreshMatrix();
    void refreshEquilibrium();
  });
  $('matrix-open-quantum-circuit').addEventListener('click', () => {
    document.querySelector('.tab[data-tab="formula"]').click();
    $('circuit-qubits').focus();
  });
  function renderEquilibrium(snapshot) {
    $('equilibrium-summary').textContent =
      `${snapshot.active_branches} branches · average vitality ${snapshot.average_vitality} · ` +
      `${snapshot.composted_count} composted · zero-harm invariant ` +
      `${snapshot.zero_harm_verified ? 'verified' : 'FAILED'} · vitality floor ${snapshot.vitality_floor}.`;
    const body = $('equilibrium-branches');
    body.replaceChildren();
    for (const branch of snapshot.branches) {
      const row = document.createElement('tr');
      for (const value of [
        branch.branch_id,
        branch.domain,
        `${(branch.vitality * 100).toFixed(1)}%`,
        String(branch.energy_draw),
        String(branch.harm_index),
        branch.is_stale ? 'Stale' : 'Active'
      ]) {
        const cell = document.createElement('td');
        cell.textContent = value;
        row.append(cell);
      }
      body.append(row);
    }
    const compost = $('equilibrium-compost');
    compost.replaceChildren();
    for (const item of snapshot.compost_archive) {
      const row = document.createElement('li');
      row.textContent = `${item.recycled_id} · ${item.domain} · ${item.reason}`;
      compost.append(row);
    }
  }
  async function equilibriumRequest(path, payload) {
    const response = await fetch(path, {
      method: payload === undefined ? 'GET' : 'POST',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        ...(payload === undefined ? {} : { 'Content-Type': 'application/json' })
      },
      ...(payload === undefined ? {} : { body: JSON.stringify(payload) })
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status}).`);
    }
    return data;
  }
  async function refreshEquilibrium() {
    $('equilibrium-status').textContent = 'Loading in-memory equilibrium…';
    try {
      renderEquilibrium(await equilibriumRequest('/api/aristotle/equilibrium'));
      $('equilibrium-status').textContent = 'Equilibrium snapshot refreshed. State is held only in this app process.';
    } catch (error) {
      $('equilibrium-status').textContent = `Equilibrium unavailable: ${error.message}`;
    }
  }
  $('equilibrium-refresh').addEventListener('click', refreshEquilibrium);
  $('equilibrium-register-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    $('equilibrium-status').textContent = 'Checking zero-harm admission…';
    try {
      const result = await equilibriumRequest('/api/aristotle/equilibrium/branches', {
        branch_id: $('equilibrium-branch-id').value,
        domain: $('equilibrium-domain').value,
        vitality: Number($('equilibrium-vitality').value),
        energy_draw: Number($('equilibrium-energy').value),
        harm_index: Number($('equilibrium-harm').value),
        is_stale: $('equilibrium-stale').checked
      });
      renderEquilibrium(result.snapshot);
      $('equilibrium-status').textContent = result.registered
        ? 'Branch admitted.'
        : 'Branch rejected: harm_index must be exactly zero.';
      if (result.registered) form.reset();
    } catch (error) {
      $('equilibrium-status').textContent = `Branch registration failed: ${error.message}`;
    }
  });
  $('equilibrium-nurture').addEventListener('click', async () => {
    $('equilibrium-status').textContent = 'Advancing active branches…';
    try {
      const result = await equilibriumRequest('/api/aristotle/equilibrium/nurture', {
        boost_amount: 0.08
      });
      renderEquilibrium(result.snapshot);
      $('equilibrium-status').textContent = result.notes.join(' ') || 'No branches advanced.';
    } catch (error) {
      $('equilibrium-status').textContent = `Advancement failed: ${error.message}`;
    }
  });
  const pruneDialog = $('equilibrium-prune-dialog');
  $('equilibrium-prune').addEventListener('click', () => pruneDialog.showModal());
  pruneDialog.addEventListener('close', async () => {
    const choice = pruneDialog.returnValue;
    pruneDialog.returnValue = '';
    if (choice !== 'prune') return;
    $('equilibrium-status').textContent = 'Pruning simulator branches…';
    try {
      const result = await equilibriumRequest('/api/aristotle/equilibrium/prune', {});
      renderEquilibrium(result.snapshot);
      $('equilibrium-status').textContent = result.notes.join(' ') || 'No branches met the prune criteria.';
    } catch (error) {
      $('equilibrium-status').textContent = `Pruning failed: ${error.message}`;
    }
  });
})();
