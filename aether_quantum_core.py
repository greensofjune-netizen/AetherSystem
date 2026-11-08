import math
import sys
import threading
import time

import torch
import torch.nn as nn
from torch.nn import functional as F

# Try importing FastAPI components, gracefully handling clean environmental rollbacks
try:
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
except ImportError:
    print("❌ Missing deployment requirements. Please execute: pip install fastapi uvicorn")
    sys.exit(1)

# =====================================================================
# MODULE 1: VERIFIED CLASSICAL QUANTUM STATE SIMULATOR
# =====================================================================

class StateCollapseAnomalyError(Exception):
    """Custom runtime exception representing volatile wave functional disruptions"""
    pass

class QuantumStateSimulator:
    """Simulates shifts between wave ([W]) and particle ([P]) probability states based on risk matrices"""
    def __init__(self, risk_coherence: float = 0.5, fluctuation_index: float = 0.2):
        self.risk_coherence = max(0.0, min(1.0, risk_coherence))
        self.fluctuation_index = fluctuation_index
        
    def calculate_entropy_index(self, status_vector: list) -> float:
        """Computes current system uncertainty profile metrics using classic Shannon metrics"""
        if not status_vector:
            raise StateCollapseAnomalyError("Cannot resolve metrics over an unobserved null vector.")
        
        # Simple Shannon entropy approximation calculation loop
        entropy = 0.0
        total = sum(status_vector)
        if total == 0:
            return 0.0
        
        for val in status_vector:
            if val > 0:
                p = val / total
                entropy -= p * math.log2(p)
        return round(entropy + (self.fluctuation_index * 0.1), 4)

    def compute_wave_coherence(self) -> dict:
        """Determines the stable alignment index of current wave functions"""
        base_coherence = 1.0 - self.risk_coherence
        harmonic_shift = math.sin(time.time()) * self.fluctuation_index
        calculated_coherence = max(0.0, min(1.0, base_coherence + (harmonic_shift * 0.2)))
        
        # Establish deterministic operational state bounds
        state_label = "[WAVE]" if calculated_coherence >= 0.5 else "[PARTICLE]"
        return {
            "coherence_index": round(calculated_coherence, 4),
            "dominant_state": state_label,
            "system_risk": self.risk_coherence
        }

# =====================================================================
# MODULE 2: MULTI-BEHAVIORAL ROPE LLM TRANSFORMER MATRIX
# =====================================================================

# Hyperparameters
n_embd = 128
n_head = 4
n_layer = 4
block_size = 128
dropout = 0.1
device = 'cuda' if torch.cuda.is_available() else 'cpu'

training_corpus = """
[POETRY] Deep into that darkness peering, long I stood there wondering, fearing, doubting, dreaming dreams no mortal ever dared to dream before.
[HUMOR] I asked the AI engine to write a deep poem about absolute existential dread, and it just suggested I check my Wi-Fi configuration.
[BALANCED] True internal harmony does not mean eliminating chaos entirely, but maintaining a calm and stable equilibrium within the storm.
""" * 30

chars = sorted(list(set(training_corpus)))
vocab_size = len(chars)
stoi = { ch:i for i,ch in enumerate(chars) }
itos = { i:ch for i,ch in enumerate(chars) }
def encode(text: str) -> list[int]:
    return [stoi[character] for character in text]


def decode(token_ids: list[int]) -> str:
    return "".join(itos[token_id] for token_id in token_ids)

def precompute_rope_angles(dim, seq_len):
    inv_freq = 1.0 / (10000.0 ** (torch.arange(0, dim, 2).float() / dim))
    t = torch.arange(seq_len, dtype=torch.float32)
    freqs = torch.outer(t, inv_freq)
    return torch.polar(torch.ones_like(freqs), freqs).to(device)

def rotate_tensor(x, freqs_cis):
    B, T, H, D = x.shape
    x_complex = torch.view_as_complex(x.reshape(B, T, H, -1, 2).contiguous())
    freqs_cis = freqs_cis[:T].view(1, T, 1, -1)
    return torch.view_as_real(x_complex * freqs_cis).view(B, T, H, D)

class RoPEAttentionHead(nn.Module):
    def __init__(self, head_size):
        super().__init__()
        self.head_size = head_size
        self.key = nn.Linear(n_embd, head_size, bias=False)
        self.query = nn.Linear(n_embd, head_size, bias=False)
        self.value = nn.Linear(n_embd, head_size, bias=False)
        self.register_buffer('tril', torch.tril(torch.ones(block_size, block_size)))
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, freqs_cis):
        B, T, C = x.shape
        k = self.key(x).view(B, T, 1, self.head_size)
        q = self.query(x).view(B, T, 1, self.head_size)
        v = self.value(x).view(B, T, 1, self.head_size).squeeze(2)
        
        q = rotate_tensor(q, freqs_cis).squeeze(2)
        k = rotate_tensor(k, freqs_cis).squeeze(2)
        
        wei = q @ k.transpose(-2, -1) * (self.head_size ** -0.5)
        wei = wei.masked_fill(self.tril[:T, :T] == 0, float('-inf'))
        return self.dropout(F.softmax(wei, dim=-1)) @ v

class RoPEMultiHeadAttention(nn.Module):
    def __init__(self, num_heads, head_size):
        super().__init__()
        self.heads = nn.ModuleList([RoPEAttentionHead(head_size) for _ in range(num_heads)])
        self.proj = nn.Linear(n_embd, n_embd)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, freqs_cis):
        out = torch.cat([h(x, freqs_cis) for h in self.heads], dim=-1)
        return self.dropout(self.proj(out))

class RoPETransformerBlock(nn.Module):
    def __init__(self):
        super().__init__()
        self.sa = RoPEMultiHeadAttention(n_head, n_embd // n_head)
        self.ffwd = nn.Sequential(
            nn.Linear(n_embd, 4 * n_embd),
            nn.GELU(),
            nn.Linear(4 * n_embd, n_embd),
            nn.Dropout(dropout),
        )
        self.ln1 = nn.LayerNorm(n_embd)
        self.ln2 = nn.LayerNorm(n_embd)

    def forward(self, x, freqs_cis):
        x = x + self.sa(self.ln1(x), freqs_cis)
        return x + self.ffwd(self.ln2(x))

class IntegratedRoPELLM(nn.Module):
    def __init__(self):
        super().__init__()
        self.token_embedding_table = nn.Embedding(vocab_size, n_embd)
        self.blocks = nn.ModuleList([RoPETransformerBlock() for _ in range(n_layer)])
        self.ln_f = nn.LayerNorm(n_embd)
        self.lm_head = nn.Linear(n_embd, vocab_size)
        self.freqs_cis = precompute_rope_angles(n_embd // n_head, block_size)

    def forward(self, idx):
        x = self.token_embedding_table(idx)
        for block in self.blocks:
            x = block(x, self.freqs_cis)
        return self.lm_head(self.ln_f(x)), None

    @torch.no_grad()
    def generate(self, anchor, max_tokens=60):
        context = encode(anchor)
        idx = torch.tensor([context], dtype=torch.long, device=device)
        for _ in range(max_tokens):
            logits, _ = self(idx[:, -block_size:])
            probs = F.softmax(logits[:, -1, :], dim=-1)
            idx_next = torch.multinomial(probs, num_samples=1)
            idx = torch.cat((idx, idx_next), dim=1)
            if itos[idx_next.item()] == '\n':
                break
        return decode(idx.tolist()[0])

# Instantiate global, warm-trained structural instances
global_model = IntegratedRoPELLM().to(device)
global_simulator = QuantumStateSimulator(risk_coherence=0.35, fluctuation_index=0.15)

# =====================================================================
# MODULE 3: PRODUCTION FASTAPI WEB SERVICE ROUTER INTERFACE
# =====================================================================

app = FastAPI(title="AetherSystem Quantum Core API", version="2.0.0")

class MatrixQuery(BaseModel):
    behavioral_anchor: str = "[BALANCED]"
    max_tokens: int = 60

class SimulationInput(BaseModel):
    status_vector: list = [12, 45, 78, 23, 11]

@app.get("/health")
def api_health_check():
    """Returns local engine uptime metrics and operational safety telemetry"""
    return {"status": "healthy", "engine": "AetherSystem_V2", "listening_port": 8000}

@app.get("/process")
def api_get_quantum_coherence():
    """Exposes real-time wave function metrics directly over local networks"""
    return global_simulator.compute_wave_coherence()

@app.post("/simulate")
def api_calculate_matrix_entropy(payload: SimulationInput):
    """Calculates active Shannon uncertainty bounds over an input numerical matrix"""
    try:
        entropy_score = global_simulator.calculate_entropy_index(payload.status_vector)
        coherence_data = global_simulator.compute_wave_coherence()
        return {
            "calculated_entropy": entropy_score,
            "telemetry_context": coherence_data
        }
    except StateCollapseAnomalyError as err:
        raise HTTPException(status_code=400, detail=str(err))

@app.post("/completion")
def api_generate_behavioral_completion(payload: MatrixQuery):
    """Allows web networks to request context-steered text generations directly"""
    if payload.behavioral_anchor not in ["[POETRY]", "[HUMOR]", "[BALANCED]"]:
        raise HTTPException(status_code=400, detail="Invalid anchor payload key string.")
    
    generated_text = global_model.generate(payload.behavioral_anchor, max_tokens=payload.max_tokens)
    return {"anchor_injected": payload.behavioral_anchor, "response": generated_text}

# =====================================================================
# MODULE 4: PROGRAMMATIC WORKER SCHEDULER & CONSOLE RUNTIME
# =====================================================================

def boot_web_server_backend():
    """Runs local network connections in a separate backend thread container"""
    # Guardrails: Non-loopback client blocking enabled via localhost mapping bindings
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")

def run_system_console():
    """Main terminal processing loop allowing interactive steering modifications"""
    time.sleep(1.5) # Wait for web application background loops to settle cleanly
    print("\n" + "="*70)
    print("🛰️  AETHERSYSTEM MASTER INTERACTIVE ENGINE CONTROL PLATFORM ACTIVE")
    print("="*70)
    print("Local REST API Listening Network: http://127.0.0.1:8000")
    print("Interactive Commands: 1->Poetry | 2->Humor | 3->Telemetry | 'exit'->Halt")
    print("-" * 70)
    
    mapping = {"1": "[POETRY]", "2": "[HUMOR]", "3": "[BALANCED]"}
    
    while True:
        action = input("👉 Enter Selection [1/2/3/exit]: ").strip()
        
        if action.lower() == 'exit':
            print("\n🚨 Initiating complete local stack spin-down procedures. Goodbye friend.")
            break
            
        if action in ["1", "2"]:
            anchor = mapping[action]
            print(f"🔮 Injecting attention steering token: {anchor}")
            print(f"📄 Output: {global_model.generate(anchor)}")
            print("-" * 50)
        elif action == "3":
            metrics = global_simulator.compute_wave_coherence()
            print(f"🔬 Live Simulator Readout: {metrics}")
            print("-" * 50)
        else:
            print("⚠️ Undefined system configuration string.")

# =====================================================================
# REVISED SYSTEM INITIATION PIPELINE (WITH LIGHTWEIGHT MATRIX TRAINING)
# =====================================================================

def pre_train_behavioral_matrix():
    """Optimizes random model weights over the corpus to ensure coherent text output"""
    print("\n⚡ [TRAINING] Warming up hidden matrix nodes on behavioral corpus...")
    
    # Establish a fast, high-performance AdamW optimization lane
    optimizer = torch.optim.AdamW(global_model.parameters(), lr=1e-3)
    global_model.train()
    
    data = torch.tensor(encode(training_corpus), dtype=torch.long)
    batch_size = 32
    total_steps = 600

    # Random windows across the whole corpus so every behavioral anchor is learned
    def sample_batch():
        ix = torch.randint(len(data) - block_size - 1, (batch_size,))
        x = torch.stack([data[i:i + block_size] for i in ix])
        y = torch.stack([data[i + 1:i + block_size + 1] for i in ix])
        return x.to(device), y.to(device)
    
    for step in range(total_steps + 1):
        x_train, y_train = sample_batch()
        logits, _ = global_model(x_train)
        
        # Calculate cross-entropy penalty across output logits vs target labels
        B, T, C = logits.shape
        loss = F.cross_entropy(logits.view(B*T, C), y_train.view(B*T))
        
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        
        if step % 100 == 0:
            print(f"   Optimization Run {step:3d}/{total_steps} | Alignment Cross-Entropy: {loss.item():.4f}")
            
    print("✅ [TRAINING] Matrix weights optimized. Shifting model to execution mode.\n")
    global_model.eval()

if __name__ == "__main__":
    print("=== CORE SYSTEM DIAGNOSTICS & ENGINE MATRIX ACTIVE ===\n")
    
    # 1. First optimize the randomized model layer weights so text output parses cleanly
    pre_train_behavioral_matrix()
    
    # 2. Spin up parallel worker pathways for the FastAPI server loop
    server_thread = threading.Thread(target=boot_web_server_backend, daemon=True)
    server_thread.start()
    
    # 3. Hand control back over to the interactive terminal command center
    try:
        run_system_console()
    except (EOFError, KeyboardInterrupt):
        print("\n🚨 Console closed. Shutting down.")
