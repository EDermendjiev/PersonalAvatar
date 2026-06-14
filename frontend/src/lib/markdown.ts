// Markdown rendering for message bubbles: marked -> DOMPurify-sanitized HTML.
// Links open in a new tab and carry rel="noopener" via a DOMPurify hook.

import { marked } from 'marked';
import DOMPurify from 'dompurify';

marked.setOptions({
  gfm: true,
  breaks: true,
});

// Make every rendered link safe + open in a new tab. Runs on each sanitize.
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.nodeName === 'A') {
    const a = node as unknown as HTMLAnchorElement;
    const href = a.getAttribute('href') || '';
    // Allow mailto/tel/http(s) only; drop anything else.
    if (!/^(https?:|mailto:|tel:)/i.test(href)) {
      a.removeAttribute('href');
    } else if (/^https?:/i.test(href)) {
      a.setAttribute('target', '_blank');
      a.setAttribute('rel', 'noopener noreferrer');
    }
  }
});

const ALLOWED_TAGS = [
  'p', 'br', 'strong', 'b', 'em', 'i', 'del', 's', 'code', 'pre',
  'a', 'ul', 'ol', 'li', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'span',
];
const ALLOWED_ATTR = ['href', 'title', 'target', 'rel'];

/** Render trusted-source markdown (avatar/human/visitor content) to safe HTML. */
export function renderMarkdown(source: string): string {
  const html = marked.parse(source ?? '', { async: false }) as string;
  return DOMPurify.sanitize(html, { ALLOWED_TAGS, ALLOWED_ATTR });
}

/** Render plain text safely (no markdown) — preserves newlines. */
export function renderText(source: string): string {
  const escaped = DOMPurify.sanitize(source ?? '', { ALLOWED_TAGS: [], ALLOWED_ATTR: [] });
  return escaped.replace(/\n/g, '<br>');
}
