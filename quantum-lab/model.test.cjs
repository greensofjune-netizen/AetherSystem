const assert = require("node:assert/strict");
const test = require("node:test");
const Q = require("./model.js");

function seeded(seed) {
  return () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 2 ** 32;
  };
}

test("screen probabilities normalize, are symmetric and finite across slider extremes", () => {
  for (const wavelengthNm of [380, 550, 750]) {
    for (const slitSeparationMm of [0.1, 0.25, 0.6]) {
      for (const whichPath of [0, 0.5, 1]) {
        const m = Q.distribution({ wavelengthNm, slitSeparationMm, whichPath });
        assert.equal(m.probabilities.length, 120);
        assert.ok(Math.abs(m.probabilities.reduce((s, p) => s + p, 0) - 1) < 1e-12);
        m.probabilities.forEach((p, i) => {
          assert.ok(Number.isFinite(p) && p >= 0);
          assert.ok(Math.abs(p - m.probabilities[119 - i]) < 1e-12);
          if (i) assert.ok(m.cdf[i] >= m.cdf[i - 1]);
        });
        assert.equal(m.cdf.at(-1), 1);
        assert.ok(m.screenEntropy > 0 && m.screenEntropy <= Math.log2(120));
      }
    }
  }
});

test("which-path information suppresses interference and raises reduced path entropy", () => {
  let previousEntropy = -1;
  for (const whichPath of [0, 0.2, 0.5, 0.9, 1]) {
    const model = Q.distribution({ whichPath });
    assert.ok(Math.abs(model.visibility ** 2 + whichPath ** 2 - 1) < 1e-12);
    assert.ok(Math.abs(model.cohesion - (1 - whichPath ** 2)) < 1e-12);
    assert.ok(model.pathEntropy > previousEntropy);
    previousEntropy = model.pathEntropy;
  }
  assert.ok(Math.abs(Q.distribution({ whichPath: 0.4 }).cohesion - 0.84) < 1e-12);
  assert.equal(Q.distribution({ whichPath: 0 }).pathEntropy, 0);
  assert.equal(Q.distribution({ whichPath: 1 }).pathEntropy, 1);
  assert.equal(Q.distribution({ whichPath: 1 }).visibility, 0);
  // With the interference term removed, slit separation cannot change the envelope.
  assert.deepEqual(Q.distribution({ whichPath: 1, slitSeparationMm: 0.1 }).probabilities,
    Q.distribution({ whichPath: 1, slitSeparationMm: 0.6 }).probabilities);
  assert.notDeepEqual(Q.distribution({ whichPath: 0 }).probabilities,
    Q.distribution({ whichPath: 1 }).probabilities);
});

test("fringe spacing follows wavelength times distance over separation", () => {
  assert.ok(Math.abs(Q.distribution().fringeSpacingMm - 3.3) < 1e-12);
  const base = Q.distribution({ wavelengthNm: 400, slitSeparationMm: 0.2 }).fringeSpacingMm;
  assert.equal(Q.distribution({ wavelengthNm: 400, slitSeparationMm: 0.4 }).fringeSpacingMm, base / 2);
  assert.ok(Math.abs(Q.distribution({ wavelengthNm: 600, slitSeparationMm: 0.2 }).fringeSpacingMm - base * 1.5) < 1e-12);
});

test("entropy handles zeros and distinguishes certain and uniform outcomes", () => {
  assert.equal(Q.entropy([1, 0]), 0);
  assert.equal(Q.entropy([0.5, 0.5]), 1);
  assert.equal(Q.entropy([0.25, 0.25, 0.25, 0.25]), 2);
  for (const p of [-1, 2, NaN, Infinity]) assert.throws(() => Q.entropy([p]), RangeError);
});

test("dimensionless equilibrium integrates the specified fields exactly", () => {
  assert.deepEqual(Q.equilibrium(), {
    waveContribution: 0.5, particleContribution: 0.5, residual: 0, equilibriumXi: 0.5,
  });
  for (const waveStrength of [0, 0.3, 1, 2]) {
    for (const particleStrength of [0, 0.7, 1, 2]) {
      for (const xi of [0, 0.25, 0.5, 1]) {
        for (const stewardship of [0, 0.4, 1]) {
          const result = Q.equilibrium({ waveStrength, particleStrength, xi, stewardship });
          // Boundary flux minus the integrated constant sink on the unit interval.
          const boundaryFlux = waveStrength * xi - 0;
          const integratedSink = particleStrength * (1 - xi) * (1 - 0);
          assert.ok(Math.abs(result.residual - stewardship * (boundaryFlux - integratedSink)) < 1e-12);
          assert.ok(Number.isFinite(result.residual));
          assert.equal(result.residual, result.waveContribution - result.particleContribution);
          if (stewardship > 0 && waveStrength + particleStrength > 0) {
            assert.ok(result.equilibriumXi >= 0 && result.equilibriumXi <= 1);
            const balanced = Q.equilibrium({
              waveStrength, particleStrength, xi: result.equilibriumXi, stewardship,
            });
            assert.ok(Math.abs(balanced.residual) < 1e-12);
          } else {
            assert.equal(result.equilibriumXi, null);
            assert.equal(result.residual, 0);
          }
        }
      }
    }
  }
});

test("equilibrium distinguishes positive, negative and degenerate residuals", () => {
  assert.equal(Q.equilibrium({ xi: 0 }).residual, -1);
  assert.equal(Q.equilibrium({ xi: 1 }).residual, 1);
  assert.equal(Q.equilibrium({ particleStrength: 2 }).equilibriumXi, 2 / 3);
  assert.equal(Q.equilibrium({ waveStrength: 0 }).equilibriumXi, 1);
  assert.equal(Q.equilibrium({ particleStrength: 0 }).equilibriumXi, 0);
  assert.equal(Q.equilibrium({ stewardship: 0 }).equilibriumXi, null);
  assert.equal(Q.equilibrium({ waveStrength: 0, particleStrength: 0 }).equilibriumXi, null);
  assert.equal(Q.equilibrium({ xi: 1, stewardship: 0.25 }).residual, 0.25);
});

test("equilibrium fields reject invalid values without changing photon data", () => {
  const lab = new Q.Experiment({}, seeded(12));
  lab.emit(2);
  const before = lab.csv();
  for (const key of ["waveStrength", "particleStrength", "xi", "stewardship"]) {
    for (const value of [-1, 3, NaN, Infinity, "1"]) {
      assert.throws(() => Q.equilibrium({ [key]: value }), RangeError);
    }
  }
  for (const key of ["xi", "stewardship"]) {
    assert.throws(() => Q.equilibrium({ [key]: 1.01 }), RangeError);
  }
  Q.equilibrium({ waveStrength: 2, xi: 1 });
  assert.equal(lab.csv(), before);
});

test("inverse-CDF sampling handles both edges and exact CDF boundaries", () => {
  const m = Q.distribution();
  assert.equal(Q.sample(m, () => 0).bin, 0);
  assert.equal(Q.sample(m, () => 1 - Number.EPSILON).bin, 119);
  const hit = Q.sample(m, () => m.cdf[50]);
  assert.equal(hit.bin, 51);
  assert.equal(hit.surprise, -Math.log2(m.probabilities[51]));
  for (const bad of [1, -0.1, NaN, Infinity]) assert.throws(() => Q.sample(m, () => bad), RangeError);
});

test("50,000 seeded photons approach the expected histogram", () => {
  for (const whichPath of [0, 1]) {
    const lab = new Q.Experiment({ whichPath }, seeded(42));
    for (let i = 0; i < 5; i += 1) lab.emit(10000);
    assert.equal(lab.count, 50000);
    assert.equal(lab.counts.reduce((sum, n) => sum + n, 0), 50000);
    const totalVariation = lab.counts.reduce((sum, n, i) =>
      sum + Math.abs(n / lab.count - lab.model.probabilities[i]), 0) / 2;
    assert.ok(totalVariation < 0.025, `Total variation distance ${totalVariation}`);
    assert.equal(lab.hits.length, 6000);
    assert.equal(lab.trace.length, Q.TRACE_SIZE);
    assert.equal(lab.window.length, Q.WINDOW_SIZE);
    assert.equal(lab.windowCounts.reduce((s, n) => s + n, 0), Q.WINDOW_SIZE);
    assert.ok(lab.rollingEntropy <= Math.log2(Q.BINS));
    assert.ok(lab.hits.every((hit) => hit.xMm >= -15 && hit.xMm <= 15));
  }
});

test("rare events and rolling entropy reflect the actual detections", () => {
  const lab = new Q.Experiment({}, () => 0);
  lab.emit(160);
  assert.equal(lab.rareCount, lab.model.probabilities[0] <= 2 ** -Q.RARE_BITS ? 160 : 0);
  assert.equal(lab.rollingEntropy, 0);
  assert.equal(lab.trace.at(-1).photon, 160);
  assert.equal(lab.trace.at(-1).surprise, -Math.log2(lab.model.probabilities[0]));
});

test("configuration changes and reset cannot mix experimental datasets", () => {
  const lab = new Q.Experiment({}, seeded(3));
  lab.emit(200);
  lab.configure({ whichPath: 1, wavelengthNm: 700 });
  assert.equal(lab.count, 0);
  assert.equal(lab.hits.length, 0);
  assert.equal(lab.trace.length, 0);
  assert.equal(lab.window.length, 0);
  assert.equal(lab.rareCount, 0);
  assert.ok(lab.counts.every((n) => n === 0));
  lab.emit(1);
  lab.reset();
  assert.equal(lab.model.settings.wavelengthNm, 700);
  assert.equal(lab.model.pathEntropy, 1);
  assert.equal(lab.count, 0);
});

test("invalid settings and batch sizes report explicit errors without clearing good data", () => {
  const lab = new Q.Experiment({}, seeded(1));
  lab.emit(1);
  for (const options of [{ wavelengthNm: NaN }, { whichPath: -1 }, { whichPath: 1.1 },
    { slitSeparationMm: 0 }, { wavelengthNm: 751 }]) {
    assert.throws(() => lab.configure(options), RangeError);
    assert.equal(lab.count, 1);
  }
  for (const amount of [0, -1, 1.2, 10001, NaN]) assert.throws(() => lab.emit(amount), RangeError);
  assert.throws(() => new Q.Experiment({}, null), TypeError);
});

test("CSV has simulation provenance, physics parameters and all 120 histogram rows", () => {
  const lab = new Q.Experiment({ whichPath: 0.5 }, seeded(8));
  lab.emit(1000);
  const csv = lab.csv();
  assert.match(csv, /SIMULATED/);
  assert.match(csv, /which_path=0.5/);
  assert.match(csv, /photons=1000/);
  const data = csv.split("\n").filter((row) => !row.startsWith("#"));
  assert.equal(data.length, 121);
  assert.equal(data[0], "bin,position_mm,expected_probability,observed_count,observed_probability");
  assert.equal(data.slice(1).reduce((sum, row) => sum + Number(row.split(",")[3]), 0), 1000);
});
