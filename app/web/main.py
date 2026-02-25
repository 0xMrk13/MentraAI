from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.status import HTTP_403_FORBIDDEN
from urllib.parse import urlparse
from app.web.core.ratelimit import limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.web.core.deps import (
    SESSION_SECRET,
    IS_PROD,
    STATIC_DIR,
    templates,
    store,
)

from app.web.routes.notes import router as notes_router
from app.web.routes.auth import router as auth_router
from app.web.routes.pages import router as pages_router
from app.web.routes.api import router as api_router
from app.web.routes.agent_api import router as agent_router
from app.web.routes.mentrascan import router as mentrascan_router


# -----------------------------
# App
# -----------------------------
app = FastAPI(title="MentraAI Dashboard")

# -----------------------------
# Rate limiting
# -----------------------------
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

@app.exception_handler(RateLimitExceeded)
async def ratelimit_handler(request: Request, exc: RateLimitExceeded):
    return PlainTextResponse("Too Many Requests", status_code=429)

# -----------------------------
# Sessions
# -----------------------------
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",             # IMPORTANT for Discord OAuth callback
    https_only=bool(IS_PROD),    # True only in prod (HTTPS), False in local HTTP
    max_age=60 * 60 * 24 * 7,    # 7 days
)

# -----------------------------
# Static
# -----------------------------
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(os.path.join(STATIC_DIR, "img"), exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# shared state
app.state.templates = templates
app.state.store = store

# -----------------------------
# CSRF origin guard (same-origin)
# -----------------------------


@app.middleware("http")
async def csrf_same_host_guard(request: Request, call_next):
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        # Se SessionMiddleware non è attivo, non possiamo fare CSRF via session
        if "session" not in request.scope:
            return await call_next(request)

        # Applica CSRF SOLO se l'utente è loggato
        u = request.session.get("discord_user")
        if u and u.get("id"):
            origin = request.headers.get("origin")
            referer = request.headers.get("referer")

            base = str(request.base_url).rstrip("/")
            base_host = urlparse(base).netloc

            ok = False
            if origin:
                ok = (urlparse(origin).netloc == base_host)
            elif referer:
                ok = (urlparse(referer).netloc == base_host)

            if not ok:
                return Response("CSRF blocked", status_code=HTTP_403_FORBIDDEN)

    return await call_next(request)

# -----------------------------
# Security headers
# -----------------------------
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)

    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

    csp = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "img-src 'self' data: https://cdn.discordapp.com https://media.discordapp.net https://api.dicebear.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://api.fontshare.com; "
        "font-src 'self' https://api.fontshare.com https://cdn.fontshare.com data:; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "connect-src 'self';"
    )

    response.headers["Content-Security-Policy"] = csp.replace("\n", " ").replace("\r", " ").strip()
    return response

# -----------------------------
# Routes
# -----------------------------
app.include_router(auth_router)
app.include_router(pages_router)
app.include_router(api_router)
app.include_router(agent_router)
app.include_router(notes_router)
app.include_router(mentrascan_router)