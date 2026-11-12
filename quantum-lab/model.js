/* Shared by the offline browser app and the dependency-free Node tests. */
(function (root) {
  "use strict";

  const BINS = 120;
  const HALF_SCREEN_MM = 15;
  const WINDOW_SIZE = 128;
  const TRACE_SIZE = 160;
  const RARE_BITS = 8;
  const DEFAULTS = Object.freeze({
    wavelengthNm: 550,
    slitSeparationMm: 0.25,
    whichPath: 0,
  });

  function bounded(value, low, high, name) {
    if (!Number.isFinite(value) || value < low || value > high) {
      throw new RangeError(`${name} must be between ${low} and ${high}.`);
    }
    return value;
  }

  function settingsFor(options = {}) {
    return {
      wavelengthNm: bounded(options.wavelengthNm ?? DEFAULTS.wavelengthNm, 380, 750, "Wavelength"),
      slitSeparationMm: bounded(options.slitSeparationMm ?? DEFAULTS.slitSeparationMm, 0.1, 0.6, "Slit separation"),
      whichPath: bounded(options.whichPath ?? DEFAULTS.whichPath, 0, 1, "Which-path distinguishability"),
    };
  }

  function entropy(probabilities) {
    let result = 0;
    for (const p of probabilities) {
      if (!Number.isFinite(p) || p < 0 || p > 1) {
        throw new RangeError("Probabilities must be finite values between zero and one.");
      }
      if (p > 0) result -= p * Math.log2(p);
    }
    return result;
  }

  function equilibrium(options = {}) {
    const waveStrength = bounded(options.waveStrength ?? 1, 0, 2, "Wave strength");
    const particleStrength = bounded(options.particleStrength ?? 1, 0, 2, "Particle strength");
    const xi = bounded(options.xi ?? 0.5, 0, 1, "Wave weight");
    const stewardship = bounded(options.stewardship ?? 1, 0, 1, "Stewardship weight");
    // On u in [0, 1], W(u) = waveStrength * u and xi, P, S are constant.
    const waveContribution = stewardship * waveStrength * xi;
    const particleContribution = stewardship * particleStrength * (1 - xi);
    return {
      waveContribution,
      particleContribution,
      residual: waveContribution - particleContribution,
      equilibriumXi: stewardship === 0 || waveStrength + particleStrength === 0
        ? null : particleStrength / (waveStrength + particleStrength),
    };
  }

  function distribution(options) {
    const settings = settingsFor(options);
    const visibility = Math.sqrt(1 - settings.whichPath ** 2);
    const wavelength = settings.wavelengthNm * 1e-9;
    const separation = settings.slitSeparationMm * 1e-3;
    const distance = 1.5;
    const slitWidth = 0.04e-3;
    const widthMm = 2 * HALF_SCREEN_MM / BINS;
    const positions = Array.from({ length: BINS }, (_, i) =>
      -HALF_SCREEN_MM + (i + 0.5) * widthMm);
    const weights = positions.map((xMm) => {
      const x = xMm * 1e-3;
      const beta = Math.PI * slitWidth * x / (wavelength * distance);
      const envelope = beta === 0 ? 1 : (Math.sin(beta) / beta) ** 2;
      return envelope * (1 + visibility * Math.cos(2 * Math.PI * separation * x / (wavelength * distance)));
    });
    const total = weights.reduce((sum, p) => sum + p, 0);
    const probabilities = weights.map((p) => p / total);
    let cumulative = 0;
    const cdf = probabilities.map((p) => (cumulative += p));
    cdf[BINS - 1] = 1;
    return {
      settings, visibility, positions, probabilities, cdf, widthMm,
      cohesion: visibility ** 2,
      screenEntropy: entropy(probabilities),
      pathEntropy: entropy([(1 + visibility) / 2, (1 - visibility) / 2]),
      fringeSpacingMm: wavelength * distance / separation * 1e3,
    };
  }

  function randomUnit(random) {
    const value = random();
    if (!Number.isFinite(value) || value < 0 || value >= 1) {
      throw new RangeError("Random source must return a finite value in [0, 1).");
    }
    return value;
  }

  function sample(model, random = Math.random) {
    const u = randomUnit(random);
    let low = 0;
    let high = model.cdf.length - 1;
    while (low < high) {
      const mid = Math.floor((low + high) / 2);
      if (u < model.cdf[mid]) high = mid;
      else low = mid + 1;
    }
    const bin = low;
    const xMm = model.positions[bin] + (randomUnit(random) - 0.5) * model.widthMm;
    const yUnit = randomUnit(random);
    return { bin, xMm, yUnit, surprise: -Math.log2(model.probabilities[bin]) };
  }

  class Experiment {
    constructor(options = {}, random = Math.random) {
      if (typeof random !== "function") throw new TypeError("Random source must be a function.");
      this.random = random;
      this.configure(options);
    }

    configure(options) {
      this.model = distribution(options);
      this.reset();
    }

    reset() {
      this.count = 0;
      this.rareCount = 0;
      this.counts = Array(BINS).fill(0);
      this.windowCounts = Array(BINS).fill(0);
      this.window = [];
      this.hits = [];
      this.trace = [];
      this.rollingEntropy = 0;
    }

    emit(amount) {
      if (!Number.isInteger(amount) || amount < 1 || amount > 10000) {
        throw new RangeError("Emit between 1 and 10,000 photons at a time.");
      }
      for (let i = 0; i < amount; i += 1) {
        const hit = sample(this.model, this.random);
        this.count += 1;
        this.counts[hit.bin] += 1;
        if (hit.surprise >= RARE_BITS) this.rareCount += 1;
        this.window.push(hit.bin);
        this.windowCounts[hit.bin] += 1;
        if (this.window.length > WINDOW_SIZE) {
          this.windowCounts[this.window.shift()] -= 1;
        }
        this.rollingEntropy = entropy(this.windowCounts.map((n) => n / this.window.length));
        this.hits.push(hit);
        this.trace.push({
          photon: this.count,
          surprise: hit.surprise,
          entropy: this.rollingEntropy,
          rare: hit.surprise >= RARE_BITS,
        });
      }
      this.hits = this.hits.slice(-6000);
      this.trace = this.trace.slice(-TRACE_SIZE);
    }

    csv() {
      const s = this.model.settings;
      return [
        "# Quantum Light Lab: SIMULATED data; Math.random, not a quantum entropy source",
        `# wavelength_nm=${s.wavelengthNm},slit_separation_mm=${s.slitSeparationMm},which_path=${s.whichPath}`,
        "# distance_m=1.5,slit_width_mm=0.04,screen_half_width_mm=15",
        `# photons=${this.count},visibility=${this.model.visibility},path_entropy_bits=${this.model.pathEntropy}`,
        "bin,position_mm,expected_probability,observed_count,observed_probability",
        ...this.counts.map((n, i) => [
          i, this.model.positions[i], this.model.probabilities[i], n,
          this.count ? n / this.count : 0,
        ].join(",")),
      ].join("\n");
    }
  }

  const api = Object.freeze({
    BINS, HALF_SCREEN_MM, WINDOW_SIZE, TRACE_SIZE, RARE_BITS, DEFAULTS,
    distribution, entropy, equilibrium, sample, Experiment,
  });
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.QuantumLab = api;
})(globalThis);
