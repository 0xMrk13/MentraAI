from __future__ import annotations

import os
import base64
import hashlib
from urllib.parse import urlparse


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def pkce_verifier() -> str:
    # 43-128 chars recommended; 32 bytes -> 43 chars base64url
    return _b64url(os.urandom(32))


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return _b64url(digest)


def safe_next(next_url: str) -> str:
    if not next_url:
        return "/"
    p = urlparse(next_url)
    if p.scheme or p.netloc:
        return "/"
    if not next_url.startswith("/"):
        return "/"
    return next_url
