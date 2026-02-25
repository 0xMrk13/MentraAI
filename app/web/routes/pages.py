from __future__ import annotations

from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()


def _user_from_session(request: Request) -> Optional[Dict[str, Any]]:
    return request.session.get("discord_user")


def _default_avatar(user_id: int) -> str:
    discrim = int(user_id) % 5
    return f"https://cdn.discordapp.com/embed/avatars/{discrim}.png"


@router.get("/", response_class=HTMLResponse)
def leaderboard_page(
    request: Request,
    tab: str = Query(default="leaderboard"),
    topic: Optional[str] = Query(default=None),
    days: int = Query(default=30, ge=0, le=3650),
    limit: int = Query(default=10, ge=1, le=100),
):
    store = request.app.state.store
    templates = request.app.state.templates

    topics = store.list_topics(guild_id=None, limit=25)

    return templates.TemplateResponse(
        "leaderboard.html",
        {
            "request": request,
            "user": _user_from_session(request),
            "tab": tab,
            "topic": topic,
            "days": days,
            "limit": limit,
            "topics": topics,
        },
    )


@router.get("/me")
def me(request: Request):
    user = _user_from_session(request)
    if not user:
        return RedirectResponse("/login?next=/me", status_code=302)
    return RedirectResponse(f"/user?user_id={int(user['id'])}", status_code=302)

@router.get("/mentrascan", response_class=HTMLResponse)
def mentrascan_page(request: Request):
    templates = request.app.state.templates

    return templates.TemplateResponse(
        "mentrascan.html",
        {
            "request": request,
            "user": _user_from_session(request),
            # utile per login redirect coerente
            "_next": "/mentrascan",
            # opzionale: per UI (tab attivo)
            "tab": "mentrascan",
        },
    )

@router.get("/user", response_class=HTMLResponse)
def user_page(
    request: Request,
    user_id: Optional[int] = Query(default=None),
    days: int = Query(default=30, ge=0, le=3650),
):
    if user_id is None:
        return RedirectResponse("/me", status_code=302)

    store = request.app.state.store
    templates = request.app.state.templates

    # 1) Stats + streak + runs (primary)
    s = store.user_stats(user_id=int(user_id), guild_id=None, days=days) or {}
    streak = store.user_streak(user_id=int(user_id), guild_id=None) or {}
    runs = store.recent_user_runs(user_id=int(user_id), guild_id=None, limit=12, days=days) or []

    # 2) Fallback “single source”
    if int(s.get("quizzes") or 0) == 0:
        s = store.user_stats_from_scores(user_id=int(user_id), days=days) or s

    if not runs:
        runs = store.recent_user_runs_from_scores(user_id=int(user_id), days=days, limit=12)

    acc = float(s.get("accuracy") or 0.0)
    total = int(s.get("total") or 0)
    acc_pct = int(round(acc * 100)) if total else 0

    timeframe = "All-time" if days == 0 else f"Last {days} days"


    session_user = _user_from_session(request)

    # 3) Display name + avatar (NO session bleed)
    session_user = _user_from_session(request)
    is_me = bool(session_user and str(session_user.get("id")) == str(user_id))

    if is_me:
        display_name = session_user.get("global_name") or session_user.get("username") or f"User {user_id}"
        uid = int(session_user.get("id"))
        av = session_user.get("avatar")
        avatar_url = f"https://cdn.discordapp.com/avatars/{uid}/{av}.png?size=96" if av else _default_avatar(uid)
    else:
        pub = store.get_user_public_profile(int(user_id)) or {}
        display_name = (pub.get("display_name") or "").strip() or f"User {user_id}"
        avatar_url = (pub.get("avatar_url") or "").strip() or _default_avatar(int(user_id))


    # 4) Runs list -> dicts for template
    run_items: List[Dict[str, Any]] = []
    for topic, score, total, created_at in runs:
        run_items.append(
            {
                "topic": str(topic or ""),
                "score": int(score or 0),
                "total": int(total or 0),
                "created_at": str(created_at),
            }
        )

    # 5) Heatmap series (all-time)
    series = store.user_points_timeseries(user_id=int(user_id), guild_id=None, days=0)
    series_labels = [d for (d, _) in series]
    series_values = [p for (_, p) in series]
    print("PROFILE OPEN:", "req_user_id=", user_id, "display=", display_name, "avatar=", avatar_url)

    return templates.TemplateResponse(
        "user.html",
        {
            "request": request,
            "display_name": display_name,
            "avatar_url": avatar_url,
            "days": days,
            "timeframe": timeframe,
            "user_id": int(user_id),
            "stats": {
                "quizzes": int(s.get("quizzes") or 0),
                "correct": int(s.get("correct") or 0),
                "total": int(s.get("total") or 0),
                "accuracy_pct": acc_pct,
                "best_topic": (s.get("best_topic") or "—"),
                "streak_days": int(streak.get("streak_days") or 0),
                "days_played": int(streak.get("days_played") or 0),
            },
            "runs": run_items,
            "series_labels": series_labels,
            "series_values": series_values,
            "user": session_user,
        },
    )
