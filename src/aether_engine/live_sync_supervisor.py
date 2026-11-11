import asyncio
import json
import math
import random
import time
from asyncio import QueueFull
from collections.abc import Mapping
from typing import Set

MAX_CONNECTED_INTERFACES = 64
MAX_PENDING_EVENTS_PER_INTERFACE = 256


# ==========================================
# 🌌 CENTRAL SYSTEM CONFIGURATION & REGISTRY
# ==========================================
class LiveSyncSupervisor:
    def __init__(self):
        # Track the active UI subscribers for live event broadcasts.
        self._connected_interfaces: Set[asyncio.Queue[str | None]] = set()
        self._last_cloud_alert_state = None
        self.is_running = True

    def register_interface(self) -> asyncio.Queue[str | None]:
        """Registers a new UI panel or console tab to the broadcast pool."""
        if len(self._connected_interfaces) >= MAX_CONNECTED_INTERFACES:
            raise RuntimeError("The live-sync subscriber limit has been reached.")
        queue: asyncio.Queue[str | None] = asyncio.Queue(
            maxsize=MAX_PENDING_EVENTS_PER_INTERFACE
        )
        self._connected_interfaces.add(queue)
        return queue

    def unregister_interface(self, queue: asyncio.Queue[str | None]) -> None:
        """Removes an offline interface stream smoothly."""
        self._connected_interfaces.discard(queue)

    async def broadcast(self, event_type: str, data: dict) -> int:
        """Sends a synchronized update payload to EVERY single connected view instantly."""
        payload = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": event_type,
            "data": data,
            "status": "EQUILIBRIUM"
        }
        message = json.dumps(payload)

        notified = 0
        for queue in tuple(self._connected_interfaces):
            try:
                queue.put_nowait(message)
            except QueueFull:
                self.unregister_interface(queue)
                while not queue.empty():
                    queue.get_nowait()
                    queue.task_done()
                queue.put_nowait(None)
                continue
            notified += 1
        return notified

    async def evaluate_cloud_cover_alerts(
        self, weather_reading: Mapping[str, object]
    ) -> None:
        """Broadcast cloud-cover alerts only when crossing a threshold state."""
        cloud_pct = weather_reading.get("cloud_cover")
        if cloud_pct is None or weather_reading.get("is_live") is not True:
            return
        if (
            isinstance(cloud_pct, bool)
            or not isinstance(cloud_pct, (int, float))
            or not 0 <= cloud_pct <= 100
            or not math.isfinite(cloud_pct)
        ):
            raise ValueError(
                "Live cloud cover must be a finite percentage from 0 to 100."
            )

        city = weather_reading.get("city", "Unknown Location")
        city = city.strip() if isinstance(city, str) else "Unknown Location"
        if not city:
            city = "Unknown Location"

        if cloud_pct <= 15:
            current_state = "CLEAR_SKIES"
            alert_msg = (
                f"☀️ Clear Skies in {city}: Cloud cover dropped to {cloud_pct}% "
                "(Optimal visibility/solar)."
            )
            severity = "INFO"
        elif cloud_pct >= 85:
            current_state = "HEAVY_OVERCAST"
            alert_msg = (
                f"☁️ Heavy Cloud Cover in {city}: Cloud cover reached {cloud_pct}%."
            )
            severity = "WARNING"
        else:
            self._last_cloud_alert_state = None
            return

        if current_state == self._last_cloud_alert_state:
            return
        self._last_cloud_alert_state = current_state
        await self.broadcast(
            event_type="CONSOLE_ALERT",
            data={
                "message": alert_msg,
                "severity": severity,
                "cloud_cover": cloud_pct,
                "city": city,
            },
        )

# Instantiate our master background manager
supervisor = LiveSyncSupervisor()


async def evaluate_cloud_cover_alerts(
    weather_reading: Mapping[str, object],
) -> None:
    """Evaluate cloud cover and broadcast through the shared supervisor."""
    await supervisor.evaluate_cloud_cover_alerts(weather_reading)


# ==========================================
# ⚡ THE EASY COMMANDS (TRIGGER API)
# ==========================================
async def execute_command(command_str: str):
    """Processes a simple plain-text control command and refreshes the fleet."""
    cmd = command_str.strip().lower()

    if cmd in ["sync", "update", "refresh"]:
        # Rapidly triggers a total layout refresh across all panes
        await supervisor.broadcast(
            event_type="GLOBAL_UI_REFRESH",
            data={"reason": "Manual operator override", "velocity_fps": 60}
        )
        print(f"🎵 [Command] Sent instant pulse to {len(supervisor._connected_interfaces)} active interfaces.")

    elif cmd.startswith("alert "):
        # Broadcasts a specific custom notification banner text across UI modules
        alert_msg = command_str[6:]
        await supervisor.broadcast(
            event_type="CONSOLE_ALERT",
            data={"message": alert_msg, "severity": "HIGH"}
        )
        print(f"📡 [Command] Broadcasted banner: '{alert_msg}'")

    elif cmd in ["exit", "shutdown"]:
        supervisor.is_running = False
        await supervisor.broadcast(event_type="SYSTEM_SHUTDOWN", data={})
        print("🛑 Closing workspace session and supervisor lines.")

    else:
        print(f"❌ Unknown tracking token: '{cmd}'. Try: 'sync', 'alert <msg>', or 'exit'")

# ==========================================
# 🖥️ SIMATED CONSUMERS (THE INTERFACES)
# ==========================================
async def mock_user_interface_worker(ui_name: str):
    """Simulates an individual UI window, desktop widget, or terminal view listening for updates."""
    queue = supervisor.register_interface()
    print(f"🟢 {ui_name} connected to the Live Sync pipeline.")

    try:
        while supervisor.is_running:
            # Wait until the supervisor drops an update package down the pipe
            message = await queue.get()
            if message is None:
                queue.task_done()
                break
            event_data = json.loads(message)

            # Print out the incoming state cleanly
            print(f"\n[✨ {ui_name} Auto-Updated] -> {event_data['timestamp']}")
            print(f"   Event: {event_data['event']}")
            print(f"   Payload: {json.dumps(event_data['data'])}")
            queue.task_done()

    except asyncio.CancelledError:
        pass
    finally:
        supervisor.unregister_interface(queue)
        print(f"🔴 {ui_name} disconnected safely.")

# ==========================================
# 📊 ACTUAL UI PANEL CONSUMER
# ==========================================
dashboard_lock = asyncio.Lock()
dashboard_state: dict = {}

async def safe_update_dashboard_state(event_name: str, payload_data: dict):
    """Mutates the shared dashboard state under the lock to avoid interleaved updates."""
    async with dashboard_lock:
        dashboard_state.update(payload_data)
        dashboard_state["last_event"] = event_name
        dashboard_state["timestamp"] = time.time()

async def safe_replace_dashboard_state(new_state: dict):
    """Atomically swaps the entire dashboard state for a restored one."""
    async with dashboard_lock:
        dashboard_state.clear()
        dashboard_state.update(new_state)

async def safe_get_dashboard_snapshot() -> dict:
    """Returns a copy of the current state for initial client page loads."""
    async with dashboard_lock:
        return dashboard_state.copy()

async def ui_panel_worker():
    """Registers the dashboard panel and applies each broadcast payload to its state."""
    ui_queue = supervisor.register_interface()
    try:
        while supervisor.is_running:
            message = await ui_queue.get()
            if message is None:
                ui_queue.task_done()
                break
            payload = json.loads(message)
            # Update dashboard state or widgets using payload["data"]
            await safe_update_dashboard_state(payload["event"], payload["data"])
            ui_queue.task_done()
    finally:
        supervisor.unregister_interface(ui_queue)

# ==========================================
# 🌀 BACKGROUND AUTOMATED TELEMETRY DROPS
# ==========================================
async def automated_telemetry_loop():
    """Generates continuous natural variance updates to keep frames perfectly synchronized."""
    metrics = ["Stability Index", "Throughput Rate", "Harmonic Response"]

    while supervisor.is_running:
        await asyncio.sleep(4)  # Drops a steady heartbeat every few seconds
        if supervisor._connected_interfaces:
            metric_chosen = random.choice(metrics)
            value = round(random.uniform(94.2, 99.9), 2)

            await supervisor.broadcast(
                event_type="LIVE_TELEMETRY_DROP",
                data={metric_chosen: f"{value}%", "health": "OPTIMAL"}
            )

# ==========================================
# 🕹️ OPERATOR CONSOLE INTERACTIVE LOOP
# ==========================================
async def operator_console_input():
    """The easy-access interactive terminal command listener."""
    print("\n--- 🧭 Live Sync Engine Dashboard Booted ---")
    print("Commands available: 'sync' (force flash update) | 'alert <text>' | 'exit'\n")

    loop = asyncio.get_event_loop()

    while supervisor.is_running:
        try:
            # Non-blocking terminal input collection line
            user_input = await loop.run_in_executor(None, input, "Operator> ")
            if user_input:
                await execute_command(user_input)
        except Exception as e:
            print(f"Error handling request: {e}")
            break

# ==========================================
# 🚀 MAIN MASTER RUNTIME RUNNER
# ==========================================
async def main():
    # Spin up multiple layout contexts watching the exact same pool source
    await asyncio.gather(
        mock_user_interface_worker("MacBook Desktop Widget"),
        mock_user_interface_worker("Tkinter Stability Chart Dashboard"),
        mock_user_interface_worker("Console Status Supervisor"),
        ui_panel_worker(),
        automated_telemetry_loop(),
        operator_console_input()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nPipeline broken via terminal sequence. Goodbye.")
