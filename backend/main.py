"""
main.py
───────
FastAPI application.

Endpoints:
  POST /upload          — Upload a PDF, get back a session_id
  POST /ask             — Ask a question (streaming SSE)
  POST /ask/sync        — Ask a question (non-streaming JSON)
  GET  /session/{id}    — Get session info (chunk count, filename)
  DELETE /session/{id}  — Delete a session and its index
"""

from __future__ import annotations
import os
import sys
import uuid
import json
from pathlib import Path

# Ensure backend directory is in sys.path regardless of execution root
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    from config import UPLOAD_DIR, INDEX_DIR
    from pdf_processor import extract_chunks, get_pdf_info
    from vector_store import VectorStore
    from rag_chain import RAGChain
except ImportError:
    from backend.config import UPLOAD_DIR, INDEX_DIR
    from backend.pdf_processor import extract_chunks, get_pdf_info
    from backend.vector_store import VectorStore
    from backend.rag_chain import RAGChain

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="PDF RAG Assistant API",
    description="Upload any PDF and ask questions — powered by local embeddings + Groq LLM",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # for local dev; tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── In-memory session registry ────────────────────────────────────────────────
# Maps session_id → {"filename": str, "pages": int, "chunks": int}
sessions: dict[str, dict] = {}


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


class AskRequest(BaseModel):
    session_id: str
    question: str
    history: list[dict] | None = None


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """
    1. Save the uploaded PDF to disk
    2. Extract and chunk text
    3. Build FAISS index & save metadata
    4. Return a session_id to use in /ask requests
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    session_id = str(uuid.uuid4())
    save_path = Path(UPLOAD_DIR) / f"{session_id}.pdf"

    # Save file
    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    try:
        # Extract PDF info
        info = get_pdf_info(save_path)

        # Extract + chunk
        chunks = extract_chunks(save_path)
        if not chunks:
            raise HTTPException(
                status_code=422,
                detail="No readable text found in PDF. The document may be a scanned image without OCR.",
            )

        session_meta = {
            "session_id": session_id,
            "filename": file.filename,
            "title": info["title"],
            "author": info["author"],
            "pages": info["pages"],
            "chunks": len(chunks),
        }

        # Build vector index & save metadata
        store = VectorStore(session_id)
        store.build(chunks, session_meta=session_meta)

        # Register in-memory session
        sessions[session_id] = session_meta

        return {
            **session_meta,
            "message": f"PDF processed successfully. {len(chunks)} chunks indexed.",
        }

    except ValueError as ve:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        save_path.unlink(missing_ok=True)
        raise
    except Exception as e:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to process PDF: {str(e)}")


@app.post("/ask")
async def ask_streaming(req: AskRequest):
    """Stream the answer as Server-Sent Events (SSE)."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        rag = RAGChain(req.session_id)
    except ValueError as ve:
        raise HTTPException(status_code=500, detail=str(ve))

    if not rag.store.exists():
        raise HTTPException(status_code=404, detail="Session not found. Please upload a PDF first.")

    context, sources = rag.get_context(req.question)

    async def event_stream():
        # First event: send sources metadata
        sources_payload = json.dumps({"type": "sources", "data": sources})
        yield f"data: {sources_payload}\n\n"

        # Stream LLM tokens
        try:
            async for token in rag.stream_answer(req.question, history=req.history):
                token_payload = json.dumps({"type": "token", "data": token})
                yield f"data: {token_payload}\n\n"
        except Exception as err:
            err_payload = json.dumps({"type": "error", "data": str(err)})
            yield f"data: {err_payload}\n\n"

        # Final event: signal completion
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/ask/sync")
async def ask_sync(req: AskRequest):
    """Non-streaming ask — returns full answer + sources as JSON."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        rag = RAGChain(req.session_id)
    except ValueError as ve:
        raise HTTPException(status_code=500, detail=str(ve))

    if not rag.store.exists():
        raise HTTPException(status_code=404, detail="Session not found.")

    try:
        answer, sources = rag.answer(req.question, history=req.history)
        return {"answer": answer, "sources": sources}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/session/{session_id}")
def get_session(session_id: str):
    """Return metadata for a session, restoring from disk if needed."""
    store = VectorStore(session_id)
    if not store.exists():
        raise HTTPException(status_code=404, detail="Session not found.")

    meta = sessions.get(session_id)
    if not meta:
        meta = store.get_metadata()
        if meta:
            sessions[session_id] = meta

    return {
        "session_id": session_id,
        "chunks": store.chunk_count(),
        **(meta or {}),
    }


@app.delete("/session/{session_id}")
def delete_session(session_id: str):
    """Delete the index and uploaded file for a session."""
    Path(INDEX_DIR, f"{session_id}.faiss").unlink(missing_ok=True)
    Path(INDEX_DIR, f"{session_id}.pkl").unlink(missing_ok=True)
    Path(INDEX_DIR, f"{session_id}_meta.json").unlink(missing_ok=True)
    Path(UPLOAD_DIR, f"{session_id}.pdf").unlink(missing_ok=True)
    sessions.pop(session_id, None)
    return {"message": "Session deleted."}


# ── Serve frontend static files ────────────────────────────────────────────────
# Mount AFTER all API routes so /upload, /ask, /session routes take priority.
# Visit http://localhost:8000 in your browser — no need to open index.html manually.
_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if _FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
