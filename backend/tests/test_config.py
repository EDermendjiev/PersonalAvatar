"""Tests for ``app.config`` — env loading and the SESSION_SECRET fallback.

These reload the module under a controlled environment so the assertions do not
depend on the contents of the real project-root ``.env`` (CONTRACT.md §1).
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import app.config as config_module


def _reload_config_with(monkeypatch, env: dict[str, str]):
    """Reload ``app.config`` with ``env`` applied and ``load_dotenv`` neutralised.

    ``config.py`` calls ``load_dotenv(ENV_PATH, override=True)`` at import time;
    we stub it to a no-op so the values we set via ``monkeypatch.setenv`` are the
    ones the module reads, regardless of the real ``.env``.
    """
    # Clear all the keys config reads so leftovers from .env don't leak in.
    for key in (
        "OPENROUTER_API_KEY",
        "MODEL",
        "OWNER_NAME",
        "ADMIN_PASSWORD",
        "SESSION_SECRET",
        "COOKIE_SECURE",
        "PUSHOVER_USER",
        "PUSHOVER_TOKEN",
        "SUPABASE_URL",
        "SUPABASE_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    return importlib.reload(config_module)


@pytest.fixture(autouse=True)
def _restore_config():
    """Ensure the real module is reloaded after each test so other test files
    (which import ``app.config`` indirectly) see the genuine values again."""
    yield
    importlib.reload(config_module)


def test_defaults_applied(monkeypatch):
    cfg = _reload_config_with(monkeypatch, {"ADMIN_PASSWORD": "pw"})
    assert cfg.MODEL == "openai/gpt-5.4-nano"
    assert cfg.OWNER_NAME == "Ed Donner"  # contract fallback
    assert cfg.OPENROUTER_BASE_URL == "https://openrouter.ai/api/v1"
    assert cfg.COOKIE_SECURE is False
    assert cfg.MAX_MESSAGE_CHARS == 20_000
    assert cfg.RATE_LIMIT_PER_MINUTE == 20


def test_values_read_from_env(monkeypatch):
    cfg = _reload_config_with(
        monkeypatch,
        {
            "OWNER_NAME": "Emil Dermendzhiev",
            "MODEL": "openai/gpt-5.4-mini",
            "ADMIN_PASSWORD": "hunter2",
            "OPENROUTER_API_KEY": "sk-or-xyz",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_KEY": "sb_secret_abc",
        },
    )
    assert cfg.OWNER_NAME == "Emil Dermendzhiev"
    assert cfg.MODEL == "openai/gpt-5.4-mini"
    assert cfg.ADMIN_PASSWORD == "hunter2"
    assert cfg.OPENROUTER_API_KEY == "sk-or-xyz"
    assert cfg.SUPABASE_URL == "https://example.supabase.co"
    assert cfg.SUPABASE_KEY == "sb_secret_abc"


def test_session_secret_fallback_derives_from_password(monkeypatch):
    cfg = _reload_config_with(monkeypatch, {"ADMIN_PASSWORD": "swordfish"})
    assert cfg.SESSION_SECRET == "avatar::swordfish"


def test_session_secret_explicit_overrides_fallback(monkeypatch):
    cfg = _reload_config_with(
        monkeypatch,
        {"ADMIN_PASSWORD": "swordfish", "SESSION_SECRET": "explicit-secret"},
    )
    assert cfg.SESSION_SECRET == "explicit-secret"


def test_blank_values_treated_as_unset(monkeypatch):
    """Whitespace-only env values fall back to defaults (the ``_get`` helper)."""
    cfg = _reload_config_with(
        monkeypatch,
        {"ADMIN_PASSWORD": "pw", "OWNER_NAME": "   ", "MODEL": ""},
    )
    assert cfg.OWNER_NAME == "Ed Donner"
    assert cfg.MODEL == "openai/gpt-5.4-nano"


def test_cookie_secure_enabled(monkeypatch):
    cfg = _reload_config_with(
        monkeypatch, {"ADMIN_PASSWORD": "pw", "COOKIE_SECURE": "1"}
    )
    assert cfg.COOKIE_SECURE is True


def test_pushover_optional_unset_is_none(monkeypatch):
    cfg = _reload_config_with(monkeypatch, {"ADMIN_PASSWORD": "pw"})
    assert cfg.PUSHOVER_USER is None
    assert cfg.PUSHOVER_TOKEN is None


def test_paths_resolved(monkeypatch):
    cfg = _reload_config_with(monkeypatch, {"ADMIN_PASSWORD": "pw"})
    assert cfg.KNOWLEDGE_DIR == cfg.PROJECT_ROOT / "knowledge"
    assert cfg.FRONTEND_DIST == cfg.PROJECT_ROOT / "frontend" / "dist"
    assert isinstance(cfg.PROJECT_ROOT, Path)
    # ENV_PATH must point at the project-root .env (two levels above app/).
    assert cfg.ENV_PATH == cfg.PROJECT_ROOT / ".env"
