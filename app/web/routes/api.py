from __future__ import annotations

import math
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from app.web.core.ratelimit import limiter
from app.web.core.deps import store, user_from_session, rows_to_items, my_rank_row

router = APIRouter()


@router.get("/api/leaderboard")
@limiter.limit("60/minute")
def api_leaderboard(
    request: Request,
    days: int = Query(default=30, ge=0, le=3650),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    topic: Optional[str] = Query(default=None),
):
    offset = (page - 1) * limit

    total = store.count_users(guild_id=None, days=days, topic=topic)
    total_pages = max(1, math.ceil(total / limit)) if total > 0 else 1
    page = max(1, min(page, total_pages))
    offset = (page - 1) * limit

    if topic:
        t_sql, t_args = store._time_filter_sql(days)
        sql = f"""
            SELECT
                user_id,
                COALESCE(MAX(display_name), MAX(username)) AS username,
                MAX(avatar_url) AS avatar_url,
                SUM(score) AS points,
                COUNT(*) AS quizzes,
                SUM(score)*1.0 / NULLIF(SUM(total), 0) AS accuracy
            FROM quiz_scores
            WHERE topic = ?
            {t_sql}
            GROUP BY user_id
            ORDER BY points DESC, accuracy DESC, quizzes DESC
            LIMIT ? OFFSET ?
        """
        with store._connect() as con:
            rows = con.execute(sql, (str(topic), *t_args, int(limit), int(offset))).fetchall()
            rows = [(r["user_id"], r["username"], r["avatar_url"], r["points"], r["quizzes"], r["accuracy"]) for r in rows]
        items = rows_to_items(rows)
    else:
        rows = store.top_users(guild_id=None, limit=limit, days=days, offset=offset)
        items = rows_to_items(rows)

    session_user = user_from_session(request)

    me = None
    me_in_page = False
    if session_user and session_user.get("id"):
        me = my_rank_row(user_id=int(session_user["id"]), days=days, topic=topic)
        if me:
            me_in_page = any(str(it.get("user_id")) == str(me["user_id"]) for it in items)

    return JSONResponse(
        {
            "items": items,
            "page": page,
            "limit": limit,
            "days": days,
            "topic": topic,
            "total": total,
            "total_pages": total_pages,
            "me": me,
            "me_in_page": me_in_page,
        }
    )
