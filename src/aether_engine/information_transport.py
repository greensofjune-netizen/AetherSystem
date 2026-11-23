"""Educational packet encoding and simulated radio-transport lifecycle."""

from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any

MAX_PAYLOAD_BYTES = 64 * 1024
DEFAULT_CHUNK_BYTES = 128
TRANSPORT_PRINCIPLE_PATH = Path(__file__).resolve().parents[2] / (
    "radio_information_principles.json"
)
INSTALLED_TRANSPORT_PRINCIPLE_PATH = (
    Path(sys.prefix) / "share" / "aether-engine" / "radio_information_principles.json"
)


def load_transport_principles() -> dict[str, Any]:
    source = (
        TRANSPORT_PRINCIPLE_PATH
        if TRANSPORT_PRINCIPLE_PATH.is_file()
        else INSTALLED_TRANSPORT_PRINCIPLE_PATH
    )
    if source.is_symlink():
        raise ValueError("Transport principles cannot be loaded from a symlink.")
    try:
        principles = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Transport principles could not be loaded.") from error
    if (
        not isinstance(principles, dict)
        or principles.get("schema_version") != 1
        or not isinstance(principles.get("stages"), list)
        or not isinstance(principles.get("principles"), list)
    ):
        raise ValueError("Transport principles schema is invalid.")
    return principles


def _bytes_to_bits(payload: bytes) -> list[int]:
    return [(byte >> shift) & 1 for byte in payload for shift in range(7, -1, -1)]


def _bits_to_bytes(bits: list[int]) -> bytes:
    if len(bits) % 8:
        raise ValueError("Bit stream length must be a multiple of eight.")
    values = bytearray()
    for offset in range(0, len(bits), 8):
        value = 0
        for bit in bits[offset : offset + 8]:
            value = (value << 1) | bit
        values.append(value)
    return bytes(values)


def simulate_transport(
    value: Any,
    *,
    bit_error_rate: float = 0.0,
    seed: int = 0,
    chunk_bytes: int = DEFAULT_CHUNK_BYTES,
) -> dict[str, Any]:
    """Serialize, model BPSK transport, decode, and verify; never transmit."""
    if (
        isinstance(bit_error_rate, bool)
        or not isinstance(bit_error_rate, (int, float))
        or not 0.0 <= bit_error_rate <= 1.0
    ):
        raise ValueError("Bit error rate must be between 0 and 1.")
    if type(seed) is not int or seed < 0:
        raise ValueError("Seed must be a non-negative integer.")
    if type(chunk_bytes) is not int or not 1 <= chunk_bytes <= 4096:
        raise ValueError("Chunk size must be between 1 and 4096 bytes.")
    try:
        payload = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise ValueError("Payload must be JSON serializable UTF-8 data.") from error
    if not payload or len(payload) > MAX_PAYLOAD_BYTES:
        raise ValueError(f"Payload must contain 1-{MAX_PAYLOAD_BYTES} UTF-8 bytes.")

    digest = hashlib.sha256(payload).hexdigest()
    chunks = [payload[index : index + chunk_bytes] for index in range(0, len(payload), chunk_bytes)]
    bits = _bytes_to_bits(b"".join(chunks))
    symbols = [1.0 if bit else -1.0 for bit in bits]
    rng = random.Random(seed)
    received_symbols = [
        -symbol if rng.random() < bit_error_rate else symbol for symbol in symbols
    ]
    decoded_bits = [1 if symbol > 0 else 0 for symbol in received_symbols]
    decoded = _bits_to_bytes(decoded_bits)
    received_digest = hashlib.sha256(decoded).hexdigest()
    return {
        "scope": "EDUCATIONAL_PACKET_AND_BPSK_CHANNEL_SIMULATION",
        "transmission_performed": False,
        "payload_bytes": len(payload),
        "chunk_count": len(chunks),
        "chunk_bytes": chunk_bytes,
        "bit_count": len(bits),
        "modeled_symbols": len(symbols),
        "bit_error_rate_requested": float(bit_error_rate),
        "bit_errors_modeled": sum(
            original != received for original, received in zip(bits, decoded_bits)
        ),
        "integrity_valid": received_digest == digest,
        "source_sha256": digest,
        "received_sha256": received_digest,
        "lifecycle": load_transport_principles()["stages"],
        "decoded_payload_matches": decoded == payload,
        "limitations": [
            "BPSK symbols are an idealized in-memory model.",
            "No RF waveform, antenna, transmitter, receiver, or live channel was used.",
            "No transmission permission or field performance is established.",
        ],
    }
