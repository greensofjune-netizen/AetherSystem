(function () {
  "use strict";

  const Q = globalThis.QuantumLab;
  const $ = (id) => document.getElementById(id);
  const lab = new Q.Experiment();
  const canvases = ["detector", "distribution", "entropy"].map($);
  const contexts = canvases.map((canvas) => canvas.getContext("2d"));
  const controls = ["which-path", "wavelength", "separation", "rate"].map($);
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  let running = false;
  let lastTime = null;
  let credit = 0;
  let frame = null;
  let lastPaint = 0;
  let lastTable = 0;
  let dirty = true;

  function announce(message) { $("status").textContent = message; }

  function stop(message) {
    running = false;
    $("run").textContent = "Start experiment";
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
    lastTime = null;
    credit = 0;
    if (message) announce(message);
  }

  function fail(error) {
    stop("Experiment stopped because of an error.");
    console.error("Quantum Light Lab:", error);
    $("error").hidden = false;
    $("error").textContent = error instanceof Error ? error.message : String(error);
  }

  function guarded(action) {
    return (...args) => {
      try { action(...args); } catch (error) { fail(error); }
    };
  }

  function sizeCanvases() {
    const ratio = Math.min(devicePixelRatio || 1, 2);
    canvases.forEach((canvas) => {
      canvas.width = Math.round(canvas.clientWidth * ratio);
      canvas.height = Math.round(canvas.clientHeight * ratio);
    });
    dirty = true;
    paint();
  }

  function surface(index) {
    const canvas = canvases[index];
    const context = contexts[index];
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    context.setTransform(canvas.width / w, 0, 0, canvas.height / h, 0, 0);
    context.clearRect(0, 0, w, h);
    return { c: context, w, h };
  }

  function drawDetector() {
    const { c, w, h } = surface(0);
    c.strokeStyle = "#1c303e";
    c.lineWidth = 1;
    for (let i = 1; i < 12; i += 1) {
      const x = i * w / 12;
      c.beginPath(); c.moveTo(x, 0); c.lineTo(x, h); c.stroke();
    }
    c.fillStyle = "#83eddd";
    c.globalAlpha = 0.7;
    for (const hit of lab.hits) {
      const x = (hit.xMm + Q.HALF_SCREEN_MM) / (2 * Q.HALF_SCREEN_MM) * w;
      c.fillRect(x, 8 + hit.yUnit * (h - 16), 1.7, 1.7);
    }
    c.globalAlpha = 1;
    if (!lab.count) {
      c.fillStyle = "#a7b8c5"; c.textAlign = "center"; c.font = "13px system-ui";
      c.fillText("Your first photon starts the story.", w / 2, h / 2);
    }
  }

  function axes(index, maximum, xLabels, yLabel) {
    const { c, w, h } = surface(index);
    const left = 40, right = w - 10, top = 23, bottom = h - 29;
    c.font = "10px system-ui"; c.lineWidth = 1;
    for (let i = 0; i <= 4; i += 1) {
      const y = bottom - (bottom - top) * i / 4;
      c.strokeStyle = "#2b3c4b";
      c.beginPath(); c.moveTo(left, y); c.lineTo(right, y); c.stroke();
      c.fillStyle = "#a7b8c5"; c.textAlign = "right";
      c.fillText((maximum * i / 4).toFixed(1), left - 6, y + 3);
    }
    c.textAlign = "left"; c.fillText(yLabel, left, 12);
    xLabels.forEach((text, i) => {
      c.textAlign = i === 0 ? "left" : i === xLabels.length - 1 ? "right" : "center";
      c.fillText(text, left + (right - left) * i / (xLabels.length - 1), h - 8);
    });
    return {
      c, left, right, top, bottom,
      x: (fraction) => left + fraction * (right - left),
      y: (value) => bottom - value / maximum * (bottom - top),
    };
  }

  function line(plot, values, color, dashed = false) {
    plot.c.strokeStyle = color; plot.c.lineWidth = 1.6;
    plot.c.setLineDash(dashed ? [5, 4] : []);
    plot.c.beginPath();
    values.forEach((v, i) => {
      const x = plot.x(values.length === 1 ? 0.5 : i / (values.length - 1));
      if (i === 0) plot.c.moveTo(x, plot.y(v));
      else plot.c.lineTo(x, plot.y(v));
    });
    plot.c.stroke(); plot.c.setLineDash([]);
  }

  function drawDistribution() {
    const expected = lab.model.probabilities.map((p) => p * 100);
    const observed = lab.counts.map((n) => lab.count ? n / lab.count * 100 : 0);
    const max = Math.max(...expected, ...observed) * 1.15;
    const plot = axes(1, max, ["-15", "0 mm", "+15"], "% / bin");
    const barWidth = (plot.right - plot.left) / Q.BINS;
    plot.c.fillStyle = "#718dc9";
    observed.forEach((value, i) => {
      plot.c.fillRect(plot.left + i * barWidth, plot.y(value),
        Math.max(0.5, barWidth - 0.5), plot.bottom - plot.y(value));
    });
    // Expected values refer to bin centers, not the edges of the screen.
    const curvePlot = { ...plot, x: (fraction) => plot.x((0.5 + fraction * (Q.BINS - 1)) / Q.BINS) };
    line(curvePlot, expected, "#6ce2d2");
  }

  function drawEntropy() {
    const values = lab.trace.map((point) => point.surprise);
    const max = Math.max(10, Math.ceil(Math.max(0, ...values) + 1));
    const first = lab.trace[0]?.photon ?? 0;
    const last = lab.trace.at(-1)?.photon ?? 0;
    const plot = axes(2, max, [String(first), "Photon", String(last)], "bits");
    plot.c.strokeStyle = "#8b7158"; plot.c.setLineDash([2, 5]);
    plot.c.beginPath(); plot.c.moveTo(plot.left, plot.y(Q.RARE_BITS));
    plot.c.lineTo(plot.right, plot.y(Q.RARE_BITS)); plot.c.stroke(); plot.c.setLineDash([]);
    if (values.length) {
      line(plot, values, "#6ce2d2");
      line(plot, lab.trace.map((point) => point.entropy), "#f4b578", true);
      lab.trace.forEach((point, i) => {
        if (point.rare || values.length === 1) {
          plot.c.fillStyle = point.rare ? "#f4b578" : "#6ce2d2";
          plot.c.beginPath();
          plot.c.arc(plot.x(values.length === 1 ? 0.5 : i / (values.length - 1)), plot.y(point.surprise), 2.5, 0, 2 * Math.PI);
          plot.c.fill();
        }
      });
    }
  }

  function rows(target, data) {
    const fragment = document.createDocumentFragment();
    data.forEach((values) => {
      const tr = document.createElement("tr");
      values.forEach((value) => {
        const td = document.createElement("td");
        td.textContent = String(value); tr.append(td);
      });
      fragment.append(tr);
    });
    target.replaceChildren(fragment);
  }

  function updateTables() {
    if (!$("data-details").open) return;
    rows($("bin-data"), lab.counts.map((n, i) => [
      lab.model.positions[i].toFixed(3),
      (lab.model.probabilities[i] * 100).toFixed(4),
      n,
      (lab.count ? n / lab.count * 100 : 0).toFixed(4),
    ]));
    rows($("trace-data"), lab.trace.map((point) => [
      point.photon, point.surprise.toFixed(3), point.entropy.toFixed(3), point.rare ? "Yes" : "No",
    ]));
  }

  function paint() {
    if (!dirty) return;
    drawDetector(); drawDistribution(); drawEntropy();
    $("count").textContent = lab.count.toLocaleString();
    $("visibility").textContent = `${(lab.model.visibility * 100).toFixed(0)}%`;
    $("cohesion").textContent = `${(lab.model.cohesion * 100).toFixed(0)}%`;
    $("path-entropy").textContent = lab.model.pathEntropy.toFixed(3);
    $("rare-count").textContent = lab.rareCount.toLocaleString();
    $("spacing").textContent = `${lab.model.fringeSpacingMm.toFixed(2)} mm`;
    $("screen-entropy").textContent = `${lab.model.screenEntropy.toFixed(3)} bits`;
    $("rolling-entropy").textContent = `${lab.rollingEntropy.toFixed(3)} bits`;
    $("mode").textContent = lab.model.visibility === 0 ? "No interference" :
      lab.model.visibility === 1 ? "Coherent paths" : "Partial coherence";
    $("export").disabled = lab.count === 0;
    dirty = false;
  }

  function refresh() { dirty = true; paint(); updateTables(); }

  function updateEquilibrium() {
    const values = {};
    for (const [id, key] of [
      ["notebook-wave", "waveStrength"], ["notebook-particle", "particleStrength"],
      ["notebook-xi", "xi"], ["notebook-stewardship", "stewardship"],
    ]) {
      const input = $(id);
      values[key] = Number(input.value);
      const text = `${values[key].toFixed(2)} (dimensionless)`;
      $(`${id}-value`).textContent = text;
      input.setAttribute("aria-valuetext", text);
    }
    const result = Q.equilibrium(values);
    $("equilibrium-residual").textContent = result.residual.toFixed(6);
    $("equilibrium-xi").textContent = result.equilibriumXi === null
      ? "Not unique" : result.equilibriumXi.toFixed(4);
    $("equilibrium-status").textContent = result.equilibriumXi === null
      ? "E is zero for every ξ: zero stewardship or both strengths zero masks the balance. No unique equilibrium weight."
      : Math.abs(result.residual) < 1e-10
        ? "Balanced within numerical tolerance (|E| < 10⁻¹⁰). This is an algebraic balance, not proof of quantum or thermodynamic equilibrium."
        : result.residual > 0
          ? "Positive residual: weighted wave contribution exceeds weighted particle contribution."
          : "Negative residual: weighted particle contribution exceeds weighted wave contribution.";
  }

  function tick(time) {
    frame = null;
    if (!running) return;
    if (lastTime !== null) {
      // Do not generate a backlog after a delayed frame or suspended tab.
      credit += Math.min((time - lastTime) / 1000, 0.1) * Number($("rate").value);
      const amount = Math.floor(credit);
      if (amount > 0) { lab.emit(amount); credit -= amount; dirty = true; }
    }
    lastTime = time;
    if (time - lastPaint >= (reducedMotion.matches ? 250 : 33)) {
      paint(); lastPaint = time;
    }
    if (time - lastTable >= 1000) { updateTables(); lastTable = time; }
    frame = requestAnimationFrame(guarded(tick));
  }

  function configure() {
    lab.configure({
      wavelengthNm: Number($("wavelength").value),
      slitSeparationMm: Number($("separation").value),
      whichPath: Number($("which-path").value) / 100,
    });
    $("path-value").textContent = `${$("which-path").value}%`;
    $("wavelength-value").textContent = `${$("wavelength").value} nm`;
    $("separation-value").textContent = `${Number($("separation").value).toFixed(2)} mm`;
    credit = 0; lastTime = null;
    announce("Physics changed. Detections cleared for a fresh experiment.");
    refresh();
  }

  if (contexts.some((context) => !context)) {
    fail(new Error("This browser does not support 2D canvas. Please use a current browser."));
    document.querySelectorAll("button, input").forEach((el) => { el.disabled = true; });
    return;
  }

  controls.slice(0, 3).forEach((control) => control.addEventListener("input", guarded(configure)));
  ["notebook-wave", "notebook-particle", "notebook-xi", "notebook-stewardship"]
    .forEach((id) => $(id).addEventListener("input", guarded(updateEquilibrium)));
  $("rate").addEventListener("input", () => { $("rate-value").textContent = `${$("rate").value} / s`; });
  $("run").addEventListener("click", guarded(() => {
    if (running) { stop(`Paused at ${lab.count.toLocaleString()} detections.`); refresh(); }
    else {
      running = true; lastTime = null;
      $("run").textContent = "Pause experiment";
      announce("Running. Pause to inspect the data or change the experiment settings.");
      frame = requestAnimationFrame(guarded(tick));
    }
  }));
  for (const [id, amount] of [["single", 1], ["batch", 1000]]) {
    $(id).addEventListener("click", guarded(() => {
      lab.emit(amount); refresh();
      announce(`Emitted ${amount.toLocaleString()}. Total: ${lab.count.toLocaleString()} detections.`);
    }));
  }
  $("reset").addEventListener("click", guarded(() => {
    stop(); lab.reset(); refresh(); announce("Run cleared. Physics settings preserved.");
  }));
  $("export").addEventListener("click", guarded(() => {
    const url = URL.createObjectURL(new Blob([lab.csv()], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url; link.download = "quantum-light-lab-simulated.csv";
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    announce("Histogram CSV download requested. Includes physics settings and simulation labels.");
  }));
  $("data-details").addEventListener("toggle", guarded(updateTables));
  document.addEventListener("visibilitychange", guarded(() => {
    if (document.hidden && running) { stop("Paused while this tab is hidden. Resume when ready."); refresh(); }
  }));
  window.addEventListener("resize", guarded(sizeCanvases));
  guarded(() => {
    updateEquilibrium();
    sizeCanvases();
    announce("Ready. Start a run or emit one photon.");
  })();
})();
