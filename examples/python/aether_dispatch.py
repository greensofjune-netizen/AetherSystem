"""Send a unified event through the local Aether Engine C ABI."""

import ctypes
import json
import time
from pathlib import Path


def main() -> int:
    library_path = Path(__file__).resolve().parents[2] / "libaether.dylib"
    library = ctypes.CDLL(str(library_path))
    library.aether_dispatch_json.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_int,
    ]
    library.aether_dispatch_json.restype = ctypes.c_int

    envelope = {
        "protocol_version": "1.0.0",
        "source_lang": "python",
        "node": "ATLAS",
        "event": "PYTHON_C_ABI_CHECK",
        "timestamp": time.time(),
        "payload": {"verified": True},
    }
    encoded = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
    response = ctypes.create_string_buffer(4096)
    status = library.aether_dispatch_json(encoded, response, len(response))
    if status < 0:
        raise RuntimeError(f"Aether C ABI failed with error code {status}.")
    if status >= 400:
        raise RuntimeError(
            f"Aether API returned HTTP {status}: "
            f"{response.value.decode('utf-8', errors='replace')}"
        )
    print(response.value.decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
