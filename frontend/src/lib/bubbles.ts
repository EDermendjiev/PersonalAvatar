// Shared message-bubble builders. The markup mirrors the mockups exactly so the
// visitor chat and the admin thread render identically (components.md / mockups).

import type { Message, ToolCall } from './api.ts';
import { el, initials, formatTime } from './dom.ts';
import { icon } from './icons.ts';
import { renderMarkdown } from './markdown.ts';

const ROBOT = '/assets/avatar-robot-round.png';
const HUMAN = '/assets/avatar-human.png';

/** A tool-status line, e.g. `faq_tool · "automation"` (cyan) / push (yellow). */
export function toolLine(tool: string, detail?: string): HTMLElement {
  const isPush = tool === 'push_tool';
  const cls = `tool-line${isPush ? ' tool-line--push' : ''}`;
  const label = isPush
    ? detail
      ? `push_tool · ${detail}`
      : 'push_tool · notified the owner'
    : detail
      ? `${tool} · ${detail}`
      : tool;
  return el('span', { class: cls }, [icon(isPush ? 'i-bell' : 'i-search', 'icon--sm'), label]);
}

/**
 * A tool call's `args` arrives as a JSON **string** from the backend (the raw
 * SDK arguments) — not an object. Parse it defensively into an object; never
 * throw (using `in` on a string primitive would otherwise crash the render).
 */
export function parseToolArgs(args: unknown): Record<string, unknown> | null {
  if (args == null) return null;
  if (typeof args === 'object') return args as Record<string, unknown>;
  if (typeof args === 'string') {
    const trimmed = args.trim();
    if (!trimmed) return null;
    try {
      const parsed = JSON.parse(trimmed);
      return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : null;
    } catch {
      return null;
    }
  }
  return null;
}

/** Human-friendly detail for a tool line, e.g. `Q3` (faq) / `notified Emil`. */
export function toolDetail(
  tool: string,
  args: unknown,
  ownerName: string,
  resultSummary?: string | null
): string {
  if (resultSummary) return resultSummary;
  const obj = parseToolArgs(args);
  if (tool === 'faq_tool' && obj && 'question_number' in obj) {
    return `Q${String(obj.question_number)}`;
  }
  if (tool === 'push_tool') {
    return `notified ${firstName(ownerName)}`;
  }
  return '';
}

function toolStack(toolCalls: ToolCall[] | null | undefined, ownerName: string): HTMLElement | null {
  if (!toolCalls || toolCalls.length === 0) return null;
  const stack = el('div', { class: 'tool-stack' });
  for (const tc of toolCalls) {
    const detail = toolDetail(tc.tool, tc.args, ownerName, tc.result_summary);
    stack.append(toolLine(tc.tool, detail));
  }
  return stack;
}

function firstName(name: string): string {
  return (name || '').trim().split(/\s+/)[0] || name || 'the owner';
}

/** Detect a bare `Qn` message (used to show the `.qn-tag` on the visitor turn). */
export function matchQn(text: string): string | null {
  const m = (text || '').trim().match(/^[Qq](\d+)$/);
  return m ? `Q${m[1]}` : null;
}

/** A visitor bubble (blue, right-aligned). Shows the `.qn-tag` for bare `Qn`. */
export function visitorBubble(content: string, time: string, name: string | null): HTMLElement {
  const qn = matchQn(content);
  const meta = el('div', { class: 'msg__meta' });
  if (qn) {
    meta.append(el('span', { class: 'qn-tag' }, [icon('i-zap', 'icon--sm'), qn]));
  }
  meta.append(el('span', { class: 'msg__time' }, [time]));

  const bubble = el('div', { class: 'msg__bubble' });
  bubble.textContent = content;

  return el('div', { class: 'msg msg--visitor' }, [
    el('div', { class: 'avatar avatar--sm avatar--visitor' }, [initials(name)]),
    el('div', { class: 'msg__col' }, [meta, bubble]),
  ]);
}

/** An avatar (twin) bubble (cyan name, left-aligned), with optional tool stack. */
export function avatarBubble(
  contentHtml: string,
  time: string,
  toolCalls: ToolCall[] | null,
  ownerName: string,
  instant = false
): HTMLElement {
  const col = el('div', { class: 'msg__col' });
  const stack = toolStack(toolCalls, ownerName);
  if (stack) col.append(stack);

  const meta = el('div', { class: 'msg__meta' }, [
    el('span', { class: 'msg__name' }, ['Avatar']),
  ]);
  if (instant) meta.append(el('span', { class: 'badge badge--cyan' }, ['instant']));
  meta.append(el('span', { class: 'msg__time' }, [time]));
  col.append(meta);

  const bubble = el('div', { class: 'msg__bubble' });
  bubble.innerHTML = contentHtml;
  col.append(bubble);

  return el('div', { class: 'msg msg--avatar' }, [
    el('div', { class: 'avatar avatar--sm avatar--twin' }, [
      el('img', { src: ROBOT, alt: 'Avatar' }),
    ]),
    col,
  ]);
}

/** A human (owner) bubble — yellow ring + tint + glow + "{owner} · live". */
export function humanBubble(contentHtml: string, time: string, ownerName: string): HTMLElement {
  const bubble = el('div', { class: 'msg__bubble' });
  bubble.innerHTML = contentHtml;
  return el('div', { class: 'msg msg--human' }, [
    el('div', { class: 'avatar avatar--sm avatar--owner' }, [
      el('img', { src: HUMAN, alt: ownerName }),
    ]),
    el('div', { class: 'msg__col' }, [
      el('div', { class: 'msg__meta' }, [
        el('span', { class: 'msg__name' }, [ownerName]),
        el('span', { class: 'live-tag' }, ['live']),
        el('span', { class: 'msg__time' }, [time]),
      ]),
      bubble,
    ]),
  ]);
}

/** Build a bubble for a stored message of any role. */
export function messageBubble(
  msg: Message,
  ownerName: string,
  visitorName: string | null = null
): HTMLElement {
  const time = formatTime(msg.created_at);
  if (msg.role === 'visitor') {
    return visitorBubble(msg.content, time, visitorName);
  }
  if (msg.role === 'human') {
    return humanBubble(renderMarkdown(msg.content), time, ownerName);
  }
  const instant = !!matchQn(precedingHint(msg));
  return avatarBubble(renderMarkdown(msg.content), time, msg.tool_calls, ownerName, instant);
}

// The avatar's instant `Qn` answer starts with "**Qn:**"; surface the badge then.
function precedingHint(msg: Message): string {
  const m = msg.content.match(/^\*\*(Q\d+):/);
  return m ? m[1] : '';
}
