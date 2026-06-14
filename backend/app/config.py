"""Environment configuration for the Avatar backend.

Loads the project-root ``.env`` (two directories above ``backend/app``) with
``override=True`` and exposes every setting the rest of the app needs as plain
module constants. Defaults follow CONTRACT.md §1.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Project root is two levels up from this file: backend/app/config.py -> root.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
ENV_PATH: Path = PROJECT_ROOT / ".env"

# Load the project-root .env, overriding anything already in the environment so
# that the file is the single source of truth during local development.
load_dotenv(ENV_PATH, override=True)


def _get(name: str, default: str | None = None) -> str | None:
    """Read an env var, treating blank/whitespace-only values as unset."""
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


# --- LLM / OpenRouter -------------------------------------------------------
OPENROUTER_API_KEY: str = _get("OPENROUTER_API_KEY", "") or ""
MODEL: str = _get("MODEL", "openai/gpt-5.4-nano") or "openai/gpt-5.4-nano"
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"


def _get_int(name: str, default: int) -> int:
    """Read an int env var, falling back to ``default`` on unset/invalid."""
    raw = _get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Cap the model's completion tokens per reply. Conversational avatar replies
# need only a few thousand tokens; leaving this unset lets the SDK default to a
# very large value (65536), which over-reserves budget on metered/limited
# OpenRouter accounts (HTTP 402). Tunable via the MAX_OUTPUT_TOKENS env var.
MAX_OUTPUT_TOKENS: int = _get_int("MAX_OUTPUT_TOKENS", 8000)

# --- Identity ---------------------------------------------------------------
OWNER_NAME: str = _get("OWNER_NAME", "Emil Dermendzhiev") or "Emil Dermendzhiev"

# --- Admin auth -------------------------------------------------------------
ADMIN_PASSWORD: str = _get("ADMIN_PASSWORD", "") or ""

# Signs the admin session cookie. Falls back to a value derived from the admin
# password so the app still works if SESSION_SECRET is unset (CONTRACT.md §1).
SESSION_SECRET: str = _get("SESSION_SECRET") or f"avatar::{ADMIN_PASSWORD}"

# Cookie is marked Secure (HTTPS-only) when COOKIE_SECURE == "1".
COOKIE_SECURE: bool = (_get("COOKIE_SECURE", "0") or "0") == "1"

# --- Pushover (optional) ----------------------------------------------------
PUSHOVER_USER: str | None = _get("PUSHOVER_USER")
PUSHOVER_TOKEN: str | None = _get("PUSHOVER_TOKEN")

# --- Supabase ---------------------------------------------------------------
SUPABASE_URL: str = _get("SUPABASE_URL", "") or ""
SUPABASE_KEY: str = _get("SUPABASE_KEY", "") or ""

# --- Paths ------------------------------------------------------------------
KNOWLEDGE_DIR: Path = PROJECT_ROOT / "knowledge"
# Built frontend (Vite multi-page output). Served by main.py when present.
FRONTEND_DIST: Path = PROJECT_ROOT / "frontend" / "dist"

# --- Abuse guards (fixed, no configuration per SPEC Q&A #12) ----------------
MAX_MESSAGE_CHARS: int = 20_000
TRUNCATION_NOTE: str = (
    "\n\n[...message truncated as it's too long; ask the visitor to send "
    "something more concise]"
)
RATE_LIMIT_PER_MINUTE: int = 20

# --- Session cookie details -------------------------------------------------
SESSION_COOKIE_NAME: str = "avatar_admin"
SESSION_COOKIE_SALT: str = "avatar-admin"
SESSION_MAX_AGE: int = 7 * 24 * 3600  # one week, in seconds
