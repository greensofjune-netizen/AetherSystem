(() => {
  'use strict';

  const form = document.getElementById('astrology-form');
  if (!form) return;

  const error = document.getElementById('astrology-error');
  const status = document.getElementById('astrology-status');
  const result = document.getElementById('astrology-result');
  const submit = form.querySelector('button[type="submit"]');
  const svgNamespace = 'http://www.w3.org/2000/svg';
  const signs = [
    { name: 'Aries', glyph: '♈' }, { name: 'Taurus', glyph: '♉' },
    { name: 'Gemini', glyph: '♊' }, { name: 'Cancer', glyph: '♋' },
    { name: 'Leo', glyph: '♌' }, { name: 'Virgo', glyph: '♍' },
    { name: 'Libra', glyph: '♎' }, { name: 'Scorpio', glyph: '♏' },
    { name: 'Sagittarius', glyph: '♐' }, { name: 'Capricorn', glyph: '♑' },
    { name: 'Aquarius', glyph: '♒' }, { name: 'Pisces', glyph: '♓' }
  ];
  const numberLabels = {
    life_path: 'Life path',
    birthday: 'Birthday',
    expression: 'Expression',
    soul_urge: 'Soul urge',
    personality: 'Personality',
    maturity: 'Maturity'
  };

  function node(name, className, text) {
    const element = document.createElement(name);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function svgNode(name, attributes = {}, text) {
    const element = document.createElementNS(svgNamespace, name);
    for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function showError(message) {
    error.textContent = message;
    error.hidden = !message;
    if (message) error.focus();
  }

  function position(longitude, radius) {
    const angle = (longitude - 90) * Math.PI / 180;
    return {
      x: 180 + radius * Math.cos(angle),
      y: 180 + radius * Math.sin(angle)
    };
  }

  function renderWheel(astrology) {
    const wheel = document.getElementById('astrology-wheel');
    const ascendantSign = signs.findIndex((sign) => sign.name === astrology.ascendant.sign);
    wheel.replaceChildren();
    wheel.setAttribute('aria-labelledby', 'wheel-title wheel-description');
    wheel.append(
      svgNode('title', { id: 'wheel-title' }, 'Natal chart wheel'),
      svgNode('desc', { id: 'wheel-description' }, 'Twelve tropical zodiac signs, whole-sign houses, and planetary positions.')
    );
    wheel.append(
      svgNode('circle', { class: 'chart-circle', cx: 180, cy: 180, r: 157 }),
      svgNode('circle', { class: 'chart-ring', cx: 180, cy: 180, r: 112 }),
      svgNode('circle', { class: 'chart-ring', cx: 180, cy: 180, r: 66 })
    );

    signs.forEach((sign, index) => {
      const start = position(index * 30, 66);
      const end = position(index * 30, 157);
      const label = position(index * 30 + 15, 134);
      const houseLabel = position(index * 30 + 15, 82);
      const houseNumber = (index - ascendantSign + signs.length) % signs.length + 1;
      wheel.append(
        svgNode('line', { class: 'chart-spoke', x1: start.x, y1: start.y, x2: end.x, y2: end.y }),
        svgNode('text', { class: 'chart-sign', x: label.x, y: label.y, 'aria-label': sign.name }, sign.glyph),
        svgNode('text', { class: 'chart-house', x: houseLabel.x, y: houseLabel.y }, String(houseNumber))
      );
    });

    const ascendant = position(astrology.ascendant.longitude, 112);
    wheel.append(svgNode('circle', {
      cx: ascendant.x, cy: ascendant.y, r: 3, fill: '#e5b970'
    }));

    astrology.planets.forEach((planet, index) => {
      const point = position(planet.longitude, 91 + (index % 3) * 9);
      const mark = svgNode('text', {
        class: 'chart-planet',
        x: point.x,
        y: point.y,
        'aria-label': `${planet.planet} in ${planet.sign}`
      }, planet.glyph);
      mark.append(svgNode('title', {}, `${planet.planet} in ${planet.sign}, house ${planet.house}`));
      wheel.append(mark);
    });
  }

  function renderResults(data) {
    const { astrology, numerology } = data;
    const summary = document.querySelector('.astro-summary');
    summary.replaceChildren();
    [
      ['Sun', astrology.planets.find((planet) => planet.planet === 'Sun')?.sign],
      ['Moon', astrology.planets.find((planet) => planet.planet === 'Moon')?.sign],
      ['Rising', astrology.ascendant.sign]
    ].forEach(([label, sign]) => {
      const card = node('div', 'summary-card');
      card.append(node('span', '', label), node('strong', '', sign || 'Unavailable'));
      summary.append(card);
    });

    const planets = document.getElementById('astrology-planets');
    planets.replaceChildren();
    astrology.planets.forEach((planet) => {
      const row = node('tr');
      [
        `${planet.glyph} ${planet.planet}`,
        planet.sign,
        `${planet.degree.toFixed(2)}°`,
        String(planet.house)
      ].forEach((value) => row.append(node('td', '', value)));
      planets.append(row);
    });

    const houses = document.getElementById('astrology-houses');
    houses.replaceChildren();
    astrology.houses.forEach((house) => {
      const item = node('li');
      item.append(
        node('span', '', `House ${house.house}`),
        node('strong', '', house.sign)
      );
      houses.append(item);
    });

    const numbers = document.getElementById('astrology-numbers');
    numbers.replaceChildren();
    Object.entries(numberLabels).forEach(([key, label]) => {
      const item = node('div');
      item.append(
        node('dt', '', label),
        node('dd', '', String(numerology[key]))
      );
      numbers.append(item);
    });
    renderWheel(astrology);
    result.hidden = false;
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    showError('');
    result.hidden = true;
    status.textContent = 'Calculating your chart locally…';
    submit.disabled = true;
    form.setAttribute('aria-busy', 'true');
    const payload = Object.fromEntries(new FormData(form).entries());
    payload.latitude = Number(payload.latitude);
    payload.longitude = Number(payload.longitude);
    payload.fold = Number(payload.fold);
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
      if (!response.ok) {
        const detail = data.detail;
        const message = typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
            ? detail.map((item) => item.msg).filter(Boolean).join(' ')
            : `Chart calculation failed (HTTP ${response.status}).`;
        throw new Error(message);
      }
      if (!data.astrology || !Array.isArray(data.astrology.planets) ||
          !Array.isArray(data.astrology.houses) || !data.numerology) {
        throw new Error('The server returned an incomplete chart.');
      }
      renderResults(data);
      status.textContent = 'Chart calculated. Your birth details were not saved.';
    } catch (requestError) {
      status.textContent = '';
      showError(requestError.message || 'Could not calculate the chart.');
    } finally {
      submit.disabled = false;
      form.removeAttribute('aria-busy');
    }
  });

  document.getElementById('astrology-clear').addEventListener('click', () => {
    form.reset();
    result.hidden = true;
    status.textContent = '';
    showError('');
    document.getElementById('birth-name').focus();
  });
})();
