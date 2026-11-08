import os
import shutil
import subprocess
import sys
import tempfile

MODELS_DIRECTORY = "/Volumes/Atlas/models"
DEFAULT_MODEL_FILENAME = "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
OLLAMA_MODEL_NAME = "atlas-qwen-coder"


class OfflineBrainBridge:
    """Runs a local GGUF model from the Atlas drive through a subprocess.

    Pure standard library: no compiled Python wheels. Uses `llama-cli` if installed,
    otherwise registers the GGUF with `ollama` and calls `ollama run`.
    """

    def __init__(self, model_filename=DEFAULT_MODEL_FILENAME, models_dir=MODELS_DIRECTORY, timeout=300):
        if not os.path.isdir(models_dir):
            raise FileNotFoundError(f"Models directory not found: {models_dir} (is 'Atlas' plugged in?)")

        self.model_path = os.path.join(models_dir, model_filename)
        if not os.path.isfile(self.model_path):
            raise FileNotFoundError(
                f"Model file not found: {self.model_path}\n"
                f"Available: {self.list_models(models_dir) or 'none'}"
            )

        self.timeout = timeout
        self.llama_cli = shutil.which("llama-cli") or shutil.which("llama-completion")
        self.ollama = shutil.which("ollama")
        if self.llama_cli:
            self.backend = "llama-cli"
        elif self.ollama:
            self.backend = "ollama"
            self._register_with_ollama()
        else:
            raise RuntimeError(
                "No local runtime found. Install one: `brew install llama.cpp` or Ollama (https://ollama.com)."
            )

    @staticmethod
    def list_models(models_dir=MODELS_DIRECTORY):
        if not os.path.isdir(models_dir):
            return []
        return sorted(f for f in os.listdir(models_dir) if f.endswith(".gguf"))

    def _register_with_ollama(self):
        listing = subprocess.run([self.ollama, "list"], capture_output=True, text=True, timeout=60)
        if listing.returncode != 0:
            raise RuntimeError(f"Ollama is not reachable (is `ollama serve` running?): {listing.stderr.strip()}")
        if OLLAMA_MODEL_NAME in listing.stdout:
            return
        with tempfile.TemporaryDirectory() as tmp:
            modelfile = os.path.join(tmp, "Modelfile")
            with open(modelfile, "w") as f:
                f.write(f"FROM {self.model_path}\n")
            created = subprocess.run(
                [self.ollama, "create", OLLAMA_MODEL_NAME, "-f", modelfile],
                capture_output=True, text=True, timeout=self.timeout,
            )
        if created.returncode != 0:
            raise RuntimeError(f"Ollama could not import the model: {created.stderr.strip()}")

    def chat(self, prompt, max_tokens=256):
        if self.backend == "llama-cli":
            cmd = [self.llama_cli, "-m", self.model_path, "-p", prompt, "-n", str(max_tokens),
                   "--no-display-prompt", "-no-cnv"]
        else:
            cmd = [self.ollama, "run", OLLAMA_MODEL_NAME, prompt]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout,
                                    stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Model call timed out after {self.timeout}s")
        if result.returncode != 0:
            raise RuntimeError(f"{self.backend} failed: {result.stderr.strip()}")
        return result.stdout.strip()


if __name__ == "__main__":
    try:
        bridge = OfflineBrainBridge()
        print(f"🧠 [OFFLINE BRAIN] {bridge.model_path} via {bridge.backend}")
        question = " ".join(sys.argv[1:]) or "Write a Python function that reverses a string."
        print(bridge.chat(question))
    except (RuntimeError, FileNotFoundError) as error:
        print(f"❌ [BRIDGE ERROR] {error}")
        sys.exit(1)
