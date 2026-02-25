from __future__ import annotations

import os
import secrets
from typing import Optional, Dict, Any, List

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.db import KeyStore
from app.services.llm import LLMClient

# -----------------------------
# Settings / env
# -----------------------------
try:
    from config import DB_PATH, OPENAI_BASE_URL, DEFAULT_MODEL
except Exception:
    DB_PATH = os.getenv("DB_PATH", "./data/studybot.sqlite3")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:11434/v1")
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "llama3.1")

# ---- Discord OAuth env ----
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://127.0.0.1:8000/callback")
DISCORD_SCOPES = os.getenv("DISCORD_SCOPES", "identify")  # keep minimal

SESSION_SECRET = os.environ["WEB_SESSION_SECRET"]
ENV = os.getenv("ENV", "").lower()
IS_PROD = ENV == "prod"

# -----------------------------
# Paths 
# -----------------------------
CORE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.abspath(os.path.join(CORE_DIR, ".."))  # app/web

TEMPLATES_DIR = os.getenv("TEMPLATES_DIR", os.path.join(WEB_DIR, "templates"))
STATIC_DIR = os.getenv("STATIC_DIR", os.path.join(WEB_DIR, "static"))

# -----------------------------
# Singletons 
# -----------------------------
templates = Jinja2Templates(directory=TEMPLATES_DIR)
store = KeyStore(DB_PATH)

provider = os.getenv("LLM_PROVIDER", "").strip().lower()

if provider == "groq":
    llm = LLMClient(
        base_url="https://api.groq.com/openai/v1",
        default_model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        openai_base_url="https://api.groq.com/openai/v1",
        openai_default_model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        prefer_responses_api=False,   # Groq NON usa /responses
        force_chat_completions=True,
    )
else:
    llm = LLMClient(
        base_url=OPENAI_BASE_URL,
        default_model=DEFAULT_MODEL,
        openai_base_url=os.getenv("OPENAI_REMOTE_BASE_URL", "").strip() or None,
        openai_default_model=os.getenv("OPENAI_REMOTE_MODEL", "").strip() or None,
        prefer_responses_api=True,
    )


# -----------------------------
# Session helpers
# -----------------------------
def user_from_session(request: Request) -> Optional[Dict[str, Any]]:
    return request.session.get("discord_user")


def sid(request: Request) -> str:
    s = request.session.get("sid")
    if not s:
        s = secrets.token_urlsafe(16)
        request.session["sid"] = s
    return s


def default_avatar(user_id: int) -> str:
    discrim = int(user_id) % 5
    return f"https://cdn.discordapp.com/embed/avatars/{discrim}.png"


# -----------------------------
# Agent chat persistence 
# -----------------------------
def agent_key(request: Request) -> str:
    u = user_from_session(request)
    if u and u.get("id"):
        return f"u:{u['id']}"
    return f"s:{sid(request)}"


def agent_db_init() -> None:
    # idempotente: safe anche se chiamata più volte
    with store._connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_key TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                content TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_agent_chat_key_time
            ON agent_chat_messages(agent_key, created_at)
            """
        )
        con.commit()


def agent_hist_get(agent_key_val: str, max_turns: int = 12) -> list[dict[str, str]]:
    with store._connect() as con:
        rows = con.execute(
            """
            SELECT role, content
            FROM agent_chat_messages
            WHERE agent_key = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (agent_key_val, int(max_turns)),
        ).fetchall()

    out: list[dict[str, str]] = []
    for r in reversed(rows or []):
        out.append({"role": r["role"], "content": r["content"]})
    return out


def agent_hist_add(agent_key_val: str, role: str, content: str) -> None:
    content = (content or "").strip()
    if not content:
        return
    role = (role or "").strip().lower()
    if role not in ("user", "assistant"):
        return

    with store._connect() as con:
        con.execute(
            "INSERT INTO agent_chat_messages(agent_key, role, content) VALUES (?,?,?)",
            (agent_key_val, role, content),
        )
        con.commit()


def agent_hist_clear(agent_key_val: str) -> None:
    with store._connect() as con:
        con.execute("DELETE FROM agent_chat_messages WHERE agent_key = ?", (agent_key_val,))
        con.commit()


def agent_migrate_session_to_user(request: Request, user_id: str) -> None:
    """
    If there is anonymous chat (s:<sid>) and user chat (u:<id>) is empty,
    migrate messages from session to user.
    """
    from_key = f"s:{sid(request)}"
    to_key = f"u:{user_id}"

    # don't overwrite/duplicate if already has history
    if agent_hist_get(to_key, max_turns=1):
        return

    history = agent_hist_get(from_key, max_turns=500)
    if not history:
        return

    for m in history:
        role = (m.get("role") or "").strip().lower()
        content = (m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            agent_hist_add(to_key, role, content)

    agent_hist_clear(from_key)


def build_transcript(history: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for m in history:
        role = (m.get("role") or "").strip().lower()
        content = (m.get("content") or "").strip()
        if not content:
            continue
        lines.append(("User: " if role == "user" else "Assistant: ") + content)
    return "\n".join(lines).strip()


# -----------------------------
# Helpers for leaderboard payload
# -----------------------------
def _clean_avatar_url(avatar_url: Optional[str], uid_int: int) -> str:
    s = (avatar_url or "").strip()
    if not s:
        return default_avatar(uid_int)

    low = s.lower()
    if low in ("none", "null", "undefined"):
        return default_avatar(uid_int)

    # accetta solo url http(s)
    if not (low.startswith("http://") or low.startswith("https://")):
        return default_avatar(uid_int)

    return s


def rows_to_items(rows: List[tuple]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for user_id, username, avatar_url, points, quizzes, acc in rows:
        acc_pct = int(round((acc or 0) * 100))
        uid_int = int(user_id)

        items.append(
            {
                "user_id": str(user_id),
                "username": (username or f"User {uid_int}"),
                "avatar_url": _clean_avatar_url(avatar_url, uid_int),
                "points": int(points or 0),
                "quizzes": int(quizzes or 0),
                "accuracy_pct": acc_pct,
            }
        )
    return items


def my_rank_row(user_id: int, days: int, topic: Optional[str]) -> Optional[Dict[str, Any]]:
    t_sql, t_args = store._time_filter_sql(days)

    where_topic = "AND topic = ?" if topic else ""
    args: list[Any] = []
    if topic:
        args.append(str(topic))
    args.extend(t_args)

    with store._connect() as con:
        row = con.execute(
            f"""
            WITH agg AS (
              SELECT
                user_id,
                COALESCE(MAX(display_name), MAX(username)) AS username,
                MAX(avatar_url) AS avatar_url,
                SUM(score) AS points,
                COUNT(*) AS quizzes,
                SUM(score)*1.0 / NULLIF(SUM(total),0) AS accuracy
              FROM quiz_scores
              WHERE 1=1
              {where_topic}
              {t_sql}
              GROUP BY user_id
            ),
            ranked AS (
              SELECT
                *,
                ROW_NUMBER() OVER (ORDER BY points DESC, accuracy DESC, quizzes DESC) AS rnk
              FROM agg
            )
            SELECT rnk, user_id, username, avatar_url, points, quizzes, accuracy
            FROM ranked
            WHERE user_id = ?
            LIMIT 1
            """,
            (*args, int(user_id)),
        ).fetchone()

    if not row:
        return None

    uid = int(row["user_id"])
    return {
        "user_id": str(uid),
        "username": row["username"] or f"User {uid}",
        "avatar_url": row["avatar_url"] or default_avatar(uid),
        "points": int(row["points"] or 0),
        "quizzes": int(row["quizzes"] or 0),
        "accuracy_pct": int(round((row["accuracy"] or 0) * 100)),
        "rank": int(row["rnk"]),
    }


def lookup_user_public_profile(user_id: int) -> Dict[str, Optional[str]]:
    return store.get_user_public_profile(int(user_id))


# init agent db tables at import (safe / idempotent)
agent_db_init()
