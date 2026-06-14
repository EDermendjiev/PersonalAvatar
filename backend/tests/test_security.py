"""Tests for ``app.security`` — admin session signing/verifying and the guard.

Covers token round-trip, tamper/expiry rejection, the non-raising
``is_authenticated`` check, the raising ``require_admin`` dependency, and cookie
attributes (CONTRACT.md §9).
"""

from __future__ import annotations

import time

import pytest
from fastapi import HTTPException
from itsdangerous import URLSafeTimedSerializer

from app import config, security


class _FakeRequest:
    """Minimal stand-in exposing only ``.cookies`` like a Starlette Request."""

    def __init__(self, cookies: dict[str, str]):
        self.cookies = cookies


class _FakeResponse:
    """Captures ``set_cookie`` / ``delete_cookie`` kwargs for assertions."""

    def __init__(self):
        self.set_kwargs = None
        self.deleted = None

    def set_cookie(self, **kwargs):
        self.set_kwargs = kwargs

    def delete_cookie(self, **kwargs):
        self.deleted = kwargs


def test_issue_and_validate_round_trip():
    token = security.issue_session()
    assert security._valid_token(token) is True


def test_valid_token_rejects_empty_and_garbage():
    assert security._valid_token(None) is False
    assert security._valid_token("") is False
    assert security._valid_token("not-a-real-token") is False


def test_valid_token_rejects_wrong_secret():
    """A token signed with a different secret must not validate."""
    other = URLSafeTimedSerializer("a-different-secret", salt=config.SESSION_COOKIE_SALT)
    forged = other.dumps({"admin": True})
    assert security._valid_token(forged) is False


def test_valid_token_rejects_wrong_salt():
    other = URLSafeTimedSerializer(config.SESSION_SECRET, salt="wrong-salt")
    forged = other.dumps({"admin": True})
    assert security._valid_token(forged) is False


def test_valid_token_rejects_non_admin_payload():
    token = security._serializer.dumps({"admin": False})
    assert security._valid_token(token) is False
    token2 = security._serializer.dumps({"something": "else"})
    assert security._valid_token(token2) is False


def test_valid_token_expiry(monkeypatch):
    """A token older than SESSION_MAX_AGE is rejected."""
    token = security.issue_session()
    monkeypatch.setattr(config, "SESSION_MAX_AGE", 0)
    # itsdangerous treats max_age=0 with a >0 age as expired; give it a moment.
    time.sleep(1.1)
    assert security._valid_token(token) is False


def test_is_authenticated_reads_cookie():
    token = security.issue_session()
    good = _FakeRequest({config.SESSION_COOKIE_NAME: token})
    bad = _FakeRequest({})
    assert security.is_authenticated(good) is True
    assert security.is_authenticated(bad) is False


def test_require_admin_passes_with_cookie():
    token = security.issue_session()
    req = _FakeRequest({config.SESSION_COOKIE_NAME: token})
    assert security.require_admin(req) is True


def test_require_admin_raises_without_cookie():
    req = _FakeRequest({})
    with pytest.raises(HTTPException) as exc:
        security.require_admin(req)
    assert exc.value.status_code == 401
    assert exc.value.detail == {"error": "unauthorized"}


def test_set_session_cookie_attributes(monkeypatch):
    monkeypatch.setattr(config, "COOKIE_SECURE", True)
    resp = _FakeResponse()
    security.set_session_cookie(resp)
    kw = resp.set_kwargs
    assert kw["key"] == config.SESSION_COOKIE_NAME
    assert kw["httponly"] is True
    assert kw["samesite"] == "lax"
    assert kw["secure"] is True
    assert kw["max_age"] == config.SESSION_MAX_AGE
    assert kw["path"] == "/"
    # The value is a valid session token.
    assert security._valid_token(kw["value"]) is True


def test_set_session_cookie_insecure_by_default(monkeypatch):
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    resp = _FakeResponse()
    security.set_session_cookie(resp)
    assert resp.set_kwargs["secure"] is False


def test_clear_session_cookie():
    resp = _FakeResponse()
    security.clear_session_cookie(resp)
    assert resp.deleted["key"] == config.SESSION_COOKIE_NAME
    assert resp.deleted["path"] == "/"
