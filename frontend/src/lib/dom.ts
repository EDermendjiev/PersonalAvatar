// Tiny DOM + formatting helpers shared by the visitor and admin apps.

/** Query a single element, asserting it exists (typed). */
export function $<T extends HTMLElement = HTMLElement>(
  selector: string,
  root: ParentNode = document
): T {
  const node = root.querySelector<T>(selector);
  if (!node) throw new Error(`Element not found: ${selector}`);
  return node;
}

/** Query a single element, or null if absent. */
export function $opt<T extends HTMLElement = HTMLElement>(
  selector: string,
  root: ParentNode = document
): T | null {
  return root.querySelector<T>(selector);
}

type Attrs = Record<string, string | number | boolean | null | undefined>;
type Child = Node | string | null | undefined | false;

/**
 * Create an element with attributes and children.
 * `class` / `className` set the class; other keys become attributes
 * (a `true` value sets a bare attribute; `false`/null/undefined are skipped).
 */
export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Attrs = {},
  children: Child[] = []
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class' || key === 'className') {
      node.className = String(value);
    } else if (value === true) {
      node.setAttribute(key, '');
    } else {
      node.setAttribute(key, String(value));
    }
  }
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    node.append(typeof child === 'string' ? document.createTextNode(child) : child);
  }
  return node;
}

/** Initials from a name/initials string. Falls back to a neutral dot. */
export function initials(name: string | null | undefined): string {
  const raw = (name || '').trim();
  if (!raw) return '·';
  // If they typed something that already looks like initials (<=3 chars, no spaces), upcase it.
  if (raw.length <= 3 && !/\s/.test(raw)) return raw.toUpperCase();
  const parts = raw.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Human-friendly clock time (HH:MM) for a message bubble. */
export function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
}

/** Relative day-ish label for inbox rows: 14:08 / Yest. / Mon / 12 Jun. */
export function formatInboxTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const dayMs = 86_400_000;
  const t = d.getTime();
  if (t >= startOfToday) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
  }
  if (t >= startOfToday - dayMs) return 'Yest.';
  if (t >= startOfToday - 6 * dayMs) return d.toLocaleDateString([], { weekday: 'short' });
  return d.toLocaleDateString([], { day: 'numeric', month: 'short' });
}

/** A day-separator label used at the top of a thread. */
export function formatDaySep(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'Today';
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const dayMs = 86_400_000;
  const t = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  if (t === startOfToday) return 'Today';
  if (t === startOfToday - dayMs) return 'Yesterday';
  return d.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'short' });
}

/** Escape text for safe insertion into HTML (used for non-markdown text). */
export function escapeHtml(text: string): string {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/** Debounce a function by `ms`. */
export function debounce<A extends unknown[]>(
  fn: (...args: A) => void,
  ms: number
): (...args: A) => void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return (...args: A) => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

/** Auto-size a textarea up to a max height (matches the mockup behaviour). */
export function autosize(textarea: HTMLTextAreaElement, max = 160): void {
  textarea.style.height = 'auto';
  textarea.style.height = `${Math.min(textarea.scrollHeight, max)}px`;
}
