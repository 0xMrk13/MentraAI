from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Body, File, Form, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from slowapi import Limiter

from app.web.core.ratelimit import limiter
from app.prompts.mentra_scan import MENTRASCAN_SYSTEM, build_mentrascan_prompt
from app.web.core.deps import llm, sid

DB_PATH = os.getenv("DB_PATH", "./data/studybot.sqlite3")
LLM_PROVIDER = (os.getenv("LLM_PROVIDER", "") or "").strip().lower()
API_KEY = os.getenv("GROQ_API_KEY", "") if LLM_PROVIDER == "groq" else os.getenv("BOT_API_KEY", "")

DEFAULT_DAYS = 7

router = APIRouter(prefix="/api/mentrascan", tags=["mentrascan"])

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def _db_connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _ensure_checks_table() -> None:
    with _db_connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS mentrascan_checks (
              owner_key TEXT NOT NULL,
              plan_id   TEXT NOT NULL,
              day       INTEGER NOT NULL,
              idx       INTEGER NOT NULL,
              checked   INTEGER NOT NULL DEFAULT 0,
              updated_at TEXT NOT NULL,
              PRIMARY KEY (owner_key, plan_id, day, idx)
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_mscan_checks_plan ON mentrascan_checks(owner_key, plan_id)")
        con.commit()


def _owner_key(request: Request) -> str:
    u = request.session.get("discord_user") or {}
    uid = u.get("id")
    if uid:
        return f"u:{uid}"
    return f"s:{sid(request)}"


def _checks_to_nested(rows) -> Dict[str, Dict[str, bool]]:
    out: Dict[str, Dict[str, bool]] = {}
    for r in rows:
        day = str(int(r["day"]))
        idx = str(int(r["idx"]))
        out.setdefault(day, {})[idx] = bool(int(r["checked"]))
    return out


def _first_balanced_object(s: str) -> Optional[str]:
    start = s.find("{")
    if start < 0:
        return None

    depth = 0
    in_str = False
    esc = False

    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start : i + 1]
    return None


def _extract_any_json_object(raw: str) -> Tuple[Optional[Dict[str, Any]], str]:
    raw = (raw or "").strip()
    if not raw:
        return None, "empty"

    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj, "direct"
    except Exception:
        pass

    m = _JSON_BLOCK_RE.search(raw)
    if m:
        cand = m.group(1).strip()
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj, "fenced"
        except Exception:
            pass

    cand2 = _first_balanced_object(raw)
    if cand2:
        try:
            obj = json.loads(cand2)
            if isinstance(obj, dict):
                return obj, "balanced"
        except Exception:
            pass

    return None, "none"


def _is_plan_shape(obj: Dict[str, Any]) -> bool:
    return isinstance(obj.get("days"), list)


def _pdf_to_text(pdf_bytes: bytes) -> str:
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    parts = [page.get_text("text") for page in doc]
    doc.close()
    return "\n".join(parts).strip()


async def _generate_raw(notes: str, days: int) -> str:
    prompt = build_mentrascan_prompt(notes, days=days)
    out = await llm.ask(
        api_key=API_KEY,
        prompt=prompt,
        system=MENTRASCAN_SYSTEM,
        max_tokens=1200,
        temperature=0.4,
    )
    return (out or "").strip()


@router.post("/plan_text")
@limiter.limit("10/minute")
async def plan_text(request: Request, content: str = Form(""), days: int = Form(DEFAULT_DAYS)):
    notes = (content or "").strip()
    if not notes:
        return JSONResponse({"error": "Empty notes."}, status_code=400)

    d = int(days) if str(days).isdigit() else DEFAULT_DAYS
    d = max(1, min(30, d))

    raw = await _generate_raw(notes, d)
    obj, mode = _extract_any_json_object(raw)

    if not obj:
        return JSONResponse({"ok": False, "reason": "Could not parse JSON", "extract_mode": mode, "raw": raw}, status_code=200)

    if not _is_plan_shape(obj):
        return JSONResponse({"ok": False, "reason": "JSON parsed but missing 'days'[]", "extract_mode": mode, "obj": obj, "raw": raw}, status_code=200)

    request.session["mentrascan_active_plan"] = obj
    return JSONResponse({"ok": True, "extract_mode": mode, "plan_json": obj})


@router.post("/plan_pdf")
@limiter.limit("5/minute")
async def plan_pdf(request: Request, file: UploadFile = File(...), days: int = Form(DEFAULT_DAYS)):
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
        return JSONResponse({"error": "PDF has too little selectable text (maybe scanned)."}, status_code=400)

    d = int(days) if str(days).isdigit() else DEFAULT_DAYS
    d = max(1, min(30, d))

    raw = await _generate_raw(text, d)
    obj, mode = _extract_any_json_object(raw)

    if not obj:
        return JSONResponse({"ok": False, "reason": "Could not parse JSON", "extract_mode": mode, "raw": raw}, status_code=200)

    if not _is_plan_shape(obj):
        return JSONResponse({"ok": False, "reason": "JSON parsed but missing 'days'[]", "extract_mode": mode, "obj": obj, "raw": raw}, status_code=200)

    request.session["mentrascan_active_plan"] = obj
    return JSONResponse({"ok": True, "extract_mode": mode, "plan_json": obj, "filename": fname, "chars": len(text)})


@router.get("/checks")
@limiter.limit("30/minute")
async def get_checks(request: Request, plan_id: str = Query(..., min_length=1, max_length=128)):
    _ensure_checks_table()
    owner = _owner_key(request)
    pid = plan_id.strip()

    with _db_connect() as con:
        rows = con.execute(
            "SELECT day, idx, checked FROM mentrascan_checks WHERE owner_key=? AND plan_id=?",
            (owner, pid),
        ).fetchall()

    return JSONResponse({"ok": True, "plan_id": pid, "checks": _checks_to_nested(rows)})


@router.post("/checks")
@limiter.limit("60/minute")
async def set_check(request: Request, payload: Dict[str, Any] = Body(...)):
    _ensure_checks_table()
    owner = _owner_key(request)

    plan_id = str(payload.get("plan_id") or "").strip()
    day = payload.get("day")
    idx = payload.get("idx")
    checked = payload.get("checked")

    if not plan_id:
        return JSONResponse({"error": "plan_id required"}, status_code=400)
    if not isinstance(day, int) or not (1 <= day <= 30):
        return JSONResponse({"error": "day must be int 1..30"}, status_code=400)
    if not isinstance(idx, int) or idx < 0 or idx > 999:
        return JSONResponse({"error": "idx must be int 0..999"}, status_code=400)

    checked_bool = bool(checked)
    now = datetime.utcnow().isoformat()

    with _db_connect() as con:
        con.execute(
            """
            INSERT INTO mentrascan_checks(owner_key, plan_id, day, idx, checked, updated_at)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(owner_key, plan_id, day, idx)
            DO UPDATE SET checked=excluded.checked, updated_at=excluded.updated_at
            """,
            (owner, plan_id, int(day), int(idx), 1 if checked_bool else 0, now),
        )
        con.commit()

    return JSONResponse({"ok": True})


@router.post("/reset_day")
@limiter.limit("10/minute")
async def reset_day(request: Request, payload: Dict[str, Any] = Body(...)):
    _ensure_checks_table()
    owner = _owner_key(request)

    plan_id = str(payload.get("plan_id") or "").strip()
    day = payload.get("day")

    if not plan_id:
        return JSONResponse({"error": "plan_id required"}, status_code=400)
    if not isinstance(day, int) or not (1 <= day <= 30):
        return JSONResponse({"error": "day must be int 1..30"}, status_code=400)

    with _db_connect() as con:
        con.execute(
            "DELETE FROM mentrascan_checks WHERE owner_key=? AND plan_id=? AND day=?",
            (owner, plan_id, int(day)),
        )
        con.commit()

    return JSONResponse({"ok": True})


@router.get("/active_plan")
@limiter.limit("60/minute")
async def active_plan(request: Request):
    plan = request.session.get("mentrascan_active_plan")
    return JSONResponse({"ok": True, "plan_json": plan})