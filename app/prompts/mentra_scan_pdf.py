# app/prompts/mentra_scan_pdf.py
from __future__ import annotations

MENTRASCAN_PDF_EXTRACT_SYSTEM = """You extract study structure from notes.

Rules:
- Use ONLY what is in the notes.
- Do NOT add new topics.
- Output ONLY JSON. No markdown, no emojis, no extra text.

Schema:
{
  "topics": [
    {"title": "string", "bullets": ["string", "string", "string"]}
  ]
}
"""

MENTRASCAN_PDF_PLAN_SYSTEM = """You generate a 7-day plan from extracted topics.

Rules:
- Use ONLY the provided extracted topics.
- Do NOT add new topics.
- Keep tasks notes-based deliverables: summarize, outline, define, compare, flashcards, cheat sheet.
- Output ONLY JSON. No markdown, no emojis, no extra text.
- Exactly 7 days, each day: day, timebox, goal, tasks (1–3), quiz (3).
- Default timebox: Day 1–5 "60 min", Day 6–7 "90 min".
"""

def build_pdf_extract_prompt(notes: str) -> str:
    notes = (notes or "").strip()
    return f"""Extract a compact list of topics from these notes.

NOTES:
{notes}

Return only JSON in the schema."""
    
def build_pdf_plan_prompt(extracted_topics_text: str) -> str:
    return f"""Create a 7-day study plan using ONLY these extracted topics.

TOPICS:
{extracted_topics_text}

Return only JSON in the required plan schema."""

