"use strict";

const copernicusElement = (id) => document.getElementById(id);
const copernicusTimeoutMs = 135000;
const maxContextMessages = 12;
const maxContextCharacters = 12000;
let weatherContext = null;
let selectedImages = [];
let conversationHistory = [];
let readingImages = false;
let sending = false;
let chatEnabled = false;
let modelStatusPolls = 0;

function appendGovernorTelemetry(telemetry) {
  if (!telemetry) return;
  const verification = telemetry.routing_verified === true ? "verified"
    : telemetry.routing_verified === false ? "verification failed" : "not assigned";
  const matches = telemetry.matching_domains.length
    ? telemetry.matching_domains.join(", ") : "none";
  appendCopernicusMessage("Governor telemetry",
    `Simulated routing · domain: ${telemetry.domain} (matches: ${matches}) · ` +
    `${telemetry.status} · node: ${telemetry.assigned_node} · ${verification} · ` +
    `${telemetry.timestamp}\n${telemetry.message}`);
}

function appendCopernicusMessage(label, text, images = [], responseActions = false) {
  const message = document.createElement("article");
  message.className = `chat-message ${label === "You" ? "user-message" : "assistant-message"}`;
  const author = document.createElement("p");
  author.className = "message-author";
  author.textContent = label;
  const content = document.createElement("p");
  content.className = "message-content";
  content.textContent = text;
  message.append(author, content);
  for (const image of images) {
    const binary = atob(image.data);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    const preview = document.createElement("img");
    preview.className = "copernicus-image";
    preview.alt = `Attached image: ${image.name}`;
    preview.src = URL.createObjectURL(
      new Blob([bytes], { type: image.media_type }),
    );
    message.append(preview);
  }
  if (label === "Copernicus" || responseActions) {
    const actions = document.createElement("div");
    actions.className = "message-actions";
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "secondary-button";
    copy.textContent = "Copy response";
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(text);
        copy.textContent = "Copied";
      } catch (error) {
        copernicusElement("copernicus-error").textContent =
          `Could not copy the response: ${error.message}`;
        copernicusElement("copernicus-error").hidden = false;
      }
    });
    const speak = document.createElement("button");
    speak.type = "button";
    speak.className = "secondary-button";
    speak.textContent = "Read aloud";
    speak.addEventListener("click", () => {
      if (!window.AetherSpeech.speak(text)) {
        copernicusElement("copernicus-error").textContent =
          "Speech output is unavailable in this browser.";
        copernicusElement("copernicus-error").hidden = false;
      }
    });
    actions.append(copy, speak);
    message.append(actions);
  }
  const messages = copernicusElement("copernicus-messages");
  messages.append(message);
  while (messages.children.length > 100) {
    const oldest = messages.firstElementChild;
    oldest.querySelectorAll("img").forEach((image) => URL.revokeObjectURL(image.src));
    oldest.remove();
  }
  messages.scrollTop = messages.scrollHeight;
}

function updateComposer() {
  const input = copernicusElement("copernicus-message");
  copernicusElement("copernicus-character-count").textContent =
    `${input.value.length} / 4000`;
  copernicusElement("copernicus-send").disabled =
    !chatEnabled || sending || readingImages || !input.value.trim();
}

function recentConversationContext() {
  let history = conversationHistory.slice(-maxContextMessages);
  while (
    history.length &&
    history.reduce((total, turn) => total + turn.content.length, 0) >
      maxContextCharacters
  ) {
    history = history.slice(2);
  }
  return history;
}

function resetConversation() {
  if (sending) return;
  const messages = copernicusElement("copernicus-messages");
  messages.querySelectorAll("img").forEach((image) => URL.revokeObjectURL(image.src));
  window.AetherSpeech.stopSpeaking();
  const welcome = document.createElement("article");
  welcome.className = "chat-message assistant-message";
  const author = document.createElement("p");
  author.className = "message-author";
  author.textContent = "Copernicus";
  const content = document.createElement("p");
  content.className = "message-content";
  content.textContent = "I’m your personal companion. What would you like to explore?";
  welcome.append(author, content);
  messages.replaceChildren(welcome);
  conversationHistory = [];
  selectedImages = [];
  copernicusElement("copernicus-message").value = "";
  copernicusElement("copernicus-images").value = "";
  copernicusElement("copernicus-error").hidden = true;
  renderSelectedImages();
  updateComposer();
  copernicusElement("copernicus-status").textContent =
    "New private conversation. Nothing is saved.";
  copernicusElement("copernicus-message").focus();
}

function renderSelectedImages() {
  const list = copernicusElement("copernicus-selected-images");
  list.replaceChildren();
  selectedImages.forEach((image, index) => {
    const item = document.createElement("li");
    item.textContent = `${image.name} (${image.bytes.toLocaleString()} bytes) `;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Remove";
    remove.setAttribute("aria-label", `Remove ${image.name}`);
    remove.addEventListener("click", () => {
      selectedImages.splice(index, 1);
      renderSelectedImages();
    });
    item.append(remove);
    list.append(item);
  });
  copernicusElement("copernicus-image-count").textContent = selectedImages.length
    ? `${selectedImages.length} image(s) selected.`
    : "";
}

async function updateCopernicusModelStatus() {
  if (!chatEnabled) return;
  try {
    const status = await copernicusJson("/api/model/status", {}, 10000);
    if (typeof status.model !== "string" || typeof status.status !== "string") {
      throw new Error("Invalid local-model status response.");
    }
    if (status.status === "unavailable") {
      chatEnabled = false;
      updateComposer();
      copernicusElement("copernicus-status").textContent =
        `Local model unavailable: ${status.detail || "Ollama could not load the configured model."}`;
      return;
    }
    if (status.status === "ready") {
      chatEnabled = true;
      updateComposer();
      copernicusElement("copernicus-status").textContent =
        `Local model ready: ${status.model}. This conversation is not saved.`;
      return;
    }
    copernicusElement("copernicus-status").textContent =
      `Loading ${status.model} into local memory…`;
    if (["pending", "loading"].includes(status.status) && modelStatusPolls < 150) {
      modelStatusPolls += 1;
      window.setTimeout(updateCopernicusModelStatus, 2000);
    }
  } catch (error) {
    copernicusElement("copernicus-status").textContent =
      `Could not check local model status: ${error.message}`;
  }
}

async function fileToBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return btoa(binary);
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
    const error = new Error(typeof data.detail === "string"
      ? data.detail
      : `Copernicus request failed (HTTP ${response.status}).`);
    error.governor = data.governor;
    throw error;
  }
  return data;
}

copernicusJson("/api/chat/status", {}, 10000)
  .then((data) => {
    if (typeof data.enabled !== "boolean" ||
        (data.enabled && (typeof data.model !== "string" || !data.model.trim())) ||
        (!data.enabled && data.model !== null)) {
      throw new Error("Invalid Copernicus status response.");
    }
    copernicusElement("copernicus-status").textContent = data.enabled
      ? `Local model: ${data.model}. This conversation is not saved.`
      : "Local AI is disabled. Configure Ollama and reload this shell.";
    chatEnabled = data.enabled;
    updateComposer();
    void updateCopernicusModelStatus();
  })
  .catch((error) => {
    copernicusElement("copernicus-status").textContent = "Local model status unavailable.";
    copernicusElement("copernicus-error").textContent = error.message;
    copernicusElement("copernicus-error").hidden = false;
    console.error("Copernicus status failed:", error);
  });

window.AetherSpeech.attachRecognition(
  copernicusElement("copernicus-voice"),
  copernicusElement("copernicus-message"),
  copernicusElement("copernicus-voice-status"),
);

copernicusElement("copernicus-images").addEventListener("change", async (event) => {
  const files = Array.from(event.target.files || []);
  if (!files.length) return;
  readingImages = true;
  updateComposer();
  copernicusElement("copernicus-error").hidden = true;
  try {
    if (selectedImages.length + files.length > 4) {
      throw new Error("Attach no more than 4 images.");
    }
    let total = selectedImages.reduce((sum, image) => sum + image.bytes, 0);
    const additions = [];
    for (const file of files) {
      if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
        throw new Error(`${file.name}: choose a JPEG, PNG, or WebP image.`);
      }
      if (file.size < 1 || file.size > 2_000_000) {
        throw new Error(`${file.name}: each image must be no larger than 2 MB.`);
      }
      total += file.size;
      if (total > 6_000_000) throw new Error("Images exceed the 6 MB total limit.");
      additions.push({
        name: file.name,
        media_type: file.type,
        data: await fileToBase64(file),
        bytes: file.size,
      });
    }
    selectedImages.push(...additions);
    renderSelectedImages();
  } catch (error) {
    copernicusElement("copernicus-error").textContent = error.message;
    copernicusElement("copernicus-error").hidden = false;
  } finally {
    event.target.value = "";
    readingImages = false;
    updateComposer();
  }
});

copernicusElement("copernicus-new-chat").addEventListener("click", () => {
  const hasContent =
    conversationHistory.length ||
    copernicusElement("copernicus-message").value.trim() ||
    selectedImages.length;
  if (hasContent && !window.confirm("Start a new chat? This conversation and any draft will be cleared.")) {
    return;
  }
  resetConversation();
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    const input = copernicusElement("copernicus-message");
    input.value = button.dataset.prompt;
    updateComposer();
    input.focus();
  });
});

copernicusElement("copernicus-message").addEventListener("input", updateComposer);
copernicusElement("copernicus-message").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    copernicusElement("copernicus-form").requestSubmit();
  }
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
  if (!message || readingImages || sending || !chatEnabled) {
    copernicusElement("copernicus-error").textContent = !chatEnabled
      ? "The local model is not ready yet."
      : readingImages
        ? "Wait for the selected images to finish loading."
        : "Enter a message before sending.";
    copernicusElement("copernicus-error").hidden = false;
    return;
  }

  sending = true;
  const personaSelector = copernicusElement("persona-selector");
  if (personaSelector) personaSelector.disabled = true;
  const persona = window.VoiceMatrix?.activePersona;
  const personaName = window.VoiceMatrix?.name || "Copernicus";
  input.disabled = true;
  copernicusElement("copernicus-images").disabled = true;
  copernicusElement("copernicus-new-chat").disabled = true;
  document.querySelectorAll("[data-prompt]").forEach((suggestion) => {
    suggestion.disabled = true;
  });
  updateComposer();
  copernicusElement("copernicus-error").hidden = true;
  copernicusElement("copernicus-status").textContent = "Copernicus is responding...";
  const typing = document.createElement("p");
  typing.className = "chat-message assistant-message";
  typing.setAttribute("role", "status");
  typing.textContent = "Copernicus is thinking…";
  const messages = copernicusElement("copernicus-messages");
  messages.append(typing);
  messages.scrollTop = messages.scrollHeight;
  try {
    const history = recentConversationContext();
    const data = await copernicusJson("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        ...(persona ? { persona } : {}),
        ...(history.length ? { history } : {}),
        images: selectedImages.map(({ name, media_type, data }) => ({
          name, media_type, data,
        })),
        ...(weatherContext ? { weather_context: weatherContext } : {}),
      }),
    });
    if (typeof data.response !== "string" || !data.response.trim() ||
        typeof data.model !== "string") {
      throw new Error("Invalid Copernicus response.");
    }
    typing.remove();
    appendCopernicusMessage("You", message, selectedImages);
    appendGovernorTelemetry(data.governor);
    appendCopernicusMessage(personaName, data.response, [], true);
    conversationHistory.push(
      { role: "user", content: message },
      { role: "assistant", content: data.response },
    );
    conversationHistory = conversationHistory.slice(-maxContextMessages);
    input.value = "";
    selectedImages = [];
    renderSelectedImages();
    copernicusElement("copernicus-status").textContent = `Response from ${data.model}. Not saved.`;
  } catch (error) {
    typing.remove();
    appendGovernorTelemetry(error.governor);
    copernicusElement("copernicus-status").textContent = "Copernicus could not respond. Your message is retained for retry.";
    copernicusElement("copernicus-error").textContent = error.message;
    copernicusElement("copernicus-error").hidden = false;
    console.error("Copernicus chat failed:", error);
  } finally {
    sending = false;
    if (personaSelector) personaSelector.disabled = false;
    input.disabled = false;
    copernicusElement("copernicus-images").disabled = false;
    copernicusElement("copernicus-new-chat").disabled = false;
    document.querySelectorAll("[data-prompt]").forEach((suggestion) => {
      suggestion.disabled = false;
    });
    updateComposer();
  }
});
