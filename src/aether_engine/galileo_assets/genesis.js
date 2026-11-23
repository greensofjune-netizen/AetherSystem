(() => {
  "use strict";

  const panel = document.getElementById("genesis-panel");
  if (!panel) return;
  const epochs = document.getElementById("genesis-epochs");
  const lifecycle = document.getElementById("genesis-lifecycle");
  const status = document.getElementById("genesis-status");
  const range = document.getElementById("genesis-position");
  const rangeOutput = document.getElementById("genesis-position-output");
  const nearest = document.getElementById("genesis-nearest");
  const age = document.getElementById("genesis-age");
  const simulationStatus = document.getElementById("genesis-simulation-status");
  let requestNumber = 0;

  function request(path, options = {}) {
    return fetch(path, {
      credentials: "same-origin",
      headers: options.body ? { "Content-Type": "application/json" } : undefined,
      ...options,
    }).then(async (response) => {
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || `Request failed (${response.status}).`);
      return body;
    });
  }

  function lifecycleItem(entry) {
    const item = document.createElement("li");
    item.className = `genesis-stage ${entry.status.startsWith("PENDING") ? "pending" : "complete"}`;
    const title = document.createElement("strong");
    title.textContent = `${entry.stage}. ${entry.name}`;
    const badge = document.createElement("span");
    badge.textContent = entry.status.replaceAll("_", " ");
    const evidence = document.createElement("p");
    evidence.textContent = entry.evidence;
    item.append(title, badge, evidence);
    return item;
  }

  function epochItem(entry) {
    const item = document.createElement("li");
    const heading = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = entry.label;
    const time = document.createElement("span");
    time.textContent = entry.age_label;
    heading.append(title, time);
    const summary = document.createElement("p");
    summary.textContent = entry.summary;
    const claim = document.createElement("small");
    claim.textContent = entry.claim_status.replaceAll("_", " ");
    const link = document.createElement("a");
    link.href = entry.source_url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = `Source: ${entry.source}`;
    item.append(heading, summary, claim, link);
    return item;
  }

  function displayAge(result) {
    const years = result.display_age_years;
    if (years < 1 / 31_557_600) return `${result.display_age_seconds.toExponential(3)} seconds`;
    if (years < 1) return `${years.toExponential(3)} years`;
    if (years < 1_000_000) return `${Math.round(years).toLocaleString()} years`;
    if (years >= 1_000_000_000) {
      return `${(years / 1_000_000_000).toFixed(2).replace(/\\.0+$/, "")} billion years`;
    }
    return `${(years / 1_000_000).toFixed(1).replace(/\\.0$/, "")} million years`;
  }

  async function updateSimulation() {
    const requestId = ++requestNumber;
    const position = Number(range.value);
    rangeOutput.textContent = `${Math.round(position * 100)}%`;
    simulationStatus.textContent = "Calculating display position…";
    try {
      const result = await request("/api/genesis/simulate", {
        method: "POST",
        body: JSON.stringify({ position }),
      });
      if (requestId !== requestNumber) return;
      nearest.textContent = result.nearest_epoch_label;
      age.textContent = displayAge(result);
      simulationStatus.textContent = "Educational log-time position; not a physical prediction.";
    } catch (error) {
      simulationStatus.textContent = `Simulation unavailable: ${error.message}`;
    }
  }

  async function loadTimeline() {
    try {
      const data = await request("/api/genesis/timeline");
      lifecycle.replaceChildren(...data.lifecycle.map(lifecycleItem));
      epochs.replaceChildren(...data.epochs.map(epochItem));
      status.textContent = data.scope.replaceAll("_", " ");
      await updateSimulation();
    } catch (error) {
      status.textContent = `Timeline unavailable: ${error.message}`;
    }
  }

  range.addEventListener("input", updateSimulation);
  void loadTimeline();
})();
