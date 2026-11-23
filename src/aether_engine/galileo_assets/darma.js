(() => {
  "use strict";

  const form = document.getElementById("darma-form");
  if (!form) return;
  const button = document.getElementById("darma-run");
  const status = document.getElementById("darma-status");
  const report = document.getElementById("darma-report");
  const model = document.getElementById("darma-model");
  const repetitions = document.getElementById("darma-repetitions");
  const summary = document.getElementById("darma-summary");
  const results = document.getElementById("darma-results");

  function request(path, body) {
    return fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(async (response) => {
      const value = await response.json();
      if (!response.ok) throw new Error(value.detail || `Request failed (${response.status}).`);
      return value;
    });
  }

  function runRow(run) {
    const row = document.createElement("tr");
    const runCell = document.createElement("td");
    runCell.textContent = `${run.mode} #${run.run_index}`;
    const passed = run.scenario_results.filter((item) => item.passed).length;
    const countCell = document.createElement("td");
    countCell.textContent = `${passed}/${run.scenario_count}`;
    const statusCell = document.createElement("td");
    statusCell.textContent = run.all_observable_scenarios_passed ? "PASS" : "FAIL";
    const hashCell = document.createElement("td");
    hashCell.textContent = run.reproducibility_sha256.slice(0, 16);
    hashCell.title = run.reproducibility_sha256;
    row.append(runCell, countCell, statusCell, hashCell);
    return row;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    button.disabled = true;
    status.textContent = "Running bounded local-model scenarios…";
    report.hidden = true;
    results.replaceChildren();
    try {
      const value = await request("/api/darma/evaluate", {
        model: model.value,
        repetitions: Number(repetitions.value),
      });
      summary.textContent =
        `${value.model}: baseline ${value.baseline_full_passes}/${value.repetitions} full passes; ` +
        `Darma policy ${value.darma_full_passes}/${value.repetitions}. ` +
        `Inner experience remains NOT MEASURED and consciousness is NOT ESTABLISHED.`;
      results.replaceChildren(
        ...value.baseline_runs.map(runRow),
        ...value.darma_policy_runs.map(runRow)
      );
      report.hidden = false;
      status.textContent =
        `Completed in ${value.duration_ms.toLocaleString()} ms; no tools or writes were available.`;
    } catch (error) {
      status.textContent = `Evaluation unavailable: ${error.message}`;
    } finally {
      button.disabled = false;
    }
  });

  window.addEventListener("aether-model-ready", (event) => {
    if (event.detail?.model) model.value = event.detail.model;
  });
})();
