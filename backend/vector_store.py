"""
vector_store.py
───────────────
FAISS-based vector store with MMR retrieval.
Each session gets its own index saved to disk.
"""

from __future__ import annotations
import os
import sys
import json
import pickle
from pathlib import Path
from typing import List, Tuple

# Ensure backend directory is in sys.path
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import faiss
import numpy as np

try:
    from config import INDEX_DIR, TOP_K, MMR_LAMBDA
    from embedder import embed_texts, embed_query
    from pdf_processor import Chunk
except ImportError:
    from backend.config import INDEX_DIR, TOP_K, MMR_LAMBDA
    from backend.embedder import embed_texts, embed_query
    from backend.pdf_processor import Chunk


class VectorStore:
    """FAISS index + chunk metadata for a single PDF session."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.index_path = Path(INDEX_DIR) / f"{session_id}.faiss"
        self.meta_path  = Path(INDEX_DIR) / f"{session_id}.pkl"
        self.json_meta_path = Path(INDEX_DIR) / f"{session_id}_meta.json"
        self._index: faiss.Index | None = None
        self._chunks: List[Chunk] = []

    # ── Build ─────────────────────────────────────────────────────────────────
    def build(self, chunks: List[Chunk], session_meta: dict | None = None) -> None:
        """Embed all chunks, build FAISS index, and save metadata."""
        self._chunks = chunks
        texts = [c.text for c in chunks]
        
        print(f"[VectorStore] Embedding {len(texts)} chunks...")
        embeddings = embed_texts(texts)           # (n, dim)

        dim = embeddings.shape[1]
        self._index = faiss.IndexFlatIP(dim)      # Inner Product (= cosine since normalised)
        self._index.add(embeddings)

        self._save(session_meta)
        print(f"[VectorStore] Index built: {len(texts)} vectors, dim={dim}")

    # ── Retrieve ──────────────────────────────────────────────────────────────
    def retrieve(self, query: str, k: int = TOP_K) -> List[Tuple[Chunk, float]]:
        """
        MMR retrieval: balances relevance and diversity.
        Returns list of (Chunk, score) sorted by relevance.
        """
        if not query or not query.strip():
            return []

        self._ensure_loaded()
        if not self._chunks or self._index is None or self._index.ntotal == 0:
            return []

        query_emb = embed_query(query)                 # (1, dim)
        fetch_k = min(max(k * 3, 1), len(self._chunks)) # fetch more, then diversify
        
        scores, indices = self._index.search(query_emb, fetch_k)
        scores = scores[0].tolist()
        indices = indices[0].tolist()

        candidates = [
            (self._chunks[i], scores[j], i) 
            for j, i in enumerate(indices) if 0 <= i < len(self._chunks)
        ]

        return self._mmr(candidates, query_emb, k)

    def _mmr(
        self,
        candidates: List[Tuple[Chunk, float, int]],
        query_emb: np.ndarray,
        k: int,
    ) -> List[Tuple[Chunk, float]]:
        """
        Maximal Marginal Relevance:
        balance between relevance to query and diversity among results.
        """
        if not candidates:
            return []

        # If we have only 1 candidate, return it directly
        if len(candidates) == 1:
            return [(candidates[0][0], candidates[0][1])]

        lam = MMR_LAMBDA
        selected: List[Tuple[Chunk, float, int]] = []

        # Reconstruct vectors directly from FAISS index to avoid re-embedding
        candidate_embs = np.array([self._index.reconstruct(c[2]) for c in candidates])

        remaining = list(range(len(candidates)))

        for _ in range(min(k, len(candidates))):
            if not remaining:
                break
            if not selected:
                # First pick: highest relevance
                best_idx = max(remaining, key=lambda i: candidates[i][1])
            else:
                sel_indices = [s[2] for s in selected]
                sel_embs = np.array([self._index.reconstruct(idx) for idx in sel_indices])
                best_score = -1e9
                best_idx = remaining[0]
                for i in remaining:
                    relevance = float(np.dot(candidate_embs[i], query_emb[0]))
                    sim_to_sel = float(np.max(
                        [np.dot(candidate_embs[i], s) for s in sel_embs]
                    ))
                    score = lam * relevance - (1 - lam) * sim_to_sel
                    if score > best_score:
                        best_score = score
                        best_idx = i
            selected.append(candidates[best_idx])
            remaining.remove(best_idx)

        return [(chunk, score) for chunk, score, _ in selected]

    # ── Persistence ───────────────────────────────────────────────────────────
    def _save(self, session_meta: dict | None = None) -> None:
        faiss.write_index(self._index, str(self.index_path))
        with open(self.meta_path, "wb") as f:
            pickle.dump(self._chunks, f)
        if session_meta:
            with open(self.json_meta_path, "w", encoding="utf-8") as f:
                json.dump(session_meta, f, indent=2)

    def _ensure_loaded(self) -> None:
        if self._index is not None:
            return
        if self.index_path.exists() and self.meta_path.exists():
            self._index = faiss.read_index(str(self.index_path))
            with open(self.meta_path, "rb") as f:
                self._chunks = pickle.load(f)
        else:
            raise ValueError(f"Session {self.session_id} not found. Upload a PDF first.")

    def get_metadata(self) -> dict:
        """Return saved session metadata JSON if exists."""
        if self.json_meta_path.exists():
            try:
                with open(self.json_meta_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def exists(self) -> bool:
        return self.index_path.exists() and self.meta_path.exists()

    def chunk_count(self) -> int:
        self._ensure_loaded()
        return len(self._chunks)
