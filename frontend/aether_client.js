// Shared JavaScript layer for /monitor, weather.html, and Galileo.app
function aetherResponseError(result, status, operation) {
    const detail = result && typeof result === 'object' ? result.detail : undefined;
    let message = `${operation} HTTP ${status}`;
    if (typeof detail === 'string' && detail.trim()) {
        message = detail;
    } else if (Array.isArray(detail)) {
        const messages = detail
            .filter((entry) => entry && typeof entry === 'object' &&
                Array.isArray(entry.loc) &&
                entry.loc.every((part) => typeof part === 'string' ||
                    (typeof part === 'number' && Number.isInteger(part))) &&
                typeof entry.msg === 'string')
            .map((entry) => `${entry.loc.join('.') || 'request'}: ${entry.msg}`);
        if (messages.length) message = messages.join('; ');
    }
    const error = new Error(message);
    error.status = status;
    return error;
}

const AetherClient = {
    stream: null,

    async dispatchUnified({ node, event, payload = {}, timestamp = Date.now() / 1000 }) {
        const response = await fetch('/api/v1/unified/dispatch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                protocol_version: '1.0.0',
                source_lang: 'js',
                node,
                event,
                timestamp,
                payload
            })
        });
        const result = await response.json();
        if (!response.ok) {
            throw aetherResponseError(result, response.status, 'Unified dispatch');
        }
        return result;
    },

    subscribeUnified(onEvent, onError = (error) => console.error(error)) {
        const source = new EventSource('/api/v1/unified/stream');
        const receive = (event) => {
            try {
                onEvent(JSON.parse(event.data), event.type);
            } catch (error) {
                onError(error);
            }
        };
        ['snapshot', 'dispatch', 'reset', 'replay-required'].forEach((name) => {
            source.addEventListener(name, receive);
        });
        source.onerror = onError;
        return source;
    },

    // 1. Connect to the live FastAPI SSE stream
    connectLiveStream(onUpdateCallback, onAlertCallback) {
        if (this.stream) this.stream.close();

        this.stream = new EventSource('/api/v1/dashboard/stream');

        this.stream.addEventListener('ui-update', (event) => {
            const payload = JSON.parse(event.data);
            if (onUpdateCallback) onUpdateCallback(payload);
        });

        this.stream.addEventListener('CONSOLE_ALERT', (event) => {
            const alertData = JSON.parse(event.data);
            if (onAlertCallback) onAlertCallback(alertData);
        });

        this.stream.onerror = () => {
            this.stream.close();
            setTimeout(() => this.connectLiveStream(onUpdateCallback, onAlertCallback), 3000);
        };
    },

    // 2. Fetch an instant state snapshot on page load
    async fetchSnapshot() {
        const res = await fetch('/api/v1/dashboard/snapshot');
        if (!res.ok) throw new Error(`Snapshot HTTP ${res.status}`);
        return await res.json();
    },

    // 3. Send a prompt to Copernicus (backed by qwen2.5-coder)
    async askCopernicus(promptText) {
        const res = await fetch('/api/copernicus/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: promptText })
        });
        if (!res.ok) throw new Error(`Copernicus HTTP ${res.status}`);
        return await res.json();
    }
};

window.AetherClient = AetherClient;
