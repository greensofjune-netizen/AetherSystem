import os
import urllib.request

import torch
import torch.nn as nn
from torch.nn import functional as F


# =====================================================================
# PHASE 1: AUTOMATED BACKEND GGUF PATH & MODEL PROCURER
# =====================================================================
def ensure_local_assets():
    """Validates physical layout folder structure and fetches target quantized weights"""
    target_dir = "./models"
    target_file = "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
    full_path = os.path.join(target_dir, target_file)
    
    # Official direct binary mirror link on Hugging Face
    hf_download_url = (
        f"https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF"
        f"/resolve/main/{target_file}"
    )
    
    if not os.path.exists(target_dir):
        print(f"📂 [INFRA] Creating dedicated local folder: {target_dir}")
        os.makedirs(target_dir)
        
    if not os.path.exists(full_path):
        print("🚀 [DOWNLOAD] Sourcing backend model file from Hugging Face Mirror...")
        print(f"🔗 Target: {hf_download_url}")
        print("⏳ Fetching ~1.12 GB model file. Please remain on the line...")
        try:
            # Displays simple incremental download progress indicator block strings
            def progress_tracker(count, block_size, total_size):
                percent = int(count * block_size * 100 / total_size)
                print(f"\r   Downloading Core Matrix... {min(percent, 100)}%", end="")
                
            urllib.request.urlretrieve(hf_download_url, full_path, progress_tracker)
            print(f"\n\n✅ [SUCCESS] Local file verification cleared: {full_path}")
        except Exception as e:
            print(f"\n❌ [ERROR] Automated secure download stream failed: {e}")
            print("💡 Alternative: Run 'pip install huggingface_hub' and execute:")
            print(f"   huggingface-cli download Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF {target_file} --local-dir ./models --local-dir-use-symlinks False")
    else:
        print(f"✅ [INFRA] Valid local model path cleared: {full_path}")

# =====================================================================
# PHASE 2: ADVANCED TRANSFORMER ARCHITECTURE UPGRADE (ROPE INTEGRATION)
# =====================================================================
# Architecture Configurations
batch_size = 32
block_size = 128
max_iters = 800
eval_interval = 200
learning_rate = 4e-4
device = 'cuda' if torch.cuda.is_available() else 'cpu'
n_embd = 128
n_head = 4
n_layer = 4
dropout = 0.1

# Anchored matrix behavioral profiling corpus
training_corpus = """
[POETRY] Deep into that darkness peering, long I stood there wondering, fearing, doubting, dreaming dreams no mortal ever dared to dream before.
[HUMOR] I asked the AI engine to write a deep poem about absolute existential dread, and it just suggested I check my Wi-Fi configuration.
[BALANCED] True internal harmony does not mean eliminating chaos entirely, but maintaining a calm and stable equilibrium within the storm.
[POETRY] Shadows dance across the silent stone, the midnight sky reveals a brilliant cosmic sea, a quiet observer standing entirely alone.
[HUMOR] They say artificial intelligence is a threat to humanity, but my code still crashes if someone hits an empty submit button.
[BALANCED] Unsupervised frameworks can fall into volatile states, requiring structural grounding rules to gently steer human intention safely.
""" * 40

chars = sorted(list(set(training_corpus)))
vocab_size = len(chars)
stoi = { ch:i for i,ch in enumerate(chars) }
itos = { i:ch for i,ch in enumerate(chars) }
def encode(text: str) -> list[int]:
    return [stoi[character] for character in text]


def decode(token_ids: list[int]) -> str:
    return "".join(itos[token_id] for token_id in token_ids)

def precompute_rope_frequencies(dim, seq_len, theta=10000.0):
    """Precomputes rotation angles in complex space for RoPE coordinate tracking"""
    assert dim % 2 == 0
    inv_freq = 1.0 / (theta ** (torch.arange(0, dim, 2).float() / dim))
    t = torch.arange(seq_len, dtype=torch.float32)
    freqss = torch.outer(t, inv_freq) # (seq_len, dim // 2)
    freqs_cis = torch.polar(torch.ones_like(freqss), freqss) # Transform to complex coordinates
    return freqs_cis.to(device)

def apply_rotary_embeddings(x, freqs_cis):
    """Rotates Query and Key matrix tensors using the precomputed rotation angles"""
    # x shape: (B, T, num_heads, head_size)
    B, T, H, D = x.shape
    x_reshaped = x.reshape(B, T, H, -1, 2) # Group components into pairs
    x_complex = torch.view_as_complex(x_reshaped.contiguous())
    
    # Reshape frequencies to match tensor alignment: (1, T, 1, D // 2)
    freqs_cis = freqs_cis[:T].view(1, T, 1, -1)
    x_rotated = x_complex * freqs_cis
    
    # Flatten complex coordinates back into the normal real-number matrix space
    x_out = torch.view_as_real(x_rotated).view(B, T, H, D)
    return x_out

class AdvancedRoPEAttentionHead(nn.Module):
    """Causal Self-Attention head leveraging Rotary Position Embeddings (RoPE)"""
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
        
        # Project tokens into attention roles, keeping head dimensions isolated
        k = self.key(x).view(B, T, 1, self.head_size)   # (B, T, 1, head_size)
        q = self.query(x).view(B, T, 1, self.head_size)   # (B, T, 1, head_size)
        v = self.value(x).view(B, T, 1, self.head_size).squeeze(2) # (B, T, head_size)
        
        # Apply complex positional rotation vectors
        q = apply_rotary_embeddings(q, freqs_cis).squeeze(2) # (B, T, head_size)
        k = apply_rotary_embeddings(k, freqs_cis).squeeze(2) # (B, T, head_size)
        
        # Compute multi-dimensional attention matrix affinities
        wei = q @ k.transpose(-2, -1) * (self.head_size ** -0.5)
        wei = wei.masked_fill(self.tril[:T, :T] == 0, float('-inf'))
        wei = F.softmax(wei, dim=-1)
        wei = self.dropout(wei)
        
        return wei @ v # (B, T, head_size)

class RoPEMultiHeadAttention(nn.Module):
    def __init__(self, num_heads, head_size):
        super().__init__()
        self.heads = nn.ModuleList([AdvancedRoPEAttentionHead(head_size) for _ in range(num_heads)])
        self.proj = nn.Linear(n_embd, n_embd)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, freqs_cis):
        out = torch.cat([h(x, freqs_cis) for h in self.heads], dim=-1)
        out = self.dropout(self.proj(out))
        return out

class GeLUPredictionFFN(nn.Module):
    def __init__(self, n_embd):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_embd, 4 * n_embd),
            nn.GELU(),
            nn.Linear(4 * n_embd, n_embd),
            nn.Dropout(dropout),
        )
    def forward(self, x): return self.net(x)

class RoPETransformerBlock(nn.Module):
    def __init__(self, n_embd, n_head):
        super().__init__()
        head_size = n_embd // n_head
        self.sa = RoPEMultiHeadAttention(n_head, head_size)
        self.ffwd = GeLUPredictionFFN(n_embd)
        self.ln1 = nn.LayerNorm(n_embd)
        self.ln2 = nn.LayerNorm(n_embd)

    def forward(self, x, freqs_cis):
        x = x + self.sa(self.ln1(x), freqs_cis)
        x = x + self.ffwd(self.ln2(x))
        return x

class EvolutionaryRoPELLM(nn.Module):
    def __init__(self):
        super().__init__()
        self.token_embedding_table = nn.Embedding(vocab_size, n_embd)
        self.blocks = nn.ModuleList([RoPETransformerBlock(n_embd, n_head=n_head) for _ in range(n_layer)])
        self.ln_f = nn.LayerNorm(n_embd)
        self.lm_head = nn.Linear(n_embd, vocab_size)
        
        # Precalculate the positional rotation frequency vectors
        self.freqs_cis = precompute_rope_frequencies(n_embd // n_head, block_size)

    def forward(self, idx, targets=None):
        B, T = idx.shape
        x = self.token_embedding_table(idx) # (B, T, n_embd)
        
        # RoPE bypasses static embedding addition. We pass coordinates down directly.
        for block in self.blocks:
            x = block(x, self.freqs_cis)
            
        x = self.ln_f(x)
        logits = self.lm_head(x)

        loss = None
        if targets is not None:
            B, T, C = logits.shape
            logits = logits.view(B*T, C)
            targets = targets.view(B*T)
            loss = F.cross_entropy(logits, targets)

        return logits, loss

    def generate(self, prefix_string, max_new_tokens=100):
        context = encode(prefix_string)
        idx = torch.tensor([context], dtype=torch.long, device=device)
        for _ in range(max_new_tokens):
            idx_cond = idx[:, -block_size:]
            logits, _ = self(idx_cond)
            logits = logits[:, -1, :]
            probs = F.softmax(logits, dim=-1)
            idx_next = torch.multinomial(probs, num_samples=1)
            idx = torch.cat((idx, idx_next), dim=1)
            if itos[idx_next.item()] == '\n' and len(idx[0]) > 50:
                break
        return decode(idx[0].tolist())

# Data optimization loops
data_tensor = torch.tensor(encode(training_corpus), dtype=torch.long)
n_split = int(0.9 * len(data_tensor))
train_data = data_tensor[:n_split]
val_data = data_tensor[n_split:]

def get_batch(split):
    dataset = train_data if split == 'train' else val_data
    ix = torch.randint(len(dataset) - block_size, (batch_size,))
    x = torch.stack([dataset[i:i+block_size] for i in ix])
    y = torch.stack([dataset[i+1:i+block_size+1] for i in ix])
    return x.to(device), y.to(device)

def train_upgraded_engine():
    # NOTE: the source provided ended at this signature; body below is a minimal completion.
    model = EvolutionaryRoPELLM().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)

    @torch.no_grad()
    def estimate_loss(iters=20):
        model.eval()
        out = {}
        for split in ('train', 'val'):
            losses = torch.zeros(iters)
            for k in range(iters):
                xb, yb = get_batch(split)
                _, loss = model(xb, yb)
                losses[k] = loss.item()
            out[split] = losses.mean().item()
        model.train()
        return out

    for it in range(max_iters):
        if it % eval_interval == 0 or it == max_iters - 1:
            losses = estimate_loss()
            print(f"step {it}: train loss {losses['train']:.4f}, val loss {losses['val']:.4f}")
        xb, yb = get_batch('train')
        _, loss = model(xb, yb)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()

    model.eval()
    print(model.generate("[POETRY] ", max_new_tokens=200))
    return model

if __name__ == "__main__":
    ensure_local_assets()
    train_upgraded_engine()
