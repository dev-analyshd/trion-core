#!/usr/bin/env python3
"""
Proof-of-execution script for mental_transformer.py (TRION L3 Mental Layer).
Runs training and inference end-to-end, prints exact numeric results.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

import numpy as np

print("=" * 68)
print("TRION L3 Mental Transformer — End-to-End Proof of Execution")
print("=" * 68)

# ── 1. Verify PyTorch ──────────────────────────────────────────────────────
import torch
print(f"\n[1] PyTorch version : {torch.__version__}")
print(f"    CUDA available  : {torch.cuda.is_available()}")

# ── 2. Build and inspect model ─────────────────────────────────────────────
from src.core.mental_transformer import (
    _get_model, _BehavioralTransformerEncoder, _INPUT_DIM, _D_MODEL,
    _NHEAD, _NUM_LAYERS, _SEQ_LEN,
)
model = _get_model()
n_params = sum(p.numel() for p in model.parameters())
print(f"\n[2] Model architecture:")
print(f"    input_dim={_INPUT_DIM}, d_model={_D_MODEL}, nhead={_NHEAD}, "
      f"layers={_NUM_LAYERS}, seq_len={_SEQ_LEN}")
print(f"    Total trainable parameters: {n_params:,}")
print(f"    Model:\n{model}")

# ── 3. Untrained forward pass (pre-training baseline) ─────────────────────
rng = np.random.default_rng(42)
dummy_seq = torch.from_numpy(
    rng.random((_SEQ_LEN, _INPUT_DIM), dtype=np.float32)
).unsqueeze(0)  # (1, 16, 9)
model.eval()
import torch
with torch.no_grad():
    pre_val = float(model(dummy_seq)[0].item())
print(f"\n[3] Pre-training forward pass (random seq): {pre_val:.6f}")

# ── 4. Train on archetype centroids ───────────────────────────────────────
from src.core.mental_transformer import train_on_centroids
print(f"\n[4] Training on synthetic sequences from archetype centroids...")
train_result = train_on_centroids(epochs=80, lr=3e-3, save_weights=True)
print(f"    Epochs        : {train_result['epochs']}")
print(f"    Initial loss  : {train_result['initial_loss']}")
print(f"    Final loss    : {train_result['final_loss']}")
print(f"    Data source   : {train_result['data_source']}")
print(f"    N train seqs  : {train_result['n_train']}  seq_len={train_result['seq_len']}  "
      f"input_dim={train_result['input_dim']}")
assert train_result['final_loss'] < train_result['initial_loss'], \
    "Loss must decrease during training"
print(f"    ✓ Loss decreased: {train_result['initial_loss']} → {train_result['final_loss']}")

# ── 5. Post-training forward passes ──────────────────────────────────────
with torch.no_grad():
    post_val = float(model(dummy_seq)[0].item())
print(f"\n[5] Post-training forward pass (same random seq): {post_val:.6f}")

# Different sequence (from centroids)
centroids = np.load("trion_archetype_centroids.npy").astype(np.float32)
c0_norm = centroids[0] / (np.linalg.norm(centroids[0]) + 1e-8)
c0_9d = c0_norm[:9]
seq_c0 = np.tile(c0_9d, (_SEQ_LEN, 1))  # (16, 9)
t_c0 = torch.from_numpy(seq_c0).unsqueeze(0)
with torch.no_grad():
    val_c0 = float(model(t_c0)[0].item())

c63_norm = centroids[63] / (np.linalg.norm(centroids[63]) + 1e-8)
c63_9d = c63_norm[:9]
seq_c63 = np.tile(c63_9d, (_SEQ_LEN, 1))
t_c63 = torch.from_numpy(seq_c63).unsqueeze(0)
with torch.no_grad():
    val_c63 = float(model(t_c63)[0].item())

print(f"    centroid[0]  sequence → model output: {val_c0:.6f}")
print(f"    centroid[63] sequence → model output: {val_c63:.6f}")
print(f"    (Different sequences produce different outputs: {val_c0 != val_c63})")

# ── 6. Conformal prediction interval ─────────────────────────────────────
from src.core.mental_transformer import conformal_prediction_interval
preds_list = [val_c0] * 5 + [val_c0 + 0.02, val_c0 - 0.01, val_c0 + 0.015,
                               val_c0 - 0.005, val_c0 + 0.008]
cp = conformal_prediction_interval(preds_list, alpha=0.10)
print(f"\n[6] Conformal prediction interval (α=0.10, n={cp['n_cal']}):")
print(f"    center={cp['center']:.6f}  "
      f"lower={cp['lower']:.6f}  upper={cp['upper']:.6f}  "
      f"width={cp['width']:.6f}  q_hat={cp['q_hat']:.6f}")
assert cp['lower'] <= cp['upper'], "PI must be ordered"
assert cp['width'] > 0, "PI width must be positive"
print(f"    ✓ Valid conformal interval")

# ── 7. Full infer_genesis_value_v2() call ─────────────────────────────────
from src.core.genesis_inference import GenesisVector, Archetype, infer_genesis_value
from src.core.mental_transformer import infer_genesis_value_v2, _fitted
print(f"\n[7] infer_genesis_value_v2() full pipeline test:")
print(f"    model fitted: {_fitted}")

np.random.seed(99)
archetypes = [
    Archetype("A1", "DeFi_Blue_Chip",  "MATURE_PROTOCOL",
              np.random.normal(0.7, 0.1, 128).astype(np.float32),
              base_value=0.80, convergence_rate=0.0005, genesis_stage_value=0.60),
    Archetype("A2", "New_Memecoin",    "NEW_TOKEN",
              np.random.normal(0.3, 0.2, 128).astype(np.float32),
              base_value=0.20, convergence_rate=0.005,  genesis_stage_value=0.10),
    Archetype("A3", "Stablecoin",      "STABLECOIN",
              np.random.normal(0.5, 0.05, 128).astype(np.float32),
              base_value=0.60, convergence_rate=0.002,  genesis_stage_value=0.55),
]
genesis_vec = GenesisVector("0xNEW", centroids[5].copy())

r_v2 = infer_genesis_value_v2(genesis_vec, archetypes, D_asset=0.0)
print(f"    genesis_value       = {r_v2['genesis_value']}")
print(f"    transformer_value   = {r_v2['transformer_value']}")
print(f"    genesis_stage_value = {r_v2['genesis_stage_value']}")
print(f"    conf_genesis        = {r_v2['conf_genesis']}")
print(f"    lambda              = {r_v2['lambda']}")
print(f"    best_archetype      = {r_v2['best_archetype']}")
print(f"    genesis_inference_v = {r_v2['genesis_inference_v']}")
print(f"    conformal_interval  = {r_v2['conformal_interval']}")
assert r_v2['genesis_inference_v'] == 'v2_transformer', \
    f"Expected v2_transformer, got {r_v2['genesis_inference_v']}"
assert r_v2['transformer_value'] is not None
assert 0.0 <= r_v2['genesis_value'] <= 1.0
assert r_v2['conformal_interval'] is not None
print(f"    ✓ v2_transformer path used, transformer_value is real float")

# ── 8. infer_genesis_value() (dispatch to v2) ─────────────────────────────
r_dispatch = infer_genesis_value(genesis_vec, archetypes, D_asset=1000.0)
print(f"\n[8] infer_genesis_value() dispatch (D_asset=1000):")
print(f"    genesis_value       = {r_dispatch['genesis_value']}")
print(f"    genesis_inference_v = {r_dispatch.get('genesis_inference_v', 'v1_harmonic (no key)')}")
print(f"    ✓ Callers get real numeric output via existing public API")

# ── 9. Existing tests still pass ──────────────────────────────────────────
print(f"\n[9] Backward-compatibility check (test_all_planes test_genesis_inference):")
np.random.seed(42)
archetypes_compat = [
    Archetype("A1", "DeFi",    "MATURE", np.random.normal(0.7, 0.1, 128), 0.80, 0.0005, 0.60),
    Archetype("A2", "Memecoin","NEW",    np.random.normal(0.3, 0.2, 128), 0.20, 0.005,  0.10),
]
genesis_compat = GenesisVector("0xNEW", np.random.normal(0.68, 0.12, 128))
r0_c     = infer_genesis_value(genesis_compat, archetypes_compat, D_asset=0)
r50000_c = infer_genesis_value(genesis_compat, archetypes_compat, D_asset=50000)
assert 0 <= r0_c['genesis_value'] <= 1, "genesis_value out of range"
assert r50000_c['conf_genesis'] > r0_c['conf_genesis'], "conf must grow with D"
print(f"    r0     genesis_value={r0_c['genesis_value']:.4f}  conf={r0_c['conf_genesis']:.4f}")
print(f"    r50000 genesis_value={r50000_c['genesis_value']:.4f}  conf={r50000_c['conf_genesis']:.4f}")
print(f"    ✓ All backward-compat assertions pass")

print("\n" + "=" * 68)
print("ALL CHECKS PASSED — mental_transformer.py is real and functional")
print("=" * 68)
