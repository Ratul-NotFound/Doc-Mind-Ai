"""
pdf_processor.py
────────────────
Extracts text from PDFs page-by-page using pypdf + pdfplumber (pure Python,
no compilation required), then splits into overlapping chunks while preserving
page-number metadata.
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

import pdfplumber
from pypdf import PdfReader

from config import CHUNK_SIZE, CHUNK_OVERLAP


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Chunk:
    """A text chunk with its origin metadata."""
    text: str
    page: int          # 1-indexed
    chunk_index: int
    source: str = ""   # original filename


# ─────────────────────────────────────────────────────────────────────────────
def _clean_text(text: str) -> str:
    """Remove excessive whitespace, fix ligatures and common PDF artifacts."""
    if not text:
        return ""
    # Normalize common Unicode ligatures
    ligatures = {
        "\ufb01": "fi",
        "\ufb02": "fl",
        "\ufb00": "ff",
        "\ufb03": "ffi",
        "\ufb04": "ffl",
        "\u00ad": "",   # soft hyphen
    }
    for lig, repl in ligatures.items():
        text = text.replace(lig, repl)

    text = re.sub(r"[ \t]+", " ", text)              # collapse horizontal whitespace
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)      # fix hyphenated line breaks
    text = re.sub(r"\r\n|\r", "\n", text)             # normalize newlines
    text = re.sub(r"\n{3,}", "\n\n", text)            # max 2 consecutive newlines
    return text.strip()


def _split_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Recursive character-based splitter.
    Priority: paragraph → sentence → word boundaries.
    """
    if not text:
        return []

    separators = ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""]

    if len(text) <= size:
        return [text] if text.strip() else []

    for sep in separators:
        if sep and sep not in text:
            continue
        parts = text.split(sep) if sep else list(text)
        chunks: List[str] = []
        current = ""

        for part in parts:
            candidate = (current + sep + part).strip() if current else part
            if len(candidate) <= size:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                if len(part) > size:
                    chunks.extend(_split_text(part, size, overlap))
                    current = ""
                else:
                    current = part
        if current:
            chunks.append(current)

        # Add overlap
        if overlap > 0 and len(chunks) > 1:
            overlapped: List[str] = [chunks[0]]
            for i in range(1, len(chunks)):
                tail = chunks[i - 1][-overlap:]
                overlapped.append((tail + " " + chunks[i]).strip())
            return overlapped
        return chunks

    # Fallback: hard split
    step = max(1, size - overlap)
    return [text[i : i + size] for i in range(0, len(text), step)]


# ─────────────────────────────────────────────────────────────────────────────
def _check_encrypted(pdf_path: Path) -> None:
    """Check if the PDF is encrypted/password-protected."""
    try:
        reader = PdfReader(str(pdf_path))
        if reader.is_encrypted:
            try:
                # Try decrypting with empty password
                reader.decrypt("")
            except Exception:
                raise ValueError("This PDF is password-protected. Please upload an unprotected PDF.")
    except ValueError:
        raise
    except Exception:
        pass


def _extract_with_pdfplumber(pdf_path: Path) -> List[tuple[int, str]]:
    """Primary extractor using pdfplumber with per-page error isolation."""
    pages = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages):
            try:
                text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            except Exception as e:
                print(f"[PDF] Page {i+1} pdfplumber error ({e}), trying fallback")
                text = ""
            pages.append((i + 1, text))
    return pages


def _extract_with_pypdf(pdf_path: Path) -> List[tuple[int, str]]:
    """Fallback extractor using pypdf with per-page error isolation."""
    pages = []
    reader = PdfReader(str(pdf_path))
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception as e:
            print(f"[PDF] Page {i+1} pypdf error: {e}")
            text = ""
        pages.append((i + 1, text))
    return pages


# ─────────────────────────────────────────────────────────────────────────────
def extract_chunks(pdf_path: str | Path) -> List[Chunk]:
    """
    Main entry point: opens a PDF, extracts text per page,
    cleans it, splits into chunks, returns Chunk objects with page metadata.
    """
    pdf_path = Path(pdf_path)
    _check_encrypted(pdf_path)

    all_chunks: List[Chunk] = []
    chunk_index = 0

    # Try pdfplumber first, fall back to pypdf if plumber fails completely
    pages: List[tuple[int, str]] = []
    try:
        pages = _extract_with_pdfplumber(pdf_path)
    except Exception as e:
        print(f"[PDF] pdfplumber failed ({e}), falling back to pypdf")
        pages = _extract_with_pypdf(pdf_path)

    # If all pages extracted via plumber were empty, attempt pypdf as secondary
    total_extracted_len = sum(len(text.strip()) for _, text in pages)
    if total_extracted_len == 0:
        try:
            pypdf_pages = _extract_with_pypdf(pdf_path)
            if sum(len(t.strip()) for _, t in pypdf_pages) > 0:
                pages = pypdf_pages
        except Exception:
            pass

    for page_num, raw_text in pages:
        clean = _clean_text(raw_text)
        if not clean or len(clean) < 15:
            continue

        page_chunks = _split_text(clean)
        for text in page_chunks:
            if len(text.strip()) < 20:   # skip tiny fragments
                continue
            all_chunks.append(Chunk(
                text=text.strip(),
                page=page_num,
                chunk_index=chunk_index,
                source=pdf_path.name,
            ))
            chunk_index += 1

    return all_chunks


# ─────────────────────────────────────────────────────────────────────────────
def get_pdf_info(pdf_path: str | Path) -> dict:
    """Return basic metadata about the PDF."""
    pdf_path = Path(pdf_path)
    try:
        reader = PdfReader(str(pdf_path))
        meta = reader.metadata or {}
        title = meta.get("/Title", "") or pdf_path.stem
        author = meta.get("/Author", "Unknown") or "Unknown"
        pages = len(reader.pages)
    except Exception:
        title, author, pages = pdf_path.stem, "Unknown", 0

    return {
        "title": str(title),
        "author": str(author),
        "pages": pages,
        "filename": pdf_path.name,
    }
