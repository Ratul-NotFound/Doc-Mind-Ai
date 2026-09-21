import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM ──────────────────────────────────────────────────────────────────────
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")

# ── Embedding Model (runs locally, 100% free) ────────────────────────────────
EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"   # 22M params, ~80MB download once

# ── Chunking ─────────────────────────────────────────────────────────────────
CHUNK_SIZE: int = 800          # characters per chunk
CHUNK_OVERLAP: int = 150       # overlap to preserve context at boundaries

# ── Retrieval ────────────────────────────────────────────────────────────────
TOP_K: int = 4                 # number of chunks to retrieve per query
MMR_LAMBDA: float = 0.6        # diversity vs relevance (0 = diverse, 1 = relevant)

# ── File Storage ──────────────────────────────────────────────────────────────
UPLOAD_DIR: str = "uploads"
INDEX_DIR: str  = "indexes"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(INDEX_DIR, exist_ok=True)

# ── RAG Prompt Template ───────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a precise document assistant. Your ONLY job is to answer questions based on the provided document excerpts.

Rules:
- Answer ONLY from the context provided. Do not use outside knowledge.
- If the answer is not in the context, say: "I couldn't find this information in the uploaded document."
- Be concise and direct. Use bullet points for lists.
- When relevant, mention the page number (e.g., "According to page 3...").
- Never fabricate or guess information."""
