(() => {
  'use strict';

  function displayName(key) {
    return key
      .replaceAll('_', ' ')
      .replace(/\b[a-z]/g, (letter) => letter.toUpperCase());
  }

  function renderResults(element, data) {
    element.replaceChildren();
    for (const [key, value] of Object.entries(data)) {
      const label = document.createElement('dt');
      const result = document.createElement('dd');
      label.textContent = displayName(key);
      result.textContent = typeof value === 'number'
        ? new Intl.NumberFormat(undefined, { maximumSignificantDigits: 8 }).format(value)
        : String(value);
      element.append(label, result);
    }
    element.hidden = false;
  }

  for (const form of document.querySelectorAll('.calculator-card form')) {
    const button = form.querySelector('button[type="submit"]');
    const status = form.parentElement.querySelector('.result-status');
    const results = form.parentElement.querySelector('.result');

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;

      button.disabled = true;
      results.hidden = true;
      status.classList.remove('error');
      status.textContent = 'Calculating…';
      try {
        const values = Object.fromEntries(
          Array.from(new FormData(form), ([key, value]) => [key, Number(value)]),
        );
        const response = await fetch(form.action, {
          method: 'POST',
          cache: 'no-store',
          credentials: 'same-origin',
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(values),
        });
        let data;
        try {
          data = await response.json();
        } catch (_) {
          throw new Error(`The server returned an invalid response (HTTP ${response.status}).`);
        }
        if (!response.ok) {
          throw new Error(typeof data.detail === 'string'
            ? data.detail
            : `Calculation failed (HTTP ${response.status}).`);
        }
        if (data === null || Array.isArray(data) || typeof data !== 'object') {
          throw new Error('The server returned an invalid calculation result.');
        }
        renderResults(results, data);
        status.textContent = 'Calculation complete. Results are not saved.';
      } catch (error) {
        status.classList.add('error');
        status.textContent = error.message || 'The calculation could not be completed.';
      } finally {
        button.disabled = false;
      }
    });
  }
})();
