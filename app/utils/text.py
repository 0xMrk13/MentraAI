# app/utils/text.py
import json
import re
from typing import List, Optional, Set

from discord import app_commands
from app.constants import QUIZ_TOPICS, RESOURCES


# -----------------------------
# LLM cleaning helpers
# -----------------------------
def unwrap_message_json(text: str) -> str:
    try:
        maybe = json.loads(text)
        if isinstance(maybe, dict) and "message" in maybe:
            return str(maybe["message"])
    except Exception:
        pass
    return text


def strip_non_latin(text: str) -> str:
    allowed = set("•—“”’…✅❌⏱🧠📊🎯🏁🔹📝📚🏆⏳🔧⚠️🚀💡🔑🧷🛡️🧪🧩")
    return "".join(ch for ch in (text or "") if ord(ch) < 128 or ch in allowed)


def clean_llm_text(text: str) -> str:
    text = unwrap_message_json(text or "")
    text = strip_non_latin(text)

    lines: List[str] = []
    for line in text.splitlines():
        s = line.strip()

        if re.match(r"^\s*#\w+\s*$", s):
            continue

        s = re.sub(r"^\s*#{1,6}\s*", "", s)
        lines.append(s)

    return "\n".join(lines).strip()


# -----------------------------
# Resources / topics helpers
# -----------------------------
def best_resource_key(topic: str) -> Optional[str]:
    if topic in RESOURCES:
        return topic
    tlow = (topic or "").lower()
    for k in RESOURCES:
        if tlow in k.lower() or k.lower() in tlow:
            return k
    return None


async def topics_autocomplete(current: str) -> List[app_commands.Choice[str]]:
    cur = (current or "").strip()
    cur_low = cur.lower()

    choices: List[app_commands.Choice[str]] = []

    # 1) allow exactly what user typed
    if cur:
        choices.append(app_commands.Choice(name=f'Use: "{cur}"', value=cur))

    # 2) then suggestions that match
    matches = [t for t in QUIZ_TOPICS if cur_low in t.lower()] if cur else QUIZ_TOPICS
    for t in matches[:25 - len(choices)]:
        choices.append(app_commands.Choice(name=t, value=t))

    return choices


# -----------------------------
# Generic helpers
# -----------------------------
_MARKER_CUTOFF = [
    "\nInstruction:",
    "\nTip:",
    "\nOutput:",
    "\nExample:",
    "\nExamples:",
    "\nJSON:",
    "\n```",
]


def strip_code_fences(text: str) -> str:
    return re.sub(r"```[\s\S]*?```", "", text or "", flags=re.S).strip()


def cutoff_at_markers(text: str) -> str:
    t = text or ""
    for m in _MARKER_CUTOFF:
        idx = t.find(m)
        if idx != -1:
            t = t[:idx].strip()
    return (t or "").strip()


def limit(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)].rstrip() + "…"


def normalize_newlines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", (text or "").strip()).strip()


def chunk_text(text: str, max_len: int) -> List[str]:
    t = (text or "").strip()
    if not t:
        return ["-"]

    chunks: List[str] = []
    while len(t) > max_len:
        cut = t.rfind("\n\n", 0, max_len)
        if cut == -1:
            cut = t.rfind("\n", 0, max_len)
        if cut == -1:
            cut = max_len

        piece = t[:cut].strip()
        if not piece:
            piece = t[:max_len].strip()

        chunks.append(piece)
        t = t[len(piece) :].strip()

    if t:
        chunks.append(t)

    return chunks


# -----------------------------
# Fuzzy dedupe helpers (Jaccard)
# -----------------------------
_STOP = {
    "the","a","an","and","or","to","of","in","on","for","with","by","at","from",
    "is","are","was","were","be","been","being","this","that","these","those",
    "what","which","who","when","where","why","how"
}

def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _tokens(s: str) -> Set[str]:
    return {t for t in _norm(s).split() if len(t) >= 3 and t not in _STOP}

def jaccard_sim(a: str, b: str) -> float:
    A, B = _tokens(a), _tokens(b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)
