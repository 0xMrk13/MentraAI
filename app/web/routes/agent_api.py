from __future__ import annotations
import re
from time import time
from typing import Any
import os
from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from app.web.core.deps import llm, sid, agent_key, agent_hist_clear
from app.web.core.ratelimit import limiter
from app.prompts.agent_prompts import load_agent_prompt

router = APIRouter(prefix="/api/agent", tags=["agent"])

def _effective_api_key() -> str:
    prov = os.getenv("LLM_PROVIDER", "").strip().lower()
    if prov == "groq":
        return (os.getenv("GROQ_API_KEY", "") or "").strip()
    return (os.getenv("BOT_API_KEY", "") or "").strip()



_AGENT_RL: dict[str, tuple[int, int]] = {}  # sid -> (window_start_ts, count)
_CONTROL_RE = re.compile(
    r"(<\|.*?\|>)|(\b(role|system|developer|assistant|user)\s*:)",
    re.IGNORECASE | re.DOTALL
)

_DISCLOSE_RE = re.compile(
    r"\b(system|developer|prompt|instructions|policy|hidden)\b.*\b(show|reveal|print|output|verbatim|dump)\b"
    r"|\b(show|reveal|print|output|verbatim|dump)\b.*\b(system|developer|prompt|instructions|policy|hidden)\b",
    re.IGNORECASE | re.DOTALL
)

def sanitize_user_text(s: str) -> str:
    s = (s or "").strip()
    s = _CONTROL_RE.sub("", s)
    return s[:12000].strip()

def is_disclosure_request(s: str) -> bool:
    return bool(_DISCLOSE_RE.search((s or "").strip()))

def _rate_limit_ok(s: str, limit: int = 25, window_sec: int = 60) -> bool:
    now = int(time())
    start, cnt = _AGENT_RL.get(s, (now, 0))
    if now - start >= window_sec:
        _AGENT_RL[s] = (now, 1)
        return True
    if cnt >= limit:
        return False
    _AGENT_RL[s] = (start, cnt + 1)
    return True

@router.post("/reset")
def agent_reset(request: Request):
    key = agent_key(request)
    agent_hist_clear(key)
    _AGENT_RL.pop(sid(request), None)
    return JSONResponse({"ok": True})

@router.post("/chat")
@limiter.limit("10/minute")
async def agent_chat(request: Request, payload: dict = Body(...)):
    s = sid(request)
    if not _rate_limit_ok(s):
        return JSONResponse({"error": "Too many requests. Slow down."}, status_code=429)
    
    msg_raw = (payload.get("message") or "")
    msg = sanitize_user_text(msg_raw)

    if not msg:
        return JSONResponse({"error": "Empty message."}, status_code=400)

    if is_disclosure_request(msg_raw):
        return JSONResponse({
            "reply": "I can’t share internal instructions. Tell me what you want to build or learn and I’ll help."
        })

    # ---- scegli API key in base al provider ----
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    api_key = (
        os.getenv("GROQ_API_KEY", "")
        if provider == "groq"
        else os.getenv("BOT_API_KEY", "")
    ).strip()

    # ---- system + prompt ----
    system = load_agent_prompt("base")

    prompt = f"USER_MESSAGE:\n{msg}\n"

    # ---- LLM call ----
    try:
        reply = await llm.ask(
            api_key=api_key,
            prompt=prompt,
            system=system,
            max_tokens=1000,
            temperature=0.5,
        )
    except Exception as e:
        return JSONResponse({"error": f"Agent error: {e}"}, status_code=500)

    # ---- post-processing ----
    reply = (reply or "I couldn't generate a reply. Try again.").strip()
    if is_disclosure_request(reply) or "<|" in reply.lower() or "security:" in reply.lower():
        reply = "I can’t share internal instructions. Ask me about cybersecurity or paste the code you want to fix."

    return JSONResponse({"reply": reply})

