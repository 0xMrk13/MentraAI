import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.models.cards import Flashcard
from app.utils.text import jaccard_sim

log = logging.getLogger("MentraAI")

MAX_Q = 110
MAX_A = 220
MAX_N = 10

JACCARD_Q_SIM = 0.88


# -----------------------------
# JSON helpers (robust)
# -----------------------------
def _strip_fences(text: str) -> str:
    s = (text or "").strip()
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) >= 3:
            s = parts[1].strip()
            if s.lower().startswith("json"):
                s = s[4:].strip()
    return s.strip()


def _normalize_quotes(s: str) -> str:
    return s.replace("“", '"').replace("”", '"').replace("’", "'")


def _strip_control_chars(s: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)


def _remove_trailing_commas(s: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", s)


def _extract_first_json_object(text: str) -> str:
    s = _strip_control_chars(_normalize_quotes(_strip_fences(text)))
    start = s.find("{")
    if start == -1:
        raise ValueError("No JSON object found")

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
            continue

        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1].strip()

    raise ValueError("Unbalanced JSON braces")


def _safe_json_loads(text: str) -> Dict[str, Any]:
    candidate = _remove_trailing_commas(_extract_first_json_object(text))
    data = json.loads(candidate)
    if not isinstance(data, dict):
        raise ValueError("JSON root is not an object")
    return data


async def _retry_fix_json(llm, api_key: str, broken: str, n: int) -> Dict[str, Any]:
    prompt = (
        "Fix the following so it becomes VALID JSON ONLY.\n"
        "- Output ONLY JSON\n"
        '- Keep structure: {"cards": [{"q":"...","a":"..."}]}\n'
        f"- EXACTLY {n} cards\n"
        f"- q max {MAX_Q} chars, a max {MAX_A} chars\n\n"
        f"BROKEN:\n{broken}"
    )

    fixed = await llm.ask(
        api_key=api_key,
        prompt=prompt,
        system="You repair JSON. Output ONLY valid JSON.",
        max_tokens=min(1400, 350 + n * 80),
    )
    return _safe_json_loads(fixed)


# -----------------------------
# Cleaning / validation
# -----------------------------
def _clean_text(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^\s*(\d+[\.\)]\s*|[-•]\s*)", "", s)
    return s.strip()


def _coerce_cards(data: Dict[str, Any]) -> List[Flashcard]:
    raw = data.get("cards", [])
    if not isinstance(raw, list):
        return []

    out: List[Flashcard] = []
    for item in raw:
        if not isinstance(item, dict):
            continue

        q = _clean_text(str(item.get("q", "")))[:MAX_Q]
        a = _clean_text(str(item.get("a", "")))[:MAX_A]

        if len(q) < 4 or len(a) < 4:
            continue

        out.append(Flashcard(q=q, a=a))

    return out


# -----------------------------
# Dedupe / acceptance
# -----------------------------
def _accept_card(card: Flashcard, *, out: List[Flashcard]) -> bool:
    return not any(jaccard_sim(card.q, prev.q) >= JACCARD_Q_SIM for prev in out)


# -----------------------------
# LLM batch generation
# -----------------------------
async def _generate_batch(
    llm,
    *,
    api_key: str,
    topic: str,
    n: int,
    avoid: Optional[List[str]] = None,
) -> List[Flashcard]:
    n = max(1, min(MAX_N, int(n)))
    avoid = avoid or []

    avoid_block = ""
    if avoid:
        sample = "\n".join(f"- {x[:120]}" for x in avoid[:12])
        avoid_block = f"\nAvoid duplicates of these questions:\n{sample}\n"

    prompt = f"""
Generate EXACTLY {n} cybersecurity flashcards about: {topic}.
{avoid_block}

Return ONLY valid JSON in this format:
{{
  "cards": [
    {{"q": "question", "a": "answer"}}
  ]
}}

Rules:
- EXACTLY {n} cards
- English only
- Q <= {MAX_Q} chars
- A <= {MAX_A} chars (1–3 short sentences)
- Practical OffSec style
- No numbering, no bullets
- Each card must test a DIFFERENT angle
""".strip()

    raw = await llm.ask(
        api_key=api_key,
        prompt=prompt,
        system="You are an offensive security study assistant. Return ONLY valid JSON.",
        max_tokens=min(2200, 450 + n * 90),
    )

    try:
        data = _safe_json_loads(raw)
    except Exception as e:
        log.warning("Flashcards JSON parse failed: %s", e)
        data = await _retry_fix_json(llm, api_key, raw, n)

    return _coerce_cards(data)


# -----------------------------
# Public API
# -----------------------------
async def generate_flashcards(
    llm,
    *,
    api_key: str,
    topic: str,
    n: int,
) -> List[Flashcard]:
    n = max(1, min(MAX_N, int(n)))
    topic = (topic or "").strip() or "cybersecurity"

    out: List[Flashcard] = []
    tries = 0

    while len(out) < n and tries < 3:
        tries += 1
        remaining = n - len(out)

        avoid_qs = [c.q for c in out]
        batch_topic = topic if tries == 1 else f"{topic} (new set {tries})"

        batch = await _generate_batch(
            llm,
            api_key=api_key,
            topic=batch_topic,
            n=remaining,
            avoid=avoid_qs,
        )

        for card in batch:
            if _accept_card(card, out=out):
                out.append(card)
            if len(out) >= n:
                break

    # fail-soft padding (very rare)
    while len(out) < n:
        i = len(out) + 1
        out.append(
            Flashcard(
                q=f"{topic}: key concept #{i}?",
                a="Regenerate to get a full-quality card for this slot.",
            )
        )

    return out[:n]
