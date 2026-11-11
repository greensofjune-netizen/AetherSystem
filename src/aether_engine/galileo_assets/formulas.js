(() => {
  'use strict';

  const calculators = [
    {
      id: 'quantum',
      endpoint: '/api/formulas/quantum',
      required: [
        'risk_coefficient',
        'fluctuation_velocity',
        'state_density',
        'wave_coherence_percent',
        'entropy_index'
      ],
      labels: {
        risk_coefficient: 'Risk coefficient',
        fluctuation_velocity: 'Fluctuation velocity',
        state_density: 'State density',
        wave_coherence_percent: 'Wave coherence',
        entropy_index: 'Entropy index'
      },
      format(key, value) {
        if (key === 'wave_coherence_percent') return `${value.toFixed(1)}%`;
        if (key === 'fluctuation_velocity') return `${value.toFixed(1)} Hz`;
        return value.toFixed(1);
      }
    },
    {
      id: 'spin',
      endpoint: '/api/formulas/spin-network',
      required: [
        'num_links',
        'seed',
        'mean_spin',
        'boundary_area_planck_squared',
        'entanglement_entropy_nats'
      ],
      labels: {
        num_links: 'Boundary links',
        seed: 'Random seed',
        mean_spin: 'Mean spin',
        boundary_area_planck_squared: 'Boundary area',
        entanglement_entropy_nats: 'Entanglement entropy'
      },
      format(key, value) {
        if (key === 'boundary_area_planck_squared') return `${value.toFixed(4)} ℓₚ²`;
        if (key === 'entanglement_entropy_nats') return `${value.toFixed(4)} nats`;
        return Number.isInteger(value) ? String(value) : value.toFixed(3);
      }
    },
    {
      id: 'los',
      endpoint: '/api/formulas/los-link',
      required: [
        'distance_km',
        'max_radio_horizon_km',
        'earth_bulge_m',
        'fresnel_60pct_clearance_m',
        'required_mast_height_m',
        'average_antenna_height_m',
        'antenna_height_margin_m',
        'free_space_path_loss_db',
        'frequency_ghz',
        'los_status'
      ],
      labels: {
        distance_km: 'Great-circle distance',
        max_radio_horizon_km: 'Combined radio horizon',
        earth_bulge_m: 'Midpoint Earth bulge',
        fresnel_60pct_clearance_m: '60% Fresnel clearance',
        required_mast_height_m: 'Required average mast height',
        average_antenna_height_m: 'Actual average antenna height',
        antenna_height_margin_m: 'Antenna height margin',
        free_space_path_loss_db: 'Free-space path loss',
        frequency_ghz: 'Frequency',
        los_status: 'Path estimate'
      },
      format(key, value) {
        if (key === 'distance_km' || key === 'max_radio_horizon_km') return `${value.toFixed(3)} km`;
        if (key === 'free_space_path_loss_db') return `${value.toFixed(2)} dB`;
        if (key === 'frequency_ghz') return `${value.toFixed(3)} GHz`;
        if (key === 'los_status') return value === 'CLEAR_LOS_ESTIMATE'
          ? 'Clear by this estimate'
          : 'Obstructed or out of estimated range';
        return `${value.toFixed(2)} m`;
      }
    }
  ];

  function node(name, className, text) {
    const element = document.createElement(name);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function responseError(data, status) {
    if (typeof data?.detail === 'string') return data.detail;
    if (Array.isArray(data?.detail)) {
      const details = data.detail.map((item) => item.msg).filter(Boolean);
      if (details.length) return details.join(' ');
    }
    return `Calculation failed (HTTP ${status}).`;
  }

  function renderResults(calculator, data, result) {
    if (!data || typeof data !== 'object' ||
        calculator.required.some((key) => data[key] === undefined)) {
      throw new Error('The server returned incomplete calculation results.');
    }
    result.replaceChildren();
    for (const key of calculator.required) {
      const value = data[key];
      if (typeof value !== 'number' && typeof value !== 'string') {
        throw new Error('The server returned an invalid calculation result.');
      }
      const formatted = calculator.format(key, value);
      result.append(
        node('dt', '', calculator.labels[key]),
        node('dd', '', formatted)
      );
    }
    result.hidden = false;
  }

  for (const calculator of calculators) {
    const form = document.getElementById(`${calculator.id}-form`);
    const error = document.getElementById(`${calculator.id}-error`);
    const status = document.getElementById(`${calculator.id}-status`);
    const result = document.getElementById(`${calculator.id}-result`);
    const submit = form.querySelector('button[type="submit"]');

    form.addEventListener('input', () => {
      if (!error.hidden) {
        error.hidden = true;
        error.textContent = '';
      }
    });

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      error.hidden = true;
      error.textContent = '';
      result.hidden = true;
      status.textContent = 'Calculating on this device…';
      submit.disabled = true;
      form.setAttribute('aria-busy', 'true');
      const payload = Object.fromEntries(new FormData(form).entries());
      for (const [key, value] of Object.entries(payload)) {
        payload[key] = Number(value);
      }

      try {
        const response = await fetch(form.action, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
          cache: 'no-store',
          body: JSON.stringify(payload)
        });
        let data;
        try {
          data = await response.json();
        } catch {
          throw new Error(`The server returned an invalid response (HTTP ${response.status}).`);
        }
        if (!response.ok) throw new Error(responseError(data, response.status));
        renderResults(calculator, data, result);
        status.textContent = calculator.id === 'los' && data.los_status
          ? `Estimate complete: ${calculator.format('los_status', data.los_status)}.`
          : 'Calculation complete. Results were not saved.';
      } catch (requestError) {
        status.textContent = '';
        error.textContent = requestError.message || 'Could not complete the calculation.';
        error.hidden = false;
        error.focus();
      } finally {
        submit.disabled = false;
        form.removeAttribute('aria-busy');
      }
    });
  }

  const circuitForm = document.getElementById('quantum-circuit-form');
  const circuitError = document.getElementById('circuit-error');
  const circuitStatus = document.getElementById('circuit-status');
  const circuitResult = document.getElementById('circuit-result');
  const circuitGates = document.getElementById('circuit-gates');
  const circuitSubmit = circuitForm.querySelector('button[type="submit"]');

  circuitForm.addEventListener('input', () => {
    circuitGates.setCustomValidity('');
    circuitGates.removeAttribute('aria-invalid');
    if (!circuitError.hidden) {
      circuitError.hidden = true;
      circuitError.textContent = '';
    }
  });

  circuitForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    circuitError.hidden = true;
    circuitError.textContent = '';
    circuitResult.hidden = true;
    circuitStatus.textContent = 'Simulating locally…';
    circuitSubmit.disabled = true;
    circuitForm.setAttribute('aria-busy', 'true');

    const formData = new FormData(circuitForm);
    let gates;
    try {
      gates = JSON.parse(formData.get('gates'));
      if (!Array.isArray(gates)) throw new Error('not an array');
    } catch {
      circuitGates.setCustomValidity('Enter a valid JSON array of gates.');
      circuitGates.setAttribute('aria-invalid', 'true');
      circuitStatus.textContent = '';
      circuitError.textContent = 'Gate sequence must be a valid JSON array.';
      circuitError.hidden = false;
      circuitError.focus();
      circuitSubmit.disabled = false;
      circuitForm.removeAttribute('aria-busy');
      return;
    }

    const payload = {
      num_qubits: Number(formData.get('num_qubits')),
      shots: Number(formData.get('shots')),
      seed: Number(formData.get('seed')),
      gates
    };

    try {
      const response = await fetch(circuitForm.action, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        cache: 'no-store',
        body: JSON.stringify(payload)
      });
      let data;
      try {
        data = await response.json();
      } catch {
        throw new Error(`The server returned an invalid response (HTTP ${response.status}).`);
      }
      if (!response.ok) throw new Error(responseError(data, response.status));
      renderCircuitResults(data, circuitResult);
      circuitStatus.textContent = 'Simulation complete. Results were not saved.';
    } catch (requestError) {
      circuitStatus.textContent = '';
      circuitError.textContent = requestError.message || 'Could not simulate the circuit.';
      circuitError.hidden = false;
      circuitError.focus();
    } finally {
      circuitSubmit.disabled = false;
      circuitForm.removeAttribute('aria-busy');
    }
  });

  function renderCircuitResults(data, result) {
    if (!data || !Number.isInteger(data.num_qubits) || data.num_qubits < 1 ||
        data.num_qubits > 12 || !Array.isArray(data.state_vector) ||
        data.state_vector.length !== 2 ** data.num_qubits ||
        !data.measurement_counts || typeof data.measurement_counts !== 'object') {
      throw new Error('The server returned incomplete circuit results.');
    }
    const states = data.state_vector
      .filter((state) => state && typeof state.state === 'string' &&
        Number.isFinite(state.real) && Number.isFinite(state.imaginary) &&
        Number.isFinite(state.probability) && state.probability > 1e-12)
      .sort((left, right) => right.probability - left.probability);
    const counts = Object.entries(data.measurement_counts)
      .filter(([, count]) => Number.isInteger(count) && count > 0)
      .sort((left, right) => right[1] - left[1]);
    if (!states.length || !counts.length) {
      throw new Error('The server returned an empty circuit result.');
    }
    const lines = [
      `${data.num_qubits} qubits · ${data.gate_count} gates · ${data.shots} shots · seed ${data.seed}`,
      'Most probable basis states (full state vector is available from the API):',
      ...states.slice(0, 16).map((state) =>
        `|${state.state}⟩  probability ${state.probability.toFixed(6)}  amplitude ${state.real.toFixed(6)} ${state.imaginary < 0 ? '−' : '+'} ${Math.abs(state.imaginary).toFixed(6)}i`
      ),
      '',
      'Measurement counts:',
      ...counts.slice(0, 16).map(([state, count]) => `|${state}⟩  ${count}`)
    ];
    if (states.length > 16) lines.push(`… and ${states.length - 16} more basis states.`);
    result.textContent = lines.join('\n');
    result.hidden = false;
  }
})();
