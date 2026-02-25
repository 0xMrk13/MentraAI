"""
This file intentionally keeps rules conservative to avoid false positives.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional


# -----------------------------
# Result structure
# -----------------------------
@dataclass(frozen=True)
class RuleResult:
    ok: bool
    reason: str = ""


# -----------------------------
# Small helpers
# -----------------------------
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def _has_any(text: str, terms: List[str]) -> bool:
    t = _norm(text)
    return any(term in t for term in terms)


def _choice_text(choices: List[str], idx: int) -> str:
    if not choices or idx < 0 or idx >= len(choices):
        return ""
    return choices[idx] or ""


def _choice_has(choices: List[str], idx: int, terms: List[str]) -> bool:
    return _has_any(_choice_text(choices, idx), terms)


def _find_choice_idx(choices: List[str], terms: List[str]) -> Optional[int]:
    for i, c in enumerate(choices or []):
        if _has_any(c, terms):
            return i
    return None



def _rule_block_misconception_questions(q: str, choices: List[str], ai: int, expl: str) -> Optional[RuleResult]:
    """
    Misconception/myth questions are a major source of ambiguity.
    For reliability, we block them deterministically.
    """
    qn = _norm(q)
    if "common misconception" in qn or "misconception" in qn or "myth" in qn:
        return RuleResult(False, "Misconception-style questions are often ambiguous; blocked for reliability.")
    return None




# -----------------------------
# Public entry point
# -----------------------------
_RULES = [
    # Anti-LLM core failures
    _rule_block_misconception_questions,
]


def rule_check(
    question: str,
    choices: List[str],
    answer_index: int,
    explanation: str = "",
) -> RuleResult:
    """
    Run deterministic exam rules. Returns ok=False if a strong-signal mismatch is found.
    """
    q = question or ""
    expl = explanation or ""

    if not isinstance(choices, list) or len(choices) not in (3, 4):
        return RuleResult(False, "Invalid structure for rule_check (choices length).")

    if not isinstance(answer_index, int) or not (0 <= answer_index < len(choices)):
        return RuleResult(False, "Invalid structure for rule_check (answer_index range).")

    for fn in _RULES:
        res = fn(q, choices, answer_index, expl)
        if res is not None and res.ok is False:
            return res

    return RuleResult(True, "")

