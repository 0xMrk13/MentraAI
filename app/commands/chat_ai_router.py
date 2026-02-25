from __future__ import annotations

import json
from typing import Any, Dict

from app.services.llm import LLMClient

ALLOWED_INTENTS = {
    "quiz", "ask", "flashcards", "plan",
    "stats", "rank", "topics", "resources",
    "unknown",
}

async def infer_intent(llm: LLMClient, text: str) -> Dict[str, Any]:
    prompt = f"""
You are an intent router for a Discord cybersecurity study bot.
Return ONLY valid JSON (no markdown, no extra text).

User text:
{text}

Choose intent from:
quiz, ask, flashcards, plan, stats, rank, topics, resources, unknown

Rules:
- If user asks for a quiz/test/questions: intent="quiz"
- If user asks to explain something: intent="ask"
- If user asks for flashcards: intent="flashcards"
- If user asks for a study schedule: intent="plan"
- If user asks for leaderboard/ranking: intent="rank"
- If user asks for statistics: intent="stats"
- If user asks for topics list: intent="topics"
- If user asks for learning resources: intent="resources"
- Otherwise: intent="unknown"

Output JSON schema:
{{
  "intent": "quiz|ask|flashcards|plan|stats|rank|topics|resources|unknown",
  "topic": "string or null",
  "question": "string or null",
  "plan_request": "string or null"
}}
""".strip()

    system = "Return ONLY JSON."
    raw = await llm.ask(api_key="", prompt=prompt, system=system, max_tokens=220)

    try:
        data = json.loads(raw.strip())
    except Exception:
        return {"intent": "unknown", "topic": None, "question": None, "plan_request": None}

    intent = str(data.get("intent", "unknown")).lower()
    if intent not in ALLOWED_INTENTS:
        intent = "unknown"

    topic = data.get("topic", None)
    question = data.get("question", None)
    plan_request = data.get("plan_request", None)

    if isinstance(topic, str):
        topic = topic.strip() or None
    else:
        topic = None

    if isinstance(question, str):
        question = question.strip() or None
    else:
        question = None

    if isinstance(plan_request, str):
        plan_request = plan_request.strip() or None
    else:
        plan_request = None

    return {
        "intent": intent,
        "topic": topic,
        "question": question,
        "plan_request": plan_request,
    }
