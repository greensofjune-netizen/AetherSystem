import asyncio
import json
import random
import time
from typing import Set


# ==========================================
# 🌌 CENTRAL SYSTEM CONFIGURATION & REGISTRY
# ==========================================
class LiveSyncSupervisor:
    def __init__(self):
        # Keeps track of all actively connected user interfaces
        self._connected_interfaces: Set[asyncio.Queue] = set()
        self.is_running = True

    def register_interface(self) -> asyncio.Queue:
        """Registers a new UI panel or console tab to the broadcast pool."""
        queue = asyncio.Queue()
        self._connected_interfaces.add(queue)
        return queue

    def unregister_interface(self, queue: asyncio.Queue):
        """Removes an offline interface stream smoothly."""
        self._connected_interfaces.discard(queue)

    async def broadcast(self, event_type: str, data: dict):
        """Sends a synchronized update payload to EVERY single connected view instantly."""
        payload = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": event_type,
            "data": data,
            "status": "EQUILIBRIUM"
        }
        message = json.dumps(payload)
        
        if self._connected_interfaces:
            # Send message to all subscriber queues concurrently
            await asyncio.gather(
                *[queue.put(message) for queue in self._connected_interfaces]
            )

# Instantiate our master background manager
supervisor = LiveSyncSupervisor()

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
            payload = json.loads(await ui_queue.get())
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
