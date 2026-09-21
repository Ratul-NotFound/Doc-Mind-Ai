# DocMind — AI PDF Assistant 🧠

> Upload any PDF. Ask precise questions. Get grounded answers with page citations.

A production-quality **Retrieval-Augmented Generation (RAG)** system built for accuracy and token efficiency. Uses local embeddings so the entire PDF never gets sent to an API — only the most relevant 2–4 passages (~800 tokens) are sent per query.

---

## ✨ Features

- **Drag & Drop PDF Upload** — Any PDF, any size
- **Local Embeddings** — `sentence-transformers` runs on your CPU (zero API cost for embeddings)
- **FAISS Vector Search** — MMR-based retrieval for diverse, relevant results
- **Streaming Answers** — Real-time typewriter effect via Server-Sent Events
- **Source Citations** — Shows exact page numbers and text chunks used
- **Token Efficient** — Only ~800–1200 tokens per query (not the full PDF!)
- **Grounded Answers** — LLM refuses to hallucinate if info isn't in the document
- **Light / Dark Mode** — Professional AI-tool aesthetic
- **Free to Run** — Groq API has 14,400 free requests/day

---

## 🏗️ Architecture

```
PDF Upload
    │
    ▼
PyMuPDF Text Extraction (page-by-page)
    │
    ▼
Recursive Chunking (800 chars, 150 overlap)
    │
    ▼
sentence-transformers Embeddings (LOCAL, free)
    │
    ▼
FAISS Index (saved per session)

           USER QUESTION
               │
               ▼
         Query Embedding (local)
               │
               ▼
     FAISS Cosine Search → Top 4 Chunks (MMR)
               │
               ▼
     Groq API (llama-3.1-8b-instant)
     [~800 tokens input — not the full PDF]
               │
               ▼
     Streamed Answer + Source Citations
```

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/Ratul-NotFound/Doc-Mind-Ai.git
cd Doc-Mind-Ai

pip install -r requirements.txt
```

> **Note:** First run downloads the `all-MiniLM-L6-v2` embedding model (~80MB). It's cached locally after that.

### 2. Set up your Groq API Key

```bash
cp .env.example .env
# Edit .env and add your key from https://console.groq.com/
```

### 3. Start the Backend

```bash
cd backend
python main.py
# API runs at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### 4. Open the Frontend

Open `frontend/index.html` in your browser, or serve it:

```bash
# Simple HTTP server (Python)
cd frontend
python -m http.server 3000
# Visit http://localhost:3000
```

---

## 📁 Project Structure

```
pdf-rag-assistant/
├── backend/
│   ├── main.py          # FastAPI app + routes
│   ├── config.py        # All settings (chunk size, model, etc.)
│   ├── pdf_processor.py # PyMuPDF extraction + recursive chunking
│   ├── embedder.py      # Local sentence-transformer embeddings
│   ├── vector_store.py  # FAISS index + MMR retrieval
│   └── rag_chain.py     # Retrieval + Groq LLM pipeline
├── frontend/
│   ├── index.html       # Single-page app
│   ├── style.css        # Design system (light/dark)
│   └── app.js           # Chat logic + streaming
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🔧 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/upload` | Upload PDF → returns `session_id` |
| `POST` | `/ask` | Stream answer (SSE) |
| `POST` | `/ask/sync` | Non-streaming answer (JSON) |
| `GET`  | `/session/{id}` | Session metadata |
| `DELETE` | `/session/{id}` | Delete session + index |

Full interactive docs at `http://localhost:8000/docs`

---

## 🧠 Key Design Decisions

### Why `sentence-transformers` for embeddings?
- Runs 100% locally — no API cost, no data leaving your machine for embeddings
- `all-MiniLM-L6-v2` achieves 90% of large model quality at 1% of the size
- ~80MB download once, then cached

### Why only 4 chunks per query?
- Reduces LLM token usage by 95% vs. sending the full document
- FAISS + MMR ensures the 4 chunks are both relevant AND diverse
- Keeps answers grounded and concise

### Why Groq?
- 14,400 free requests/day
- Sub-second inference (fastest available)
- `llama-3.1-8b-instant` is excellent for factual Q&A

---

## 🌐 Deployment (Hugging Face Spaces)

```bash
# Requirements for Spaces (add to requirements.txt):
gradio  # OR keep FastAPI + use Docker

# Dockerfile for Railway / Render:
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ ./backend/
CMD ["python", "backend/main.py"]
```

---

## 📊 Token Usage Comparison

| Approach | Tokens per query | Cost |
|----------|-----------------|------|
| Full PDF to LLM | 10,000–100,000 | $$$$ |
| **This RAG system** | **~800–1,200** | **Free** |

---

## 🤝 Built With

- [FastAPI](https://fastapi.tiangolo.com/) — Modern Python API framework
- [sentence-transformers](https://sbert.net/) — Local embedding model
- [FAISS](https://github.com/facebookresearch/faiss) — Facebook AI vector search
- [pypdf](https://pypdf.readthedocs.io/) + [pdfplumber](https://github.com/jsvine/pdfplumber) — Pure Python PDF extraction
- [Groq](https://groq.com/) — Ultra-fast LLM inference

---

*Built as a portfolio project demonstrating production RAG architecture.*
