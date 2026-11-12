const assert = require("node:assert/strict");
const test = require("node:test");
const Q = require("./model.js");

// Eight-point Gauss-Legendre quadrature, independent of production Simpson integration.
function referenceBins(model, intensity) {
  const nodes = [0.1834346424956498, 0.5255324099163290, 0.7966664774136267, 0.9602898564975363];
  const weights = [0.3626837833783620, 0.3137066458778873, 0.2223810344533745, 0.1012285362903763];
  const halfWidth = model.widthMm / 2;
  const integrals = model.positions.map((center) => nodes.reduce((sum, node, i) =>
    sum + weights[i] * (intensity(center - halfWidth * node) +
      intensity(center + halfWidth * node)), 0) * halfWidth);
  const total = integrals.reduce((sum, value) => sum + value, 0);
  return integrals.map((value) => value / total);
}

function assertMatches(model, reference) {
  const totalVariation = reference.reduce((sum, value, i) =>
    sum + Math.abs(value - model.probabilities[i]), 0) / 2;
  assert.ok(totalVariation < 1e-9, `Integration total variation: ${totalVariation}`);
}

test("integrated coherent probabilities agree with complex amplitudes and independent quadrature", () => {
  for (const wavelengthNm of [380, 550, 750]) {
    for (const slitSeparationMm of [0.1, 0.25, 0.6]) {
      const model = Q.distribution({ wavelengthNm, slitSeparationMm, whichPath: 0 });
      const wavelengthMm = wavelengthNm * 1e-6;
      const distanceMm = 1500;
      const expected = referenceBins(model, (xMm) => {
        const phase = Math.PI * slitSeparationMm * xMm / (wavelengthMm * distanceMm);
        const beta = Math.PI * 0.04 * xMm / (wavelengthMm * distanceMm);
        const slitAmplitude = beta === 0 ? 1 : Math.sin(beta) / beta;
        const real = slitAmplitude * (Math.cos(phase) + Math.cos(-phase));
        const imaginary = slitAmplitude * (Math.sin(phase) + Math.sin(-phase));
        return real ** 2 + imaginary ** 2;
      });
      assertMatches(model, expected);
    }
  }
});

test("integrated partial-coherence probabilities agree with an independent mixture", () => {
  for (const wavelengthNm of [380, 550, 750]) {
    for (const slitSeparationMm of [0.1, 0.25, 0.6]) {
      for (const whichPath of [0, 0.2, 0.4, 0.8, 1]) {
        const model = Q.distribution({ wavelengthNm, slitSeparationMm, whichPath });
        const expected = referenceBins(model, (xMm) => {
          const beta = Math.PI * 0.04 * xMm / (wavelengthNm * 1e-6 * 1500);
          const envelope = beta === 0 ? 1 : (Math.sin(beta) / beta) ** 2;
          const phase = Math.PI * slitSeparationMm * xMm / (wavelengthNm * 1e-6 * 1500);
          const coherent = envelope * (2 * Math.cos(phase)) ** 2;
          const incoherent = 2 * envelope;
          return model.visibility * coherent + (1 - model.visibility) * incoherent;
        });
        assertMatches(model, expected);
      }
    }
  }
});

test("finite-difference quadrature independently checks the equilibrium integral", () => {
  const steps = 1000;
  for (const waveStrength of [0, 0.37, 1, 2]) {
    for (const particleStrength of [0, 0.61, 2]) {
      for (const xi of [0, 0.23, 0.5, 1]) {
        for (const stewardship of [0, 0.4, 1]) {
          let integral = 0;
          for (let i = 0; i < steps; i += 1) {
            const left = i / steps;
            const right = (i + 1) / steps;
            const width = right - left;
            const fluxLeft = waveStrength * left * xi;
            const fluxRight = waveStrength * right * xi;
            const derivative = (fluxRight - fluxLeft) / width;
            integral += (derivative - particleStrength * (1 - xi)) * stewardship * width;
          }
          const result = Q.equilibrium({ waveStrength, particleStrength, xi, stewardship });
          assert.ok(Math.abs(integral - result.residual) < 1e-10);
        }
      }
    }
  }
});

test("published default reference values and sampling limits remain reproducible", () => {
  const model = Q.distribution();
  assert.ok(Math.abs(model.fringeSpacingMm - 3.3) < 1e-12);
  assert.equal(model.pathEntropy, 0);
  assert.equal(model.cohesion, 1);
  const narrowestFringeMm = 380e-6 * 1500 / 0.6;
  assert.ok(Math.abs(narrowestFringeMm - 0.95) < 1e-12);
  assert.ok(narrowestFringeMm / model.widthMm >= 3.8);
  const maximumAngle = Math.atan(15 / 1500);
  assert.ok(maximumAngle < 0.010001);
});
