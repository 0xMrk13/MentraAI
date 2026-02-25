from __future__ import annotations

import re

def pdf_to_text(pdf_bytes: bytes) -> str:
    """
    Extract selectable text from PDF (no OCR).
    Requires: pip install pymupdf
    """
    import fitz  

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    chunks: list[str] = []
    for page in doc:
        chunks.append(page.get_text("text"))
    doc.close()

    text = "\n".join(chunks).strip()
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_CONTROL_RE = re.compile(r"(<\|.*?\|>)|(\b(role|system|developer|assistant|user)\s*:)", re.I | re.S)

def sanitize_notes_text(text: str, max_chars: int = 20000) -> str:
    """
    Generic safety: remove control-token patterns that can hijack some Llama-style models.
    """
    t = (text or "").strip()
    t = _CONTROL_RE.sub("", t)
    return t[:max_chars].strip()
