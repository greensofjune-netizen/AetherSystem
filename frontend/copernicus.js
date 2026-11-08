"use strict";

const copernicusElement = (id) => document.getElementById(id);
const copernicusTimeoutMs = 135000;
let weatherContext = null;

function appendCopernicusMessage(label, text) {
  const message = document.createElement("p");
  const prefix = document.createElement("strong");
  prefix.textContent = `${label}: `;
  message.append(prefix, document.createTextNode(text));
  const messages = copernicusElement("copernicus-messages");
  messages.append(message);
  messages.scrollTop = messages.scrollHeight;
}

async function copernicusJson(url, options = {}, timeoutMs = copernicusTimeoutMs) {
  const response = await fetch(url, {
    ...options,
    signal: AbortSignal.timeout(timeoutMs),
  });
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(`Copernicus request returned an invalid response (HTTP ${response.status}).`);
  }
  if (!response.ok) {
    throw new Error(typeof data.detail === "string"
      ? data.detail
      : `Copernicus request failed (HTTP ${response.status}).`);
  }
  return data;
}

copernicusJson("/api/chat/status", {}, 10000)
  .then((data) => {
    if (typeof data.enabled !== "boolean" || typeof data.model !== "string") {
      throw new Error("Invalid Copernicus status response.");
    }
    copernicusElement("copernicus-status").textContent = data.enabled
      ? `Local model: ${data.model}. Messages are not saved.`
      : "Local AI is disabled. Configure Ollama and reload this shell.";
    copernicusElement("copernicus-send").disabled = !data.enabled;
  })
  .catch((error) => {
    copernicusElement("copernicus-status").textContent = "Local model status unavailable.";
    copernicusElement("copernicus-error").textContent = error.message;
    copernicusElement("copernicus-error").hidden = false;
    console.error("Copernicus status failed:", error);
  });

window.addEventListener("weather-telemetry", (event) => {
  const reading = event.detail;
  if (!reading || typeof reading.city !== "string" ||
      typeof reading.cloud_cover_percent !== "number" ||
      typeof reading.observed_at !== "string" ||
      typeof reading.timezone !== "string" ||
      !["live", "stale"].includes(reading.freshness)) {
    console.error("Copernicus received an invalid weather context.");
    return;
  }
  weatherContext = reading;
});

copernicusElement("copernicus-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = copernicusElement("copernicus-message");
  const message = input.value.trim();
  if (!message) {
    copernicusElement("copernicus-error").textContent = "Enter a message.";
    copernicusElement("copernicus-error").hidden = false;
    return;
  }

  const button = copernicusElement("copernicus-send");
  button.disabled = true;
  copernicusElement("copernicus-error").hidden = true;
  copernicusElement("copernicus-status").textContent = "Copernicus is responding...";
  try {
    const data = await copernicusJson("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        ...(weatherContext ? { weather_context: weatherContext } : {}),
      }),
    });
    if (typeof data.response !== "string" || !data.response.trim() ||
        typeof data.model !== "string") {
      throw new Error("Invalid Copernicus response.");
    }
    appendCopernicusMessage("You", message);
    appendCopernicusMessage("Copernicus", data.response);
    input.value = "";
    copernicusElement("copernicus-status").textContent = `Response from ${data.model}. Not saved.`;
  } catch (error) {
    copernicusElement("copernicus-status").textContent = "Copernicus could not respond. Your message is retained for retry.";
    copernicusElement("copernicus-error").textContent = error.message;
    copernicusElement("copernicus-error").hidden = false;
    console.error("Copernicus chat failed:", error);
  } finally {
    button.disabled = false;
  }
});
