"""
rag_chain.py
────────────
Retrieval → Prompt construction → Groq LLM → Streamed response.
Token-efficient: only ~800–1200 tokens used per query.
"""

from __future__ import annotations
import asyncio
from typing import AsyncGenerator, List, Tuple

from groq import Groq

from config import GROQ_API_KEY, GROQ_MODEL, SYSTEM_PROMPT, TOP_K
from pdf_processor import Chunk
from vector_store import VectorStore


def _build_context(chunks_with_scores: List[Tuple[Chunk, float]]) -> str:
    """Build a formatted context string from retrieved chunks."""
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
    """Combines retrieval + Groq LLM into a single QA chain."""

    def __init__(self, session_id: str):
        self.store = VectorStore(session_id)
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

    async def stream_answer(
        self, question: str
    ) -> AsyncGenerator[str, None]:
        """
        Stream the LLM answer token by token.
        Yields string chunks for SSE.

        The Groq SDK streaming is synchronous, so we run it in a
        thread-pool executor and push tokens into an asyncio.Queue to
        avoid blocking FastAPI's async event loop.
        """
        context, _ = self.get_context(question)
        user_message = _build_user_message(question, context)

        approx_tokens = (len(SYSTEM_PROMPT) + len(user_message)) // 4
        print(f"[RAG] Approx input tokens: {approx_tokens} | Model: {GROQ_MODEL}")

        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()
        _DONE = object()  # sentinel value

        def _run_stream():
            """Runs in a background thread — consumes the sync Groq stream."""
            try:
                stream = self.client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": user_message},
                    ],
                    temperature=0.1,
                    max_tokens=1024,
                    stream=True,
                )
                for chunk in stream:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        loop.call_soon_threadsafe(queue.put_nowait, delta)
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, _DONE)

        # Start the blocking Groq stream in a worker thread
        loop.run_in_executor(None, _run_stream)

        # Yield tokens as they arrive from the queue
        while True:
            item = await queue.get()
            if item is _DONE:
                break
            if isinstance(item, Exception):
                raise item
            yield item

    def answer(self, question: str) -> Tuple[str, List[dict]]:
        """Synchronous answer (non-streaming). Returns (answer, sources)."""
        context, sources = self.get_context(question)
        user_message = _build_user_message(question, context)

        response = self.client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.1,
            max_tokens=1024,
        )

        answer_text = response.choices[0].message.content
        usage = response.usage
        print(
            f"[RAG] Tokens used — prompt: {usage.prompt_tokens}, "
            f"completion: {usage.completion_tokens}, "
            f"total: {usage.total_tokens}"
        )

        return answer_text, sources
