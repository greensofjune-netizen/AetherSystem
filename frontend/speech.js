"use strict";

window.AetherSpeech = (() => {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  function attachRecognition(button, input, status) {
    if (!Recognition || !window.isSecureContext) {
      button.disabled = true;
      status.textContent = "Voice input is unavailable in this browser context.";
      return;
    }

    const recognition = new Recognition();
    recognition.lang = navigator.language || "en-US";
    recognition.interimResults = false;
    recognition.continuous = false;
    let active = false;

    recognition.onstart = () => {
      active = true;
      button.textContent = "Stop voice input";
      status.textContent = "Listening; speech is handled by your browser.";
    };
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0]?.transcript || "")
        .join(" ")
        .trim();
      if (!transcript) return;
      const start = input.selectionStart ?? input.value.length;
      const end = input.selectionEnd ?? start;
      input.setRangeText(`${input.value.slice(0, start) ? " " : ""}${transcript}`, start, end, "end");
      input.dispatchEvent(new Event("input", { bubbles: true }));
      status.textContent = "Voice transcription added to the message.";
    };
    recognition.onerror = (event) => {
      status.textContent = event.error === "not-allowed"
        ? "Microphone access was denied."
        : `Voice input failed: ${event.error}.`;
    };
    recognition.onend = () => {
      active = false;
      button.textContent = "Start voice input";
    };

    button.addEventListener("click", () => {
      if (active) {
        recognition.stop();
        return;
      }
      status.textContent = "Requesting microphone access.";
      try {
        recognition.start();
      } catch (error) {
        status.textContent = `Voice input could not start: ${error.message}`;
      }
    });
  }

  function speak(text) {
    if (!window.speechSynthesis || !window.SpeechSynthesisUtterance) return false;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    window.speechSynthesis.speak(utterance);
    return true;
  }

  function stopSpeaking() {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
  }

  return { attachRecognition, speak, stopSpeaking };
})();
