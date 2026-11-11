import json
import time
from dataclasses import dataclass


@dataclass
class CyborgTelemetry:
    timestamp_utc: str
    target_pan: float
    target_tilt: float
    safety_lock: bool


class CyborgHardwareBridge:
    def __init__(self, port: str = "/dev/tty.usbmodem1234", baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self.serial_link = None

    def engage_comms(self):
        try:
            import serial
        except ImportError as error:
            print(
                "[Cyborg Link Offline] Simulation mode active. "
                f"Install pyserial to enable hardware communication. Detail: {error}"
            )
            return

        try:
            self.serial_link = serial.Serial(self.port, self.baudrate, timeout=0.1)
            print(f"[Cyborg Link Established] Connected to nervous node on {self.port}")
        except serial.SerialException as error:
            print(f"[Cyborg Link Offline] Simulation mode active. Check USB. Detail: {error}")

    def sync_kinetics(self, telemetry: CyborgTelemetry):
        payload = {
            "utc": telemetry.timestamp_utc,
            "pan": round(telemetry.target_pan, 2),
            "tilt": round(telemetry.target_tilt, 2),
            "safe": 1 if telemetry.safety_lock else 0,
        }

        command_string = json.dumps(payload) + "\n"

        if self.serial_link and self.serial_link.is_open:
            self.serial_link.write(command_string.encode("utf-8"))
        else:
            print(f"[Simulated Kinetic Frame Transfer] {command_string.strip()}")


if __name__ == "__main__":
    bridge = CyborgHardwareBridge()
    bridge.engage_comms()

    for loop in range(3):
        frame = CyborgTelemetry(
            timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            target_pan=15.5 * loop,
            target_tilt=45.0,
            safety_lock=False,
        )
        bridge.sync_kinetics(frame)
        time.sleep(1.0)
