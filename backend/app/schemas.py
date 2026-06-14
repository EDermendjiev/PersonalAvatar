"""Pydantic request/response models for the HTTP API (CONTRACT.md §7, §10)."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# --- Requests ---------------------------------------------------------------


class ChatRequest(BaseModel):
    conversation_id: str
    message: str
    visitor_name: Optional[str] = None


class LoginRequest(BaseModel):
    password: str


class AdminMessageRequest(BaseModel):
    content: str


# --- Responses --------------------------------------------------------------


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    tool_calls: Optional[list[dict[str, Any]]] = None
    needs_attention: bool = False
    read: bool = False
    created_at: str


class ConversationOut(BaseModel):
    conversation_id: str
    conversation_name: Optional[str] = None
    messages: list[MessageOut] = Field(default_factory=list)


class ConversationSummary(BaseModel):
    conversation_id: str
    name: Optional[str] = None
    initials: str
    preview: str
    last_role: str
    last_at: str
    message_count: int
    unread_count: int
    needs_attention: bool


class ConfigOut(BaseModel):
    owner_name: str
    model: str


class LoginResponse(BaseModel):
    ok: bool
    owner_name: str


class MeResponse(BaseModel):
    authenticated: bool
    owner_name: str
