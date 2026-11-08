from __future__ import annotations

import argparse
import http.client
import importlib
import ipaddress
import json
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_CONFIG_SUFFIXES = {".py", ".json", ".yaml", ".yml", ".ini", ".toml"}
_EXCLUDED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "build",
    "dist",
    "generated",
    "temp",
    ".aether-backups",
}
_DEFAULT_EXTERNAL_MODEL_DIRS = (Path("/Volumes/Atlas/models"),)
_SENSITIVE_FILE_MARKERS = ("secret", "credential", "token", "password", "private")
_MODEL_PATH_PATTERN = re.compile(
    r"\b(?:gguf|model_path|model_dir|model_file|llm_path)\b",
    re.IGNORECASE,
)
_TRAINING_DATA = """
[POETRY] A quiet observer stands beneath the brilliant cosmic sea.
[HUMOR] My code still crashes if someone hits an empty submit button.
[BALANCED] Maintain a calm and stable equilibrium within the storm.
[POETRY] Shadows dance across the silent stone beneath the midnight sky.
[HUMOR] The model is ready; the README is still waiting for its update.
[BALANCED] Ground each response in clear evidence and careful reasoning.
""" * 50

COSMOLOGY_CORE_CONFIG: dict[str, Any] = {
    "target": "Friedmann_Einstein_1931_Model",
    "status": "REQUIRES_VERIFICATION",
    "verified_metrics": {
        "expansion_parameter_D": "1 / (c * P) * (dP / dt)",
        "density_field_density": "kappa * rho == 3 * (D**2) / ((P_0 - P) / P)",
        "spatial_curvature": "positive_closed_universe",
    },
    "historical_anomaly_archive": {
        "event": "Oxford Lecture Blackboard (May 16, 1931)",
        "author": "Albert Einstein",
        "error_type": "Unit conversion scaling anomaly (Megaparsecs to Centimeters)",
        "impact": {
            "density_rho_observed": 1e-26,
            "cosmic_radius_P_observed": 1e8,
        },
        "system_reminder": (
            "Preserved as a claim to verify; do not treat as established fact."
        ),
    },
}


class OllamaConnectionError(RuntimeError):
    """Raised when the local Ollama API cannot provide a valid response."""


class AetherHistorian:
    """Send historian prompts to a loopback Ollama instance."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 11434,
        model: str = "aethersystem-core",
        timeout: float = 300,
    ) -> None:
        normalized_host = host.strip().casefold() if isinstance(host, str) else ""
        if normalized_host not in {"localhost", "localhost."}:
            try:
                address = ipaddress.ip_address(normalized_host)
            except ValueError as error:
                raise ValueError("Ollama host must be localhost or a loopback IP.") from error
            if not address.is_loopback:
                raise ValueError("Ollama host must be localhost or a loopback IP.")
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("Ollama port must be between 1 and 65535.")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("Ollama model name cannot be empty.")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or timeout <= 0
        ):
            raise ValueError("Ollama timeout must be greater than zero.")

        self.host = normalized_host
        self.port = port
        self.model = model.strip()
        self.timeout = timeout
        self.endpoint = "/api/generate"

    def query_brain(self, prompt: str, *, system: str | None = None) -> str:
        """Request one non-streaming response from the local Ollama API."""
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt cannot be empty.")

        payload = {
            "model": self.model,
            "prompt": prompt.strip(),
            "stream": False,
            "options": {"temperature": 0.2},
        }
        if system is not None:
            if not isinstance(system, str) or not system.strip():
                raise ValueError("System instruction cannot be empty.")
            payload["system"] = system.strip()
        connection = http.client.HTTPConnection(
            self.host, self.port, timeout=self.timeout
        )
        try:
            connection.request(
                "POST",
                self.endpoint,
                body=json.dumps(payload, ensure_ascii=False),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            if response.status != 200:
                raise OllamaConnectionError(
                    f"Ollama returned HTTP {response.status} {response.reason}."
                )
            raw_data = response.read(1_048_577)
        except (OSError, http.client.HTTPException) as error:
            raise OllamaConnectionError(
                f"Could not communicate with local Ollama at "
                f"{self.host}:{self.port}: {error}"
            ) from error
        finally:
            connection.close()

        if len(raw_data) > 1_048_576:
            raise OllamaConnectionError("Ollama response exceeded the 1 MiB limit.")
        try:
            data = json.loads(raw_data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise OllamaConnectionError(
                "Ollama returned an invalid JSON response."
            ) from error
        if not isinstance(data, dict):
            raise OllamaConnectionError("Ollama response must be a JSON object.")
        result = data.get("response")
        if not isinstance(result, str) or not result.strip():
            raise OllamaConnectionError(
                "Ollama response did not contain generated text."
            )
        return result.strip()

    def run_historian_telemetry(self) -> str:
        """Ask the local model to review the supplied, unverified archive."""
        prompt = (
            "Review this user-provided cosmology configuration and historical "
            "anomaly archive. Treat every formula and historical detail as an "
            "unverified claim: do not repeat it as established fact. This local "
            "model cannot independently consult external sources, so state what "
            "can be checked for internal consistency and what needs source "
            "verification. Explain how recording a verified correction could "
            "improve future validation resilience.\n\n"
            f"{json.dumps(COSMOLOGY_CORE_CONFIG, ensure_ascii=False, indent=2)}"
        )
        return self.query_brain(prompt)


def _is_sensitive_filename(name: str) -> bool:
    lowered = name.casefold()
    return (
        lowered.startswith(".env")
        or any(marker in lowered for marker in _SENSITIVE_FILE_MARKERS)
    )


def _external_model_directories(
    explicit: Sequence[str | Path] | None,
) -> list[Path]:
    """Resolve extra model directories, such as ones on external volumes."""
    if explicit is None:
        configured = os.environ.get("AETHER_EXTERNAL_MODEL_DIRS", "")
        candidates: list[Path] = [
            *_DEFAULT_EXTERNAL_MODEL_DIRS,
            *(
                Path(entry).expanduser()
                for entry in configured.split(os.pathsep)
                if entry.strip()
            ),
        ]
        volumes = Path("/Volumes")
        try:
            candidates.extend(
                volume / "models"
                for volume in sorted(volumes.iterdir())
                if not volume.is_symlink()
            )
        except OSError:
            pass
    else:
        candidates = [Path(entry).expanduser() for entry in explicit]

    resolved: list[Path] = []
    for candidate in candidates:
        try:
            if not candidate.is_dir():
                continue
            path = candidate.resolve()
        except OSError:
            continue
        # Skip folders already covered by an earlier directory's recursive scan.
        if not any(path == kept or kept in path.parents for kept in resolved):
            resolved.append(path)
    return resolved


def _find_gguf_weights(directory: Path) -> list[Path]:
    """List regular .gguf files below a directory without following symlinks."""
    weights: list[Path] = []
    for current_root, directories, filenames in os.walk(directory):
        current_path = Path(current_root)
        directories[:] = sorted(
            name for name in directories if not (current_path / name).is_symlink()
        )
        for filename in sorted(filenames):
            path = current_path / filename
            if path.suffix.casefold() == ".gguf" and path.is_file() and not path.is_symlink():
                weights.append(path)
    return weights


def search_for_model_paths(
    root: str | Path = ".",
    external_model_dirs: Sequence[str | Path] | None = None,
) -> list[tuple[Path, int]]:
    """Find model-path references without printing source-line contents.

    GGUF weights are also listed from the local model directories and from
    external model directories. When ``external_model_dirs`` is omitted, the
    ``AETHER_EXTERNAL_MODEL_DIRS`` environment variable (os.pathsep-separated)
    and ``/Volumes/*/models`` are checked.
    """
    scan_root = Path(root).expanduser().resolve()
    if not scan_root.is_dir():
        raise ValueError(f"Scan root is not a directory: {scan_root}")

    matches: list[tuple[Path, int]] = []
    for current_root, directories, filenames in os.walk(scan_root):
        current_path = Path(current_root)
        directories[:] = sorted(
            name
            for name in directories
            if name not in _EXCLUDED_DIRECTORIES
            and not (current_path / name).is_symlink()
        )
        for filename in sorted(filenames):
            path = current_path / filename
            if (
                path.suffix.casefold() not in _CONFIG_SUFFIXES
                or path.is_symlink()
                or _is_sensitive_filename(filename)
            ):
                continue
            try:
                with path.open(encoding="utf-8") as source_file:
                    for line_number, line in enumerate(source_file, start=1):
                        if _MODEL_PATH_PATTERN.search(line):
                            matches.append((path.relative_to(scan_root), line_number))
            except (OSError, UnicodeError) as error:
                print(
                    f"Warning: could not read {path.relative_to(scan_root)}: {error}",
                    file=sys.stderr,
                )

    if matches:
        print("Model-path references (source contents omitted):")
        for path, line_number in matches:
            print(f"  {path}:{line_number}")
    else:
        print("No model-path references found.")

    model_directories = ("models", "model", "weights", "bin")
    existing_directories = [
        name for name in model_directories if (scan_root / name).is_dir()
    ]
    if existing_directories:
        print("Model directories found: " + ", ".join(existing_directories))
    else:
        print("No common local model directories found.")

    weight_sources = [scan_root / name for name in existing_directories]
    weight_sources.extend(_external_model_directories(external_model_dirs))
    found_weights = False
    for source in weight_sources:
        weights = _find_gguf_weights(source)
        if weights:
            found_weights = True
            print(f"GGUF weights in {source}:")
            for weight in weights:
                print(f"  {weight.relative_to(source)} ({weight.stat().st_size} bytes)")
    if not found_weights:
        print("No GGUF weights found in local or external model directories.")
    return matches


def _build_model_class(
    torch: Any,
    nn: Any,
    functional: Any,
    *,
    n_embd: int,
    n_head: int,
    n_layer: int,
    block_size: int,
    dropout: float,
) -> type[Any]:
    head_size = n_embd // n_head

    class Head(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.key = nn.Linear(n_embd, head_size, bias=False)
            self.query = nn.Linear(n_embd, head_size, bias=False)
            self.value = nn.Linear(n_embd, head_size, bias=False)
            self.register_buffer(
                "tril", torch.tril(torch.ones(block_size, block_size))
            )
            self.dropout = nn.Dropout(dropout)

        def forward(self, inputs: Any) -> Any:
            _, sequence_length, channels = inputs.shape
            keys = self.key(inputs)
            queries = self.query(inputs)
            weights = queries @ keys.transpose(-2, -1) * (channels**-0.5)
            weights = weights.masked_fill(
                self.tril[:sequence_length, :sequence_length] == 0,
                float("-inf"),
            )
            weights = self.dropout(functional.softmax(weights, dim=-1))
            return weights @ self.value(inputs)

    class MultiHeadAttention(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.heads = nn.ModuleList([Head() for _ in range(n_head)])
            self.projection = nn.Linear(n_embd, n_embd)
            self.dropout = nn.Dropout(dropout)

        def forward(self, inputs: Any) -> Any:
            output = torch.cat([head(inputs) for head in self.heads], dim=-1)
            return self.dropout(self.projection(output))

    class FeedForward(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.network = nn.Sequential(
                nn.Linear(n_embd, 4 * n_embd),
                nn.ReLU(),
                nn.Linear(4 * n_embd, n_embd),
                nn.Dropout(dropout),
            )

        def forward(self, inputs: Any) -> Any:
            return self.network(inputs)

    class Block(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.attention = MultiHeadAttention()
            self.feed_forward = FeedForward()
            self.norm_attention = nn.LayerNorm(n_embd)
            self.norm_feed_forward = nn.LayerNorm(n_embd)

        def forward(self, inputs: Any) -> Any:
            inputs = inputs + self.attention(self.norm_attention(inputs))
            return inputs + self.feed_forward(self.norm_feed_forward(inputs))

    class MultiBehaviorLLM(nn.Module):
        def __init__(self, vocabulary_size: int) -> None:
            super().__init__()
            self.token_embedding = nn.Embedding(vocabulary_size, n_embd)
            self.position_embedding = nn.Embedding(block_size, n_embd)
            self.blocks = nn.Sequential(*(Block() for _ in range(n_layer)))
            self.final_norm = nn.LayerNorm(n_embd)
            self.language_head = nn.Linear(n_embd, vocabulary_size)

        def forward(self, indices: Any, targets: Any = None) -> tuple[Any, Any]:
            _, sequence_length = indices.shape
            positions = torch.arange(sequence_length, device=indices.device)
            embeddings = self.token_embedding(indices) + self.position_embedding(
                positions
            )
            logits = self.language_head(self.final_norm(self.blocks(embeddings)))
            loss = None
            if targets is not None:
                batch, sequence, channels = logits.shape
                loss = functional.cross_entropy(
                    logits.view(batch * sequence, channels),
                    targets.view(batch * sequence),
                )
            return logits, loss

        def generate_behavioral_response(
            self,
            anchor: str,
            encode: Any,
            decode: Any,
            vocabulary: dict[int, str],
            device: str,
            *,
            max_new_tokens: int = 100,
        ) -> str:
            context = encode(anchor)
            indices = torch.tensor([context], dtype=torch.long, device=device)
            for _ in range(max_new_tokens):
                conditioned = indices[:, -block_size:]
                logits, _ = self(conditioned)
                probabilities = functional.softmax(logits[:, -1, :], dim=-1)
                next_token = torch.multinomial(probabilities, num_samples=1)
                indices = torch.cat((indices, next_token), dim=1)
                if vocabulary[next_token.item()] == "\n" and indices.shape[1] > 40:
                    break
            return decode(indices[0].tolist())

    return MultiBehaviorLLM


def run_llm_pipeline(
    *,
    iterations: int = 1_000,
    seed: int = 0,
    requested_device: str = "auto",
) -> None:
    """Train and sample the optional character-level behavior demonstration."""
    if not 1 <= iterations <= 1_000:
        raise ValueError("Training iterations must be between 1 and 1000.")
    if requested_device not in {"auto", "cpu", "cuda"}:
        raise ValueError("Device must be 'auto', 'cpu', or 'cuda'.")
    try:
        torch = importlib.import_module("torch")
    except ModuleNotFoundError as error:
        if error.name != "torch":
            raise
        raise RuntimeError(
            "The behavioral demo requires PyTorch. Install the optional "
            "PyTorch dependency for your platform, then rerun with --train."
        ) from error

    functional = importlib.import_module("torch.nn.functional")
    nn = torch.nn
    if requested_device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested, but it is not available.")
    device = (
        "cuda" if requested_device == "auto" and torch.cuda.is_available()
        else "cpu" if requested_device == "auto"
        else requested_device
    )

    batch_size = 32
    block_size = 128
    eval_interval = 200
    eval_iters = 20
    learning_rate = 3e-4
    n_embd = 128
    n_head = 4
    n_layer = 4
    dropout = 0.1
    characters = sorted(set(_TRAINING_DATA))
    vocabulary_size = len(characters)
    stoi = {character: index for index, character in enumerate(characters)}
    itos = {index: character for index, character in enumerate(characters)}

    def encode(text: str) -> list[int]:
        try:
            return [stoi[character] for character in text]
        except KeyError as error:
            raise ValueError(
                f"Training data does not contain character {error.args[0]!r}."
            ) from error

    def decode(tokens: list[int]) -> str:
        return "".join(itos[token] for token in tokens)

    data = torch.tensor(encode(_TRAINING_DATA), dtype=torch.long)
    split_index = int(0.9 * len(data))
    datasets = {"train": data[:split_index], "val": data[split_index:]}
    if any(len(dataset) <= block_size for dataset in datasets.values()):
        raise ValueError("Training corpus must exceed the context window.")

    def get_batch(split: str) -> tuple[Any, Any]:
        dataset = datasets[split]
        starts = torch.randint(len(dataset) - block_size, (batch_size,))
        inputs = torch.stack([dataset[index : index + block_size] for index in starts])
        targets = torch.stack(
            [dataset[index + 1 : index + block_size + 1] for index in starts]
        )
        return inputs.to(device), targets.to(device)

    model_type = _build_model_class(
        torch,
        nn,
        functional,
        n_embd=n_embd,
        n_head=n_head,
        n_layer=n_layer,
        block_size=block_size,
        dropout=dropout,
    )
    torch.manual_seed(seed)
    model = model_type(vocabulary_size).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)

    @torch.no_grad()
    def estimate_loss() -> dict[str, float]:
        model.eval()
        losses: dict[str, float] = {}
        try:
            for split in ("train", "val"):
                measurements = torch.zeros(eval_iters)
                for index in range(eval_iters):
                    inputs, targets = get_batch(split)
                    _, loss = model(inputs, targets)
                    measurements[index] = loss.item()
                losses[split] = measurements.mean().item()
        finally:
            model.train()
        return losses

    for iteration in range(iterations):
        if iteration % eval_interval == 0:
            losses = estimate_loss()
            print(
                f"Iteration {iteration:4d}: "
                f"train loss {losses['train']:.4f}, "
                f"validation loss {losses['val']:.4f}"
            )
        inputs, targets = get_batch("train")
        _, loss = model(inputs, targets)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()

    print("Behavioral demonstration model trained.")
    for anchor in ("[POETRY]", "[HUMOR]", "[BALANCED]"):
        print(
            model.generate_behavioral_response(
                anchor, encode, decode, itos, device
            )
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scan-root",
        type=Path,
        default=Path.cwd(),
        help="directory to scan for model-path references",
    )
    parser.add_argument(
        "--train",
        action="store_true",
        help="run the optional PyTorch behavior-model demonstration",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1_000,
        help="training steps (1-1000; only used with --train)",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument(
        "--telemetry",
        action="store_true",
        help="ask aethersystem-core to review the unverified historian archive",
    )
    parser.add_argument("--ollama-host", default="localhost")
    parser.add_argument("--ollama-port", type=int, default=11434)
    parser.add_argument("--ollama-model", default="aethersystem-core")
    parser.add_argument(
        "--ollama-timeout",
        type=float,
        default=300,
        help="maximum seconds to wait for the local model (default: 300)",
    )
    arguments = parser.parse_args(argv)

    try:
        search_for_model_paths(arguments.scan_root)
        if arguments.telemetry:
            historian = AetherHistorian(
                host=arguments.ollama_host,
                port=arguments.ollama_port,
                model=arguments.ollama_model,
                timeout=arguments.ollama_timeout,
            )
            print("\n=== Local Core Intelligence Feedback ===")
            print(historian.run_historian_telemetry())
        if arguments.train:
            run_llm_pipeline(
                iterations=arguments.iterations,
                seed=arguments.seed,
                requested_device=arguments.device,
            )
    except (OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
