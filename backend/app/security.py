"""Admin session: sign/verify the session cookie and the FastAPI guard.

A signed, timed token (``itsdangerous``) stored in an httpOnly cookie guards all
admin data routes. ``require_admin`` is the dependency every ``/api/admin/*``
data route (everything except ``login`` and ``me``) depends on (CONTRACT.md §9).
"""

from __future__ import annotations

from fastapi import HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from . import config

_serializer = URLSafeTimedSerializer(
    config.SESSION_SECRET, salt=config.SESSION_COOKIE_SALT
)


def issue_session() -> str:
    """Return a signed session token marking an authenticated admin."""
    return _serializer.dumps({"admin": True})


def _valid_token(token: str | None) -> bool:
    """True iff the token is a valid, unexpired admin session token."""
    if not token:
        return False
    try:
        data = _serializer.loads(token, max_age=config.SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return bool(isinstance(data, dict) and data.get("admin") is True)


def is_authenticated(request: Request) -> bool:
    """Non-raising check used by the open ``/api/admin/me`` endpoint."""
    return _valid_token(request.cookies.get(config.SESSION_COOKIE_NAME))


def set_session_cookie(response: Response) -> None:
    """Attach a fresh admin session cookie to ``response``."""
    response.set_cookie(
        key=config.SESSION_COOKIE_NAME,
        value=issue_session(),
        httponly=True,
        samesite="lax",
        secure=config.COOKIE_SECURE,
        max_age=config.SESSION_MAX_AGE,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Remove the admin session cookie."""
    response.delete_cookie(key=config.SESSION_COOKIE_NAME, path="/")


def require_admin(request: Request) -> bool:
    """FastAPI dependency: allow the request only with a valid session cookie.

    Raises ``HTTPException(401)`` with the contract's JSON body otherwise.
    """
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail={"error": "unauthorized"})
    return True
