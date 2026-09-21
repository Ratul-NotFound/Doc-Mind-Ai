"""
embedder.py
───────────
Local sentence-transformer embeddings.
Model is cached in memory after first load — zero API cost.
"""

from __future__ import annotations
from functools import lru_cache
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

from config import EMBEDDING_MODEL


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    """Load the embedding model once and keep it in memory."""
    print(f"[Embedder] Loading model: {EMBEDDING_MODEL} (first time only)...")
    model = SentenceTransformer(EMBEDDING_MODEL)
    print(f"[Embedder] Model ready.")
    return model


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
