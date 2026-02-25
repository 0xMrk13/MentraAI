# app/web/routes/notes.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from app.web.core.deps import llm, store, user_from_session
from app.services.study_planner import generate_plan_from_notes

router = APIRouter(prefix="/api/notes", tags=["notes"])


def _clamp_days_5_10(v: Any, default: int = 7) -> int:
    try:
        d = int(v)
    except Exception:
        d = default
    if d < 5:
        d = 5
    if d > 10:
        d = 10
    return d


def _get_api_key(request: Request) -> str:
    api_key = ""
    u = user_from_session(request)
    if u and u.get("id"):
        try:
            api_key = store.get_key(int(u["id"])) or ""
        except Exception:
            api_key = ""
    return api_key


def _pdf_to_text(pdf_bytes: bytes) -> str:
    """
    Extract selectable text from PDF (no OCR).
    Requires: pip install PyMuPDF
    """
    try:
        import fitz  # PyMuPDF
    except Exception:
        raise RuntimeError("PyMuPDF not installed. Run: pip install PyMuPDF")

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    chunks: list[str] = []
    for page in doc:
        chunks.append(page.get_text("text"))
    doc.close()

    return "\n".join(chunks).strip()


@router.post("/plan_text")
async def plan_text(
    request: Request,
    content: str = Form(...),
    days: int = Form(7),
    title: str = Form("Pasted notes"),
):
    text = (content or "").strip()
    if not text:
        return JSONResponse({"error": "Empty notes."}, status_code=400)

    d = _clamp_days_5_10(days, default=7)
    api_key = _get_api_key(request)

    try:
        plan = await generate_plan_from_notes(
            llm=llm,
            api_key=api_key,
            notes_text=text,
            days=d,
            title=title,
            timeout_sec=35,
        )
    except Exception as e:
        return JSONResponse({"error": f"Plan error: {e}"}, status_code=500)

    return JSONResponse({"ok": True, "days": d, "plan": plan})


@router.post("/plan_pdf")
async def plan_pdf(
    request: Request,
    file: UploadFile = File(...),
    days: int = Form(7),
    title: str = Form("Uploaded PDF"),
):
    fname = (file.filename or "").strip()
    if not fname.lower().endswith(".pdf"):
        return JSONResponse({"error": "Only PDF files are allowed."}, status_code=400)

    pdf_bytes = await file.read()
    if len(pdf_bytes) > 8_000_000:
        return JSONResponse({"error": "PDF too large (max 8MB)."}, status_code=400)

    try:
        text = _pdf_to_text(pdf_bytes)
    except Exception as e:
        return JSONResponse({"error": f"Could not parse PDF: {e}"}, status_code=400)

    if len(text) < 120:
        return JSONResponse(
            {"error": "PDF has too little selectable text (maybe scanned images)."},
            status_code=400,
        )

    d = _clamp_days_5_10(days, default=7)
    api_key = _get_api_key(request)

    try:
        plan = await generate_plan_from_notes(
            llm=llm,
            api_key=api_key,
            notes_text=text,
            days=d,
            title=title or fname or "Uploaded PDF",
            timeout_sec=35,
        )
    except Exception as e:
        return JSONResponse({"error": f"Plan error: {e}"}, status_code=500)

    return JSONResponse(
        {"ok": True, "days": d, "filename": fname, "chars": len(text), "plan": plan}
    )
