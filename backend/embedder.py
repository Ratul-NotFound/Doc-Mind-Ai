"""
embedder.py
───────────
Local sentence-transformer embeddings.
Model is cached in memory after first load — zero API cost.
"""

from __future__ import annotations
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import List

# Ensure backend directory is in sys.path
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

# Limit PyTorch CPU threads to prevent memory/CPU spikes on 512MB instances
torch.set_num_threads(2)

try:
    from config import EMBEDDING_MODEL
except ImportError:
    from backend.config import EMBEDDING_MODEL


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    """Load the embedding model once and keep it in memory on CPU."""
    print(f"[Embedder] Loading model: {EMBEDDING_MODEL} (CPU mode)...")
    model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    print(f"[Embedder] Model ready.")
    return model


def warmup_embedder() -> None:
    """Warm up the embedding model during app startup."""
    try:
        _ = _get_model()
    except Exception as e:
        print(f"[Embedder] Warmup failed (will retry on first query): {e}")


def embed_texts(texts: List[str]) -> np.ndarray:
    """
    Encode a list of texts into L2-normalised embedding vectors.
    Returns shape (n, dim) float32 array.
    """
    model = _get_model()
    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=len(texts) > 50,
        normalize_embeddings=True,   # unit vectors → cosine = dot product
        convert_to_numpy=True,
    )
    return embeddings.astype("float32")


def embed_query(query: str) -> np.ndarray:
    """Encode a single query string. Returns shape (1, dim)."""
    return embed_texts([query])
