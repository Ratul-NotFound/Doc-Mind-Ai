"""
rag_chain.py
────────────
Retrieval → Prompt construction → Groq LLM → Response.
Token-efficient: only ~800–1200 tokens used per query.
Supports automatic multi-model fallback and multi-turn context.
"""

from __future__ import annotations
import asyncio
from typing import AsyncGenerator, List, Tuple, Optional

from groq import Groq

from config import GROQ_API_KEY, GROQ_MODEL, GROQ_FALLBACK_MODELS, SYSTEM_PROMPT, TOP_K
from pdf_processor import Chunk
from vector_store import VectorStore


def _build_context(chunks_with_scores: List[Tuple[Chunk, float]]) -> str:
    """Build a formatted context string from retrieved chunks."""
    if not chunks_with_scores:
        return "No relevant text chunks found."
    parts = []
    for chunk, score in chunks_with_scores:
        parts.append(
            f"[Source: {chunk.source}, Page {chunk.page}]\n{chunk.text}"
        )
    return "\n\n---\n\n".join(parts)


def _build_user_message(question: str, context: str) -> str:
    return f"""Use the following document excerpts to answer the question.

=== DOCUMENT EXCERPTS ===
{context}
=========================

Question: {question}

Answer:"""


# ─────────────────────────────────────────────────────────────────────────────
class RAGChain:
    """Combines retrieval + Groq LLM with automatic model failover."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.store = VectorStore(session_id)
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not configured in backend/.env")
        self.client = Groq(api_key=GROQ_API_KEY)

    def get_context(self, question: str) -> Tuple[str, List[dict]]:
        """
        Retrieve relevant chunks and return:
        - context string for the prompt
        - list of source dicts for the UI
        """
        chunks_with_scores = self.store.retrieve(question, k=TOP_K)
        context = _build_context(chunks_with_scores)
        sources = [
            {
                "page": c.page,
                "source": c.source,
                "text": c.text[:300] + ("..." if len(c.text) > 300 else ""),
                "score": round(float(score), 3),
            }
            for c, score in chunks_with_scores
        ]
        return context, sources

    def _prepare_messages(
        self, question: str, context: str, history: Optional[List[dict]] = None
    ) -> List[dict]:
        """Construct prompt messages including system prompt, short history, and current question with context."""
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Append last 2-4 turns of history if provided
        if history:
            # history is list of {"role": "user"|"assistant", "content": str}
            for turn in history[-4:]:
                if turn.get("role") in ("user", "assistant") and turn.get("content"):
                    messages.append({"role": turn["role"], "content": turn["content"]})

        user_message = _build_user_message(question, context)
        messages.append({"role": "user", "content": user_message})
        return messages

    async def stream_answer(
        self, question: str, history: Optional[List[dict]] = None
    ) -> AsyncGenerator[str, None]:
        """Stream the LLM answer token by token with automatic model failover."""
        context, _ = self.get_context(question)
        messages = self._prepare_messages(question, context, history)

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        _DONE = object()

        # Deduplicate fallback models
        models_to_try = []
        for m in GROQ_FALLBACK_MODELS:
            if m not in models_to_try:
                models_to_try.append(m)

        def _run_stream():
            last_err = None
            for model_name in models_to_try:
                try:
                    stream = self.client.chat.completions.create(
                        model=model_name,
                        messages=messages,
                        temperature=0.1,
                        max_tokens=1024,
                        stream=True,
                    )
                    for chunk in stream:
                        delta = chunk.choices[0].delta.content
                        if delta:
                            loop.call_soon_threadsafe(queue.put_nowait, delta)
                    return  # Success
                except Exception as exc:
                    print(f"[RAG Stream] Model {model_name} failed: {exc}. Trying next fallback...")
                    last_err = exc
                    continue
            
            # If all models failed
            if last_err:
                loop.call_soon_threadsafe(queue.put_nowait, last_err)
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)

        loop.run_in_executor(None, _run_stream)

        while True:
            item = await queue.get()
            if item is _DONE:
                break
            if isinstance(item, Exception):
                raise item
            yield item

    def answer(
        self, question: str, history: Optional[List[dict]] = None
    ) -> Tuple[str, List[dict]]:
        """Synchronous answer with automatic model fallback."""
        context, sources = self.get_context(question)
        messages = self._prepare_messages(question, context, history)

        models_to_try = []
        for m in GROQ_FALLBACK_MODELS:
            if m not in models_to_try:
                models_to_try.append(m)

        last_error = None
        for model_name in models_to_try:
            try:
                response = self.client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=1024,
                )
                answer_text = response.choices[0].message.content or ""
                return answer_text, sources
            except Exception as e:
                print(f"[RAG Sync] Model {model_name} failed: {e}. Trying fallback...")
                last_error = e
                continue

        # If all fallback models failed
        raise RuntimeError(f"All Groq models failed. Last error: {last_error}")
