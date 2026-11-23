(() => {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

    class AetherHypothalamus extends HTMLElement {
        connectedCallback() {
            if (this.dataset.ready === "true") {
                return;
            }
            this.dataset.ready = "true";
            const active = !reducedMotion.matches;
            this.innerHTML = `
                <div class="hypothalamus-visual" data-motion="${active}">
                    <div class="hypothalamus-copy">
                        <span class="hypothalamus-eyebrow">HYPOTHALAMUS MOTIF</span>
                        <strong>Steady-state pulse</strong>
                    </div>
                    <svg viewBox="0 0 240 112" role="img"
                         aria-label="Decorative brain profile with a gently pulsing hypothalamus region">
                        <defs>
                            <linearGradient id="brain-fill-${this.instanceId}" x1="0" y1="0" x2="1" y2="1">
                                <stop offset="0" stop-color="#26313a"/>
                                <stop offset="1" stop-color="#10171d"/>
                            </linearGradient>
                        </defs>
                        <path class="brain-outline"
                              d="M35 79C19 68 18 43 33 29C43 18 61 12 79 15C94 4 118 8 129 18C146 8 172 15 178 31C196 35 204 51 197 66C191 78 177 82 164 80C151 92 137 102 121 102C103 102 89 91 77 87C62 91 47 88 35 79Z"
                              fill="url(#brain-fill-${this.instanceId})"/>
                        <path class="brain-fold" d="M42 51C54 40 63 37 78 42C88 45 94 38 99 27"/>
                        <path class="brain-fold" d="M66 69C79 57 88 55 101 62C112 68 118 61 123 49"/>
                        <path class="brain-fold" d="M101 83C112 77 121 78 131 84"/>
                        <path class="brain-fold" d="M128 26C141 35 149 48 147 64"/>
                        <path class="brain-fold" d="M156 37C164 42 173 43 184 40"/>
                        <path class="brain-fold" d="M162 69C172 62 181 59 192 62"/>
                        <path class="signal-path" d="M112 79C129 72 145 69 163 70C181 71 197 76 214 83"/>
                        <circle class="hypothalamus-pulse-ring" cx="122" cy="70" r="13"/>
                        <circle class="hypothalamus-node" cx="122" cy="70" r="5"/>
                        <circle class="signal-dot signal-dot-one" cx="149" cy="70" r="2.4"/>
                        <circle class="signal-dot signal-dot-two" cx="181" cy="73" r="2"/>
                    </svg>
                    <button class="hypothalamus-motion-toggle" type="button">
                        ${active ? "Pause motion" : "Enable motion"}
                    </button>
                    <p>Aesthetic balance motif only; no medical or live telemetry.</p>
                </div>
            `;
            this.toggle = this.querySelector(".hypothalamus-motion-toggle");
            this.visual = this.querySelector(".hypothalamus-visual");
            this.userOverrodeMotion = false;
            this.toggle.addEventListener("click", () => {
                this.userOverrodeMotion = true;
                this.setMotion(this.visual.dataset.motion !== "true");
            });
            reducedMotion.addEventListener("change", (event) => {
                if (!this.userOverrodeMotion) {
                    this.setMotion(!event.matches);
                }
            });
            this.setAttribute("aria-label", "Decorative hypothalamus balance pulse");
        }

        get instanceId() {
            if (!this._instanceId) {
                this._instanceId = Math.random().toString(36).slice(2, 10);
            }
            return this._instanceId;
        }

        setMotion(active) {
            this.visual.dataset.motion = String(active);
            this.toggle.textContent = active ? "Pause motion" : "Enable motion";
        }
    }

    if (!customElements.get("aether-hypothalamus")) {
        customElements.define("aether-hypothalamus", AetherHypothalamus);
    }
})();
