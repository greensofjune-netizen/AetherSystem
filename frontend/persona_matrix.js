"use strict";

(() => {
  const selector = document.getElementById("persona-selector");
  const status = document.getElementById("persona-status");
  const panel = document.getElementById("copernicus-panel");
  if (!selector || !status || !panel) {
    throw new Error("Persona controls are missing.");
  }

  class FluidVoiceController {
    constructor() {
      selector.addEventListener("change", (event) => {
        if (event.target instanceof HTMLInputElement && event.target.checked) {
          this.switchVoice(event.target.value);
        }
      });
      this.switchVoice("copernicus_core");
    }

    switchVoice(key) {
      const option = Array.from(selector.querySelectorAll('input[name="persona"]'))
        .find((input) => input.value === key);
      if (!option) throw new Error(`Unknown persona: ${key}`);
      option.checked = true;
      this.activePersona = key;
      this.name = option.dataset.name;
      panel.dataset.persona = key;
      status.textContent = `${this.name}: ${option.dataset.tone}. ${option.dataset.greeting}`;
      window.dispatchEvent(new CustomEvent("persona-shift", {
        detail: { key, name: this.name, timestampUtc: new Date().toISOString() },
      }));
      return this.name;
    }
  }

  window.VoiceMatrix = new FluidVoiceController();
})();
