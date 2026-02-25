from __future__ import annotations
import json
from typing import Any, Dict, List, Optional

def _as_list(x) -> List[str]:
    if not x:
        return []
    if isinstance(x, list):
        return [str(i).strip() for i in x if str(i).strip()]
    return [str(x).strip()]

def validate_plan(obj: Dict[str, Any]) -> Dict[str, Any]:
    # minimal validation + normalization
    days = obj.get("days", [])
    if not isinstance(days, list) or not days:
        raise ValueError("Invalid JSON: missing days")

    normalized_days = []
    for d in days:
        if not isinstance(d, dict):
            continue
        day = int(d.get("day", len(normalized_days) + 1))
        normalized_days.append({
            "day": day,
            "title": str(d.get("title", f"Day {day}")).strip(),
            "timebox": str(d.get("timebox", "")).strip(),
            "learn": _as_list(d.get("learn")),
            "do": _as_list(d.get("do")),
            "practice": _as_list(d.get("practice")),
            "check": _as_list(d.get("check")),
            "deliverable": str(d.get("deliverable", "")).strip(),
        })

    obj["days"] = normalized_days
    obj.setdefault("constraints", {"weekday":"", "weekend":"", "rest_day":""})
    return obj

def try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    t = text.strip()

    # sometimes models wrap with ```json ... ```
    if t.startswith("```"):
        t = t.strip("`")
        # best-effort strip "json" header
        t = t.replace("json\n", "", 1).strip()

    # try parse
    try:
        obj = json.loads(t)
        if isinstance(obj, dict):
            return validate_plan(obj)
    except Exception:
        return None
    return None

def render_plan_text(plan: Dict[str, Any]) -> str:
    lines = []
    for d in plan["days"]:
        day = d["day"]
        title = d["title"]
        timebox = f" ({d['timebox']})" if d.get("timebox") else ""
        lines.append(f"Day {day} — {title}{timebox}")
        lines.append("Learn")
        for x in d.get("learn", []):
            lines.append(f"- {x}")
        lines.append("Do")
        for x in d.get("do", []):
            lines.append(f"- {x}")
        lines.append("Practice")
        for x in d.get("practice", []):
            lines.append(f"- {x}")
        lines.append("Check")
        for x in d.get("check", []):
            lines.append(f"- {x}")
        if d.get("deliverable"):
            lines.append("Deliverable")
            lines.append(f"- {d['deliverable']}")
        lines.append("")  # blank line
    return "\n".join(lines).strip()
