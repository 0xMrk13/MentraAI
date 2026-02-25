from __future__ import annotations

import hashlib
import logging
import re
from typing import Dict, List, Optional, Tuple
from config import LLM_PROVIDER
from app.models.quiz import QuizQuestion
from app.services.exam_rules import rule_check
from app.utils.perms import clamp
from app.utils.text import jaccard_sim

log = logging.getLogger("MentraAI")

# -----------------------------
# Limits
# -----------------------------
MAX_Q_LEN = 200
MAX_EXPL_LEN = 200

CHOICE_TOTAL_MAX = 60
CHOICE_COUNT = 4
JACCARD_Q_SIM = 0.82
TEMPERATURE = 0.75
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# -----------------------------
# Parser regex
# -----------------------------
Q_RE = re.compile(r"^\s*(?:\d+[\)\.\-]\s*)?Q\s*[:\-—]\s*(.+?)\s*$", re.IGNORECASE)
CHOICE_RE = re.compile(r"^\s*(?:[-•]\s*)?([A-D])[\)\.\:]\s*(.+?)\s*$", re.IGNORECASE)

# Accept: ANSWER: B   / ANSWER: B) Guest / ANSWER: C) Guest blah
ANS_RE = re.compile(
    r"^\s*(?:ANSWER|ANS|CORRECT(?:\s+ANSWER)?)\s*[:\-—]\s*([A-D])(?:\s*[\)\.\:])?(?:\s+.*)?\s*$",
    re.IGNORECASE,
)

EXP_RE = re.compile(
    r"^\s*(EXPLAIN|EXPLANATION|RATIONALE|WHY)\s*[:\-—]\s*(.+?)\s*$", re.IGNORECASE
)
SEP_RE = re.compile(r"^\s*(?:---+|###)\s*$", re.IGNORECASE)


# -----------------------------
# Helpers
# -----------------------------


def _short_label(choice: str, *, max_words: int = 7) -> str:
    s = _clean_text(choice)
    s = _strip_choice_prefix(s)
    s = s.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
    s = " ".join(s.split())
    s = s.rstrip(" .;:,")

    words = s.split()
    if not words:
        return ""

    out = " ".join(words[:max_words])

    return out


def _remove_control_chars(s: str) -> str:
    return _CONTROL_CHARS_RE.sub("", s or "")


def _clean_text(s: str) -> str:
    s = _remove_control_chars(s or "")
    s = s.replace("\u0000", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _one_sentence_max(text: str) -> str:
    t = _clean_text(text)
    if not t:
        return ""
    # keep only first sentence, but DO NOT truncate length
    parts = re.split(r"(?<=[\.\!\?])\s+", t)
    return parts[0].strip() if parts else t


_STOP_TOKENS = {
    "the",
    "a",
    "an",
    "of",
    "to",
    "and",
    "or",
    "in",
    "on",
    "for",
    "with",
    "as",
    "is",
    "are",
    "does",
    "do",
    "which",
    "what",
    "when",
    "where",
    "who",
    "why",
    "how",
    "most",
    "best",
    "primarily",
    "generally",
}


def _tokset(s: str) -> set[str]:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    toks = [t for t in s.split() if len(t) > 2 and t not in _STOP_TOKENS]
    return set(toks)


def _opt_overlap(a: str, b: str) -> float:
    ta = _tokset(a)
    tb = _tokset(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _normalize_question(text: str) -> Optional[str]:
    t = _clean_text(text)
    if not t:
        return None

    ql = t.lower()

    return t


def _signature(question: str, choices: List[str]) -> str:
    base = (
        _clean_text(question).lower()
        + "||"
        + "||".join(_clean_text(c).lower() for c in choices)
    )
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def _q_only_signature(question: str) -> str:
    qn = _clean_text(question).lower()
    qn = re.sub(r"[^a-z0-9\s]", "", qn)
    qn = re.sub(r"\s+", " ", qn).strip()
    return hashlib.sha256(qn.encode("utf-8")).hexdigest()[:16]


def _starter3(question: str) -> str:
    words = re.findall(r"[a-z0-9]+", (question or "").lower())
    return " ".join(words[:3]).strip()


def _normalize_topic(topic: str) -> str:
    t = (topic or "").strip()
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def _strip_choice_prefix(s: str) -> str:
    return re.sub(r"^\s*([ABCD][\)\.\:\-]\s*|[-•]\s*)", "", s).strip()


CORRECT_TAG_RE = re.compile(r"\s*\(\s*correct\s*\)\s*$", re.IGNORECASE)


def _wrap_two_lines_choice(
    s: str,
    *,
    total_max: int = CHOICE_TOTAL_MAX,
) -> str:
    s = _clean_text(s).strip("\"'")
    s = _strip_choice_prefix(s)
    if not s:
        return ""
    s = CORRECT_TAG_RE.sub("", s)
    s = s.rstrip(" .;:,")
    s = " ".join(s.split())
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s)
    # Hard cap without ellipsis (avoid truncation ambiguity)
    if len(s) > total_max:
        s = s[:total_max].rstrip()

    return s


def _normalize_choice_for_discord(s: str) -> str:
    return _wrap_two_lines_choice(s)


def _accept_question(
    built: QuizQuestion,
    *,
    out: List[QuizQuestion],
    seen_sigs: set[str],
    seen_starters: set[str],
    seen_q_sigs: set[str],
    seen_q_texts: set[str],
) -> bool:
    sig = _signature(built.question, built.choices)
    if sig in seen_sigs:
        return False

    qsig = _q_only_signature(built.question)
    if qsig in seen_q_sigs:
        return False

    qn = _clean_text(built.question).lower()
    if qn in seen_q_texts:
        return False

    # near-duplicate question text vs already accepted in this run
    if any(jaccard_sim(built.question, prev.question) >= JACCARD_Q_SIM for prev in out):
        return False

    s3 = _starter3(built.question)
    if s3 and s3 in seen_starters:
        return False

    seen_sigs.add(sig)
    seen_q_sigs.add(qsig)
    seen_q_texts.add(qn)
    if s3:
        seen_starters.add(s3)
    return True


# -----------------------------
# Prompting
# -----------------------------
def _system_prompt() -> str:
    return (
        "You write exam-style cybersecurity multiple-choice questions.\n"
        "Output PLAIN TEXT ONLY.\n"
        "ABSOLUTE RULES:\n"
        "- Use exactly the format below.\n"
        "- No extra lines, no commentary, no titles.\n"
        "- Choices are SHORT LABELS (2-7 words), NOT sentences.\n"
        "- Exactly ONE correct option.\n"
        "- Explanation is ONE short sentence.\n"
        "- Separate questions with a line containing only: ---\n"
        "\n"
        "FORMAT (repeat for each question):\n"
        "Q: <one SHORT sentence>\n"
        "A) <short label>\n"
        "B) <short label>\n"
        "C) <short label>\n"
        "D) <short label>\n"
        "ANSWER: <A|B|C|D>\n"
        "EXPLAIN: <one short sentence>\n"
        "---\n"
        "\n"
        "Now follow the same format.\n"
    )


def _make_prompt(
    topic: str,
    n: int,
    *,
    avoid: Optional[List[str]] = None,
    hint: str = "",
) -> str:
    avoid_block = ""
    if avoid:
        avoid_short = [a for a in avoid if a][:12]
        if avoid_short:
            avoid_block = (
                "AVOID close paraphrases of these recent questions:\n"
                "- " + "\n- ".join(avoid_short) + "\n\n"
            )

    hint_block = f"EXTRA:\n{hint}\n\n" if hint else ""

    return (
        f"TOPIC: {topic}\n\n"
        "Style: OffSec / exam-style.\n"
        f"Generate EXACTLY {n} question(s).\n"
        f"Choices per question: {CHOICE_COUNT}.\n"
        f"Limits: Q<={MAX_Q_LEN} chars, EXPLAIN<={MAX_EXPL_LEN} chars, CHOICE<={CHOICE_TOTAL_MAX} chars.\n"
        "Rules:\n"
        "- Exactly ONE correct option.\n"
        "- Choices must be short labels (2–7 words), not full sentences.\n"
        "- Follow the exact output format from the system message.\n\n"
        f"{avoid_block}"
        f"{hint_block}"
        "Return the questions now."
    )


def _gen_params() -> dict:
    return {"temperature": TEMPERATURE}


def _strip_inline_sep(line: str) -> Tuple[str, bool]:
    """
    If a line ends with '---', remove it and signal flush.
    This fixes: 'EXPLAIN: ... ---' (inline separator).
    """
    if not line:
        return line, False
    s = line.rstrip()
    if s.endswith("---"):
        return s[:-3].rstrip(), True
    return line, False


# -----------------------------
# Parser for delimiter format
# -----------------------------
def _parse_quiz_blocks(text: str, *, expected_choices: int) -> List[Dict[str, object]]:
    s = _remove_control_chars(text or "")
    s = s.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not s:
        return []

    lines = [ln.rstrip() for ln in s.split("\n")]
    items: List[Dict[str, object]] = []

    cur_q: Optional[str] = None
    cur_choices: Dict[str, str] = {}
    cur_ans: Optional[str] = None
    cur_exp: Optional[str] = None

    order = ["A", "B", "C", "D"][:expected_choices]

    def reset():
        nonlocal cur_q, cur_choices, cur_ans, cur_exp
        cur_q = None
        cur_choices = {}
        cur_ans = None
        cur_exp = None

    def flush():
        nonlocal cur_q, cur_choices, cur_ans, cur_exp
        if not cur_q:
            reset()
            return

        if any(k not in cur_choices for k in order):
            reset()
            return

        if not cur_ans or cur_ans.upper() not in order:
            reset()
            return

        choices_list = [cur_choices[k] for k in order]
        ans_index = order.index(cur_ans.upper())
        exp = cur_exp or ""

        items.append(
            {
                "question": cur_q,
                "choices": choices_list,
                "answer_index": ans_index,
                "explanation": exp,
            }
        )
        reset()

    for ln in lines:
        ln, had_inline_sep = _strip_inline_sep(ln)

        # Separator line alone
        if SEP_RE.match(ln):
            flush()
            continue

        m = Q_RE.match(ln)
        if m:
            if cur_q:
                flush()
            cur_q = m.group(1).strip()
            if had_inline_sep:
                flush()
            continue
        m = CHOICE_RE.match(ln)
        if m:
            letter = m.group(1).upper()
            val = m.group(2).strip()
            cur_choices[letter] = val
            if had_inline_sep:
                flush()
            continue

        m = ANS_RE.match(ln)
        if m:
            cur_ans = m.group(1).upper()
            if had_inline_sep:
                flush()
            continue

        m = EXP_RE.match(ln)
        if m:
            cur_exp = m.group(2).strip()
            if had_inline_sep:
                flush()
            continue

        # explanation wrapped to multiple lines → append until separator/new block
        if cur_exp and ln.strip():
            if not (
                Q_RE.match(ln)
                or CHOICE_RE.match(ln)
                or ANS_RE.match(ln)
                or SEP_RE.match(ln)
                or EXP_RE.match(ln)
            ):
                cur_exp = (cur_exp + " " + ln.strip()).strip()
                if had_inline_sep:
                    flush()
                continue

        # If we got an inline sep on an "unknown" line, still flush safely
        if had_inline_sep:
            flush()
            continue

    flush()
    return items


def _validate_and_build(
    item: Dict[str, object], *, expected_choices: int
) -> Optional[QuizQuestion]:
    q = _normalize_question(str(item.get("question", "") or ""))
    if not q:
        return None

    # Ensure compact stem
    q = _clean_text(q)

    explanation = str(item.get("explanation", "") or "")
    explanation = _one_sentence_max(explanation)
    explanation = _clean_text(explanation)

    if not explanation:
        explanation = (
            "Prefer safe verification and clear evidence before concluding impact."
        )

    choices_raw = item.get("choices", [])
    if not isinstance(choices_raw, list) or len(choices_raw) != expected_choices:
        return None

    choices: List[str] = []
    for c in choices_raw:
        s = _normalize_choice_for_discord(str(c))
        if not s:
            return None

        s = _short_label(s, max_words=7)  # (NOTE: only once)
        if not s:
            return None

        choices.append(s)

    # duplicates check (ignore case)
    if len({c.lower() for c in choices}) != expected_choices:
        return None

    # parse answer index
    try:
        ai = int(item.get("answer_index", -1))
    except Exception:
        return None
    if ai < 0 or ai >= expected_choices:
        return None

    for i in range(expected_choices):
        for j in range(i + 1, expected_choices):
            if _opt_overlap(choices[i], choices[j]) >= 0.72:
                return None

    lens = [len(c) for c in choices]
    avg_other = (sum(lens) - lens[ai]) / max(1, (expected_choices - 1))
    if avg_other > 0 and lens[ai] > 1.6 * avg_other:
        return None

    exp_tok = _tokset(explanation)
    ans_tok = _tokset(choices[ai])
    if ans_tok:
        overlap = len(exp_tok & ans_tok) / max(1, len(ans_tok))
        if overlap < 0.05:
            pass

    rr = rule_check(q, choices, ai, explanation)
    if not rr.ok:
        return None

    if any("(correct)" in c.lower() for c in choices):
        return None

    return QuizQuestion(
        question=q, choices=choices, answer_index=ai, explanation=explanation
    )


# -----------------------------
# Main generator (guarantee fill-to-N)
# -----------------------------
async def generate_quiz_questions(
    llm,
    *,
    api_key: str,
    topic: str,
    n: int,
    store=None,
    guild_id: int | None = None,
    user_id: int | None = None,
) -> List[QuizQuestion]:
    topic = (topic or "").strip() or "general cybersecurity"
    topic_norm = _normalize_topic(topic)

    n = clamp(int(n), 1, 10)
    expected_choices = CHOICE_COUNT

    system = _system_prompt()

    out: List[QuizQuestion] = []
    seen_sigs: set[str] = set()
    seen_q_sigs: set[str] = set()
    seen_q_texts: set[str] = set()
    seen_starters: set[str] = set()
    avoid_texts: List[str] = []

    # Persistent memory
    if store is not None and guild_id is not None and user_id is not None:
        try:
            if hasattr(store, "get_recent_quiz_avoid"):
                avoid_texts.extend(
                    store.get_recent_quiz_avoid(
                        guild_id, user_id, topic_norm, limit=120, ttl_days=30
                    )[:40]
                )
        except Exception as e:
            log.warning("Persistent quiz_seen load failed: %s", e)

    topic_hint = ""
    max_rounds = 10

    # -----------------------------
    # Phase 1: batch collection
    # -----------------------------
    for round_i in range(max_rounds):
        remaining = n - len(out)
        if remaining <= 0:
            break

        request_n = min(max(remaining + 2, 3), 8)
        prompt = _make_prompt(topic, request_n, avoid=avoid_texts, hint=topic_hint)

        max_tokens = min(2000, 750 + int(request_n * 260))

        try:
            raw = await llm.ask(
                api_key=api_key,
                prompt=prompt,
                system=system,
                max_tokens=max_tokens,
                **_gen_params(),
            )
        except TypeError:
            # Fallback if llm.ask doesn't accept temperature kwarg
            raw = await llm.ask(
                api_key=api_key,
                prompt=prompt,
                system=system,
                max_tokens=max_tokens,
            )

        parsed = _parse_quiz_blocks(raw or "", expected_choices=expected_choices)

        if not parsed:
            log.warning("Quiz parse failed (round %d): 0 blocks", round_i + 1)
            log.warning("RAW (first 1200): %r", (raw or "")[:1200])
            topic_hint = "Follow the exact format."
            continue

        built_any = 0
        accepted_any = 0

        for item in parsed:
            built = _validate_and_build(item, expected_choices=expected_choices)
            if not built:
                continue
            built_any += 1

            if not _accept_question(
                built,
                out=out,
                seen_sigs=seen_sigs,
                seen_starters=seen_starters,
                seen_q_sigs=seen_q_sigs,
                seen_q_texts=seen_q_texts,
            ):
                continue

            out.append(built)
            accepted_any += 1

            avoid_texts.append(built.question)
            if len(avoid_texts) > 40:
                avoid_texts = avoid_texts[-40:]

            if len(out) >= n:
                break

        log.info(
            "Quiz round %d | parsed=%d | built=%d | accepted=%d | total=%d/%d",
            round_i + 1,
            len(parsed),
            built_any,
            accepted_any,
            len(out),
            n,
        )

        if accepted_any == 0:
            topic_hint = (
                "Keep the question clear and specific. "
                "All options must be plausible and in the same technical context."
            )

    # -----------------------------
    # Phase 2: one-by-one fill
    # -----------------------------
    tries = 0
    while len(out) < n and tries < 40:
        prompt = _make_prompt(
            topic,
            1,
            avoid=avoid_texts,
            hint="Output exactly ONE question only. Follow the exact format.",
        )

        try:
            raw = await llm.ask(
                api_key=api_key,
                prompt=prompt,
                system=system,
                max_tokens=900,
                **_gen_params(),
            )
        except TypeError:
            raw = await llm.ask(
                api_key=api_key,
                prompt=prompt,
                system=system,
                max_tokens=900,
            )

        parsed = _parse_quiz_blocks(raw or "", expected_choices=expected_choices)
        added = False

        for item in parsed:
            built = _validate_and_build(item, expected_choices=expected_choices)
            if not built:
                continue

            if not _accept_question(
                built,
                out=out,
                seen_sigs=seen_sigs,
                seen_starters=seen_starters,
                seen_q_sigs=seen_q_sigs,
                seen_q_texts=seen_q_texts,
            ):
                continue

            out.append(built)
            avoid_texts.append(built.question)
            if len(avoid_texts) > 60:
                avoid_texts = avoid_texts[-60:]
            added = True
            break

        if not added:
            log.warning(
                "One-by-one fill failed (try %d). RAW (first 900): %r",
                tries + 1,
                (raw or "")[:900],
            )

        tries += 1

    if len(out) < n:
        raise ValueError(
            f"Quiz generation failed: only {len(out)}/{n} questions produced."
        )

    if store is not None and guild_id is not None and user_id is not None:
        for q in out:
            try:
                sig = _signature(q.question, q.choices)
                s3 = _starter3(q.question)
                if hasattr(store, "add_quiz_seen"):
                    store.add_quiz_seen(
                        guild_id, user_id, topic_norm, sig, s3, q.question
                    )
            except Exception:
                pass

    return out[:n]
