// API client for the Avatar backend (CONTRACT.md §7). All endpoints are under
// /api. The chat endpoint streams Server-Sent Events; everything else is JSON.

export type Role = 'visitor' | 'avatar' | 'human';

export interface ToolCall {
  tool: string;
  // The backend persists the raw SDK arguments as a JSON **string** (it may also
  // be an object in older rows); callers must parse defensively (see bubbles.ts).
  args?: string | Record<string, unknown> | null;
  result_summary?: string | null;
}

export interface Message {
  id: number;
  role: Role;
  content: string;
  tool_calls: ToolCall[] | null;
  needs_attention: boolean;
  read: boolean;
  created_at: string;
}

export interface Conversation {
  conversation_id: string;
  conversation_name: string | null;
  messages: Message[];
}

export interface AppConfig {
  owner_name: string;
  model?: string;
  examples?: string[];
}

export interface AdminMe {
  authenticated: boolean;
  owner_name: string;
}

export interface InboxItem {
  conversation_id: string;
  name: string | null;
  initials: string;
  preview: string;
  last_role: Role;
  last_at: string;
  message_count: number;
  unread_count: number;
  needs_attention: boolean;
}

/** Raised when the chat endpoint returns HTTP 429 (rate limited). */
export class RateLimitError extends Error {
  constructor(public detail: string) {
    super(detail);
    this.name = 'RateLimitError';
  }
}

/** Raised when an admin route returns 401 (no/invalid session). */
export class UnauthorizedError extends Error {
  constructor(message = 'unauthorized') {
    super(message);
    this.name = 'UnauthorizedError';
  }
}

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (res.status === 401) throw new UnauthorizedError();
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail || body?.error || detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

// ---- Public endpoints -----------------------------------------------------

export async function getConfig(): Promise<AppConfig> {
  const res = await fetch('/api/config', { headers: { Accept: 'application/json' } });
  return jsonOrThrow<AppConfig>(res);
}

export async function getConversation(conversationId: string): Promise<Conversation> {
  const res = await fetch(`/api/conversation/${encodeURIComponent(conversationId)}`, {
    headers: { Accept: 'application/json' },
  });
  return jsonOrThrow<Conversation>(res);
}

// ---- SSE chat stream ------------------------------------------------------

export type ChatEvent =
  | { type: 'meta'; conversation_id: string }
  | { type: 'tool'; tool: string; phase: 'called' | 'output'; detail?: string }
  | { type: 'delta'; text: string }
  | {
      type: 'done';
      message_id: number;
      created_at: string;
      tool_calls: ToolCall[] | null;
      needs_attention: boolean;
    }
  | { type: 'error'; detail: string };

export interface ChatRequest {
  conversation_id: string;
  message: string;
  visitor_name?: string;
}

/**
 * POST /api/chat and yield parsed SSE events. Throws RateLimitError on 429
 * (raised before any token is emitted, per the contract).
 */
export async function* streamChat(
  body: ChatRequest,
  signal?: AbortSignal
): AsyncGenerator<ChatEvent, void, unknown> {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  });

  if (res.status === 429) {
    let detail = "You're sending messages too quickly. Please slow down.";
    try {
      const data = await res.json();
      detail = data?.detail || detail;
    } catch {
      /* keep default */
    }
    throw new RateLimitError(detail);
  }

  if (!res.ok || !res.body) {
    let detail = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      detail = data?.detail || data?.error || detail;
    } catch {
      /* non-JSON */
    }
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by a blank line.
      let sep: number;
      while ((sep = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const event = parseFrame(frame);
        if (event) yield event;
      }
    }
    // Flush any trailing frame without a terminating blank line.
    const tail = buffer.trim();
    if (tail) {
      const event = parseFrame(tail);
      if (event) yield event;
    }
  } finally {
    reader.releaseLock();
  }
}

function parseFrame(frame: string): ChatEvent | null {
  // Collect all `data:` lines in the frame (ignore comments / other fields).
  const dataLines: string[] = [];
  for (const line of frame.split('\n')) {
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).replace(/^\s/, ''));
    }
  }
  if (dataLines.length === 0) return null;
  const payload = dataLines.join('\n');
  try {
    return JSON.parse(payload) as ChatEvent;
  } catch {
    return null;
  }
}

// ---- Admin endpoints ------------------------------------------------------

export async function adminMe(): Promise<AdminMe> {
  const res = await fetch('/api/admin/me', { headers: { Accept: 'application/json' } });
  return jsonOrThrow<AdminMe>(res);
}

export async function adminLogin(password: string): Promise<{ ok: boolean; owner_name: string }> {
  const res = await fetch('/api/admin/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ password }),
  });
  if (res.status === 401) throw new UnauthorizedError('invalid_password');
  return jsonOrThrow<{ ok: boolean; owner_name: string }>(res);
}

export async function adminLogout(): Promise<void> {
  await fetch('/api/admin/logout', { method: 'POST', headers: { Accept: 'application/json' } });
}

export async function adminConversations(): Promise<InboxItem[]> {
  const res = await fetch('/api/admin/conversations', { headers: { Accept: 'application/json' } });
  return jsonOrThrow<InboxItem[]>(res);
}

export async function adminOpenConversation(conversationId: string): Promise<Conversation> {
  const res = await fetch(`/api/admin/conversation/${encodeURIComponent(conversationId)}`, {
    headers: { Accept: 'application/json' },
  });
  return jsonOrThrow<Conversation>(res);
}

export async function adminPostMessage(
  conversationId: string,
  content: string
): Promise<Message> {
  const res = await fetch(
    `/api/admin/conversation/${encodeURIComponent(conversationId)}/message`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ content }),
    }
  );
  return jsonOrThrow<Message>(res);
}
