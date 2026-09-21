"""
vector_store.py
───────────────
FAISS-based vector store with MMR retrieval.
Each session gets its own index saved to disk.
"""

from __future__ import annotations
import json
import pickle
from pathlib import Path
from typing import List, Tuple

import faiss
import numpy as np

from config import INDEX_DIR, TOP_K, MMR_LAMBDA
from embedder import embed_texts, embed_query
from pdf_processor import Chunk


class VectorStore:
    """FAISS index + chunk metadata for a single PDF session."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.index_path = Path(INDEX_DIR) / f"{session_id}.faiss"
        self.meta_path  = Path(INDEX_DIR) / f"{session_id}.pkl"
        self._index: faiss.Index | None = None
        self._chunks: List[Chunk] = []

    # ── Build ─────────────────────────────────────────────────────────────────
    def build(self, chunks: List[Chunk]) -> None:
        """Embed all chunks and build the FAISS index."""
        self._chunks = chunks
        texts = [c.text for c in chunks]
        
        print(f"[VectorStore] Embedding {len(texts)} chunks...")
        embeddings = embed_texts(texts)           # (n, dim)

        dim = embeddings.shape[1]
        self._index = faiss.IndexFlatIP(dim)      # Inner Product (= cosine since normalised)
        self._index.add(embeddings)

        self._save()
        print(f"[VectorStore] Index built: {len(texts)} vectors, dim={dim}")

    # ── Retrieve ──────────────────────────────────────────────────────────────
    def retrieve(self, query: str, k: int = TOP_K) -> List[Tuple[Chunk, float]]:
        """
        MMR retrieval: balances relevance and diversity.
        Returns list of (Chunk, score) sorted by relevance.
        """
        self._ensure_loaded()
        if not self._chunks:
            return []

        query_emb = embed_query(query)                 # (1, dim)
        fetch_k = min(k * 3, len(self._chunks))        # fetch more, then diversify
        
        scores, indices = self._index.search(query_emb, fetch_k)
        scores = scores[0].tolist()
        indices = indices[0].tolist()

        candidates = [(self._chunks[i], scores[j]) 
                      for j, i in enumerate(indices) if i >= 0]

        return self._mmr(candidates, query_emb, k)

    def _mmr(
        self,
        candidates: List[Tuple[Chunk, float]],
        query_emb: np.ndarray,
        k: int,
    ) -> List[Tuple[Chunk, float]]:
        """
        Maximal Marginal Relevance:
        balance between relevance to query and diversity among results.
        λ=1 → pure relevance, λ=0 → pure diversity
        """
        if not candidates:
            return []

        lam = MMR_LAMBDA
        selected: List[Tuple[Chunk, float]] = []
        candidate_embs = embed_texts([c.text for c, _ in candidates])

        remaining = list(range(len(candidates)))

        for _ in range(min(k, len(candidates))):
            if not remaining:
                break
            if not selected:
                # First pick: most relevant
                best_idx = max(remaining, key=lambda i: candidates[i][1])
            else:
                sel_embs = embed_texts([c.text for c, _ in selected])
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

        return selected

    # ── Persistence ───────────────────────────────────────────────────────────
    def _save(self) -> None:
        faiss.write_index(self._index, str(self.index_path))
        with open(self.meta_path, "wb") as f:
            pickle.dump(self._chunks, f)

    def _ensure_loaded(self) -> None:
        if self._index is not None:
            return
        if self.index_path.exists() and self.meta_path.exists():
            self._index = faiss.read_index(str(self.index_path))
            with open(self.meta_path, "rb") as f:
                self._chunks = pickle.load(f)
        else:
            raise ValueError(f"Session {self.session_id} not found. Upload a PDF first.")

    def exists(self) -> bool:
        return self.index_path.exists() and self.meta_path.exists()

    def chunk_count(self) -> int:
        self._ensure_loaded()
        return len(self._chunks)
