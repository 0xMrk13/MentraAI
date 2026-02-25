from __future__ import annotations

from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.web.core.deps import (
    DISCORD_CLIENT_ID,
    DISCORD_CLIENT_SECRET,
    DISCORD_REDIRECT_URI,
    DISCORD_SCOPES,
    store,
    user_from_session,
    default_avatar,
    agent_migrate_session_to_user,
)
from app.web.core.security import safe_next, pkce_verifier, pkce_challenge

router = APIRouter()


@router.get("/login")
def login(request: Request, next: str = "/"):
    if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET:
        return HTMLResponse(
            "Discord OAuth is not configured. Set DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET.",
            status_code=500,
        )

    next = safe_next(next)

    state = __import__("secrets").token_urlsafe(24)
    verifier = pkce_verifier()
    challenge = pkce_challenge(verifier)

    request.session["oauth_state"] = state
    request.session["oauth_next"] = next
    request.session["pkce_verifier"] = verifier

    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": DISCORD_SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "none",
    }

    auth_url = "https://discord.com/api/oauth2/authorize?" + urlencode(params)
    return RedirectResponse(auth_url, status_code=302)


@router.get("/callback")
async def callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
):
    if error:
        request.session.pop("oauth_state", None)
        request.session.pop("pkce_verifier", None)
        next_url = safe_next(request.session.pop("oauth_next", "/"))

        msg = f"Login cancelled ({error})."
        if error_description:
            msg += f" {error_description}"

        return HTMLResponse(
            f"{msg}<br><br><a href='/login?next={next_url}'>Try again</a>",
            status_code=400,
        )

    expected = request.session.get("oauth_state")
    if not expected or state != expected:
        return HTMLResponse("Invalid OAuth state.", status_code=400)

    if not code:
        return HTMLResponse("Missing OAuth code.", status_code=400)

    verifier = request.session.get("pkce_verifier")
    if not verifier:
        return HTMLResponse("Missing PKCE verifier (session expired).", status_code=400)

    token_url = "https://discord.com/api/oauth2/token"
    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "code_verifier": verifier,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    async with httpx.AsyncClient(timeout=15) as client:
        tok = await client.post(token_url, data=data, headers=headers)
        if tok.status_code != 200:
            return HTMLResponse(f"Token exchange failed: {tok.text}", status_code=400)

        access_token = tok.json().get("access_token")
        if not access_token:
            return HTMLResponse("No access_token returned.", status_code=400)

        me = await client.get(
            "https://discord.com/api/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if me.status_code != 200:
            return HTMLResponse(f"User fetch failed: {me.text}", status_code=400)
        user = me.json()

    # Store user in session
    request.session["discord_user"] = {
        "id": user.get("id"),
        "username": user.get("username"),
        "global_name": user.get("global_name"),
        "avatar": user.get("avatar"),
    }

    # migrate chat (anon -> user) if needed
    try:
        if user.get("id"):
            agent_migrate_session_to_user(request, str(user["id"]))
    except Exception:
        pass

    # save public identity into DB
    try:
        uid = int(user.get("id"))
        display_name = user.get("global_name") or user.get("username")

        avatar = user.get("avatar")
        if avatar:
            avatar_url = f"https://cdn.discordapp.com/avatars/{uid}/{avatar}.png?size=96"
        else:
            avatar_url = default_avatar(uid)

        store.update_user_identity(uid, display_name, avatar_url)
    except Exception:
        pass

    request.session.pop("oauth_state", None)
    request.session.pop("pkce_verifier", None)
    next_url = safe_next(request.session.pop("oauth_next", "/"))

    return RedirectResponse(next_url or "/", status_code=302)


@router.get("/logout")
def logout(request: Request, next: str = "/"):
    next = safe_next(next)
    request.session.pop("discord_user", None)
    request.session.pop("oauth_state", None)
    request.session.pop("oauth_next", None)
    request.session.pop("pkce_verifier", None)
    return RedirectResponse(next or "/", status_code=302)


@router.get("/me")
def me(request: Request):
    u = user_from_session(request)
    if not u:
        return RedirectResponse("/login?next=/me", status_code=302)
    user_id = int(u["id"])
    return RedirectResponse(f"/user?user_id={user_id}", status_code=302)
