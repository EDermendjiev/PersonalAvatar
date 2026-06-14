// Visitor Chat app. Behaviour per SPEC + CONTRACT.md §10 + ux-flows.md.

import {
  getConfig,
  getConversation,
  streamChat,
  RateLimitError,
  type Message,
  type ChatEvent,
  type AppConfig,
} from './lib/api.ts';
import {
  $,
  el,
  initials,
  formatTime,
  formatDaySep,
  autosize,
} from './lib/dom.ts';
import { icon } from './lib/icons.ts';
import { renderMarkdown } from './lib/markdown.ts';
import { wireThemeToggle } from './lib/theme.ts';
import { visitorBubble, messageBubble, matchQn, toolDetail } from './lib/bubbles.ts';

// ---- Constants ------------------------------------------------------------

const CID_COOKIE = 'avatar_cid';
const KEEP_COOKIE = 'avatar_keep';
const NAME_KEY = 'avatar-visitor-name';
const POLL_FAST = 10_000; // 10s
const POLL_SLOW = 60_000; // 60s after 5 min idle
const IDLE_BEFORE_SLOW = 5 * 60_000;

const DEFAULT_EXAMPLES = [
  'What does E&P Systems actually do?',
  'What automations can you build for my business?',
  "What's your technical background?",
  'Can you help with an AI-powered website?',
];

// ---- Cookies --------------------------------------------------------------

function setCookie(name: string, value: string, days = 365): void {
  const maxAge = days * 24 * 60 * 60;
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${maxAge}; SameSite=Lax`;
}
function getCookie(name: string): string | null {
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : null;
}
function deleteCookie(name: string): void {
  document.cookie = `${name}=; path=/; max-age=0; SameSite=Lax`;
}

// ---- App state ------------------------------------------------------------

interface State {
  conversationId: string;
  ownerName: string;
  examples: string[];
  messages: Message[];
  keepChat: boolean;
  visitorName: string;
  streaming: boolean;
  lastActivity: number;
  pollTimer: ReturnType<typeof setTimeout> | null;
  abort: AbortController | null;
}

const dom = {
  thread: $<HTMLElement>('#thread'),
  input: $<HTMLTextAreaElement>('#input'),
  send: $<HTMLButtonElement>('#send'),
  nameField: $<HTMLInputElement>('#name-field'),
  keepChat: $<HTMLInputElement>('#keep-chat'),
  reset: $<HTMLButtonElement>('#reset'),
  theme: $<HTMLButtonElement>('#theme'),
  brandSub: $<HTMLElement>('#brand-sub'),
};

const state: State = {
  conversationId: '',
  ownerName: 'the owner',
  examples: DEFAULT_EXAMPLES,
  messages: [],
  keepChat: true,
  visitorName: '',
  streaming: false,
  lastActivity: Date.now(),
  pollTimer: null,
  abort: null,
};

// ---- Init -----------------------------------------------------------------

async function init(): Promise<void> {
  wireThemeToggle(dom.theme);

  // Keep-chat preference (default on). If the user previously turned it off,
  // honour that, but a missing preference means "on".
  state.keepChat = getCookie(KEEP_COOKIE) !== '0';
  dom.keepChat.checked = state.keepChat;

  // Restore the visitor name (separate from keep-chat persistence; harmless).
  try {
    state.visitorName = localStorage.getItem(NAME_KEY) || '';
  } catch {
    state.visitorName = '';
  }
  dom.nameField.value = state.visitorName;

  // Resolve / assign the conversation id.
  let cid: string | null = state.keepChat ? getCookie(CID_COOKIE) : null;
  if (!cid) {
    cid = crypto.randomUUID();
    if (state.keepChat) setCookie(CID_COOKIE, cid);
  }
  state.conversationId = cid;

  // Load owner config (name/subtitle/title) — never hardcode the name.
  await loadConfig();

  // Restore the thread if keep-chat is on.
  if (state.keepChat) {
    await restoreThread();
  } else {
    renderThread();
  }

  wireEvents();

  // Deep link ?q=N -> submit Qn on load, then strip the param.
  const url = new URL(window.location.href);
  const q = url.searchParams.get('q');
  if (q && /^\d+$/.test(q)) {
    url.searchParams.delete('q');
    history.replaceState({}, '', url.pathname + url.search + url.hash);
    void submitMessage(`Q${q}`);
  }

  // Focus the composer on load (preventScroll matters inside an iframe).
  dom.input.focus({ preventScroll: true });

  startPolling();
}

async function loadConfig(): Promise<void> {
  try {
    const cfg: AppConfig = await getConfig();
    if (cfg.owner_name) {
      state.ownerName = cfg.owner_name;
      dom.brandSub.textContent = `Digital Twin of ${cfg.owner_name}`;
      document.title = `Avatar — ${cfg.owner_name}`;
    }
    if (Array.isArray(cfg.examples) && cfg.examples.length > 0) {
      state.examples = cfg.examples;
    }
  } catch {
    // Backend unavailable — keep neutral defaults; do not hardcode an identity.
    dom.brandSub.textContent = 'Digital Twin';
  }
}

async function restoreThread(): Promise<void> {
  try {
    const convo = await getConversation(state.conversationId);
    state.messages = convo.messages || [];
    if (convo.conversation_name && !state.visitorName) {
      state.visitorName = convo.conversation_name;
      dom.nameField.value = state.visitorName;
    }
  } catch {
    state.messages = [];
  }
  renderThread();
}

// ---- Events ---------------------------------------------------------------

function wireEvents(): void {
  dom.input.addEventListener('input', () => autosize(dom.input));

  dom.input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void onSend();
    }
  });

  dom.send.addEventListener('click', () => void onSend());

  dom.nameField.addEventListener('input', () => {
    state.visitorName = dom.nameField.value.trim();
    try {
      localStorage.setItem(NAME_KEY, state.visitorName);
    } catch {
      /* ignore */
    }
    // Re-skin existing visitor avatars with new initials.
    updateVisitorInitials();
  });

  dom.keepChat.addEventListener('change', () => {
    state.keepChat = dom.keepChat.checked;
    if (state.keepChat) {
      setCookie(KEEP_COOKIE, '1');
      setCookie(CID_COOKIE, state.conversationId);
    } else {
      setCookie(KEEP_COOKIE, '0');
      deleteCookie(CID_COOKIE);
    }
  });

  dom.reset.addEventListener('click', () => onReset());
}

function onReset(): void {
  if (state.abort) {
    state.abort.abort();
    state.abort = null; // detach so the in-flight finally leaves fresh state alone
  }
  state.streaming = false;
  setSendEnabled(true);
  state.messages = [];
  state.conversationId = crypto.randomUUID();
  if (state.keepChat) setCookie(CID_COOKIE, state.conversationId);
  renderThread();
  dom.input.value = '';
  autosize(dom.input);
  dom.input.focus({ preventScroll: true });
  state.lastActivity = Date.now();
}

async function onSend(): Promise<void> {
  const text = dom.input.value.trim();
  if (!text || state.streaming) return;
  dom.input.value = '';
  autosize(dom.input);
  await submitMessage(text);
  // Regain focus after sending.
  dom.input.focus({ preventScroll: true });
}

// ---- Sending + streaming --------------------------------------------------

async function submitMessage(text: string): Promise<void> {
  if (state.streaming) return;
  state.streaming = true;
  setSendEnabled(false);
  state.lastActivity = Date.now();
  if (state.keepChat) setCookie(CID_COOKIE, state.conversationId);

  // Optimistically render the visitor bubble (with Qn tag if applicable).
  const now = new Date().toISOString();
  const visitorEl = visitorBubble(text, formatTime(now), state.visitorName);
  dom.thread.append(visitorEl);
  scrollToLatest();

  // Build the streaming avatar bubble shell (typing indicator first).
  const isQn = matchQn(text) !== null;
  const shell = createStreamingAvatar(isQn);
  dom.thread.append(shell.root);
  scrollToLatest();

  const controller = new AbortController();
  state.abort = controller;
  const sentCid = state.conversationId;
  let accumulated = '';
  let firstToken = false;
  let turnErrored = false;

  try {
    for await (const ev of streamChat(
      {
        conversation_id: sentCid,
        message: text,
        visitor_name: state.visitorName || undefined,
      },
      controller.signal
    )) {
      handleEvent(ev, shell, () => {
        if (!firstToken) {
          firstToken = true;
          shell.removeTyping();
        }
      });
      if (ev.type === 'delta') {
        accumulated += ev.text;
        shell.setBody(renderMarkdown(accumulated));
        scrollToLatestIfNear();
      } else if (ev.type === 'done') {
        shell.finalize(formatTime(ev.created_at || now));
      } else if (ev.type === 'error') {
        shell.removeTyping();
        shell.setBody(
          renderMarkdown(
            accumulated || 'Sorry — something went wrong reaching the server. Please try again.'
          )
        );
      }
    }
    // If the stream ended with no content at all, show a gentle fallback.
    if (!accumulated.trim()) {
      shell.setBody(renderMarkdown('_No response — please try again._'));
    }
  } catch (err) {
    if (controller.signal.aborted) {
      // Intentional abort (Reset) — the thread has already been replaced.
      shell.root.remove();
      return;
    }
    // The request was rejected before any reply: drop the optimistic shell AND
    // the visitor bubble (nothing was stored server-side), then show a friendly
    // inline note. Mark the turn errored so the finally block does NOT re-sync
    // from the server — that would wipe the note we just appended.
    turnErrored = true;
    shell.root.remove();
    visitorEl.remove();
    if (err instanceof RateLimitError) {
      appendSystemLine(err.detail);
    } else {
      appendSystemLine('Connection problem — your message may not have been sent. Please try again.');
    }
  } finally {
    if (state.abort === controller) {
      state.streaming = false;
      state.abort = null;
      setSendEnabled(true);
      state.lastActivity = Date.now();
      scrollToLatest();
      // Re-sync from the server so ids/tool data are authoritative — but only on
      // success (a rejected turn has nothing new and the re-render would wipe the
      // inline note), and only if we are still on the conversation we sent for.
      if (!turnErrored && state.conversationId === sentCid) void refreshThreadQuietly();
    }
  }
}

interface StreamShell {
  root: HTMLElement;
  setBody(html: string): void;
  removeTyping(): void;
  addToolLine(line: HTMLElement): void;
  finalize(time: string): void;
}

function createStreamingAvatar(instant: boolean): StreamShell {
  const col = el('div', { class: 'msg__col' });
  const toolStack = el('div', { class: 'tool-stack' });
  const meta = el('div', { class: 'msg__meta' }, [el('span', { class: 'msg__name' }, ['Avatar'])]);
  if (instant) meta.append(el('span', { class: 'badge badge--cyan' }, ['instant']));
  const timeSpan = el('span', { class: 'msg__time' }, ['']);
  meta.append(timeSpan);

  const typing = el('div', { class: 'msg__bubble typing' }, [
    el('span', {}),
    el('span', {}),
    el('span', {}),
  ]);
  const bubble = el('div', { class: 'msg__bubble' });
  bubble.hidden = true;

  // Order: tool stack, then meta, then bubble (matches the mockup).
  col.append(meta, typing, bubble);

  const root = el('div', { class: 'msg msg--avatar' }, [
    el('div', { class: 'avatar avatar--sm avatar--twin' }, [
      el('img', { src: '/assets/avatar-robot-round.png', alt: 'Avatar' }),
    ]),
    col,
  ]);

  let toolStackInserted = false;

  return {
    root,
    setBody(html: string) {
      bubble.hidden = false;
      bubble.innerHTML = html;
    },
    removeTyping() {
      if (typing.parentNode) typing.remove();
    },
    addToolLine(line: HTMLElement) {
      if (!toolStackInserted) {
        col.insertBefore(toolStack, meta);
        toolStackInserted = true;
      }
      toolStack.append(line);
    },
    finalize(time: string) {
      timeSpan.textContent = time;
    },
  };
}

function handleEvent(ev: ChatEvent, shell: StreamShell, onFirstToken: () => void): void {
  if (ev.type === 'tool' && ev.phase === 'called') {
    shell.addToolLine(buildToolLine(ev.tool, ev.detail));
  } else if (ev.type === 'delta') {
    onFirstToken();
  }
}

function buildToolLine(tool: string, detail?: string): HTMLElement {
  const isPush = tool === 'push_tool';
  const cls = `tool-line${isPush ? ' tool-line--push' : ''}`;
  // The SSE `detail` is the raw args JSON string; normalise it to a friendly
  // label (e.g. `Q3` / `notified Emil`) so it matches the stored-render path.
  const friendly = toolDetail(tool, detail, state.ownerName);
  const label = friendly ? `${tool} · ${friendly}` : tool;
  return el('span', { class: cls }, [icon(isPush ? 'i-bell' : 'i-search', 'icon--sm'), label]);
}

// ---- Rendering ------------------------------------------------------------

function renderThread(): void {
  dom.thread.replaceChildren();
  if (state.messages.length === 0) {
    dom.thread.append(buildIntro());
    return;
  }
  let lastDay = '';
  for (const msg of state.messages) {
    const day = formatDaySep(msg.created_at);
    if (day !== lastDay) {
      dom.thread.append(daySeparator(day));
      lastDay = day;
    }
    dom.thread.append(messageBubble(msg, state.ownerName, state.visitorName));
  }
  scrollToLatest();
}

function buildIntro(): HTMLElement {
  const chips = el('div', { class: 'intro__chips' });
  for (const ex of state.examples) {
    const chip = el('button', { class: 'prompt-chip', type: 'button' }, [
      icon('i-sparkles', 'icon--sm'),
      ex,
    ]);
    chip.addEventListener('click', () => {
      if (state.streaming) return;
      void submitMessage(ex);
      dom.input.focus({ preventScroll: true });
    });
    chips.append(chip);
  }

  return el('div', { class: 'intro' }, [
    el('div', { class: 'intro__mark' }, [
      el('img', { src: '/assets/avatar-robot-round.png', alt: 'Avatar' }),
    ]),
    el('h1', { class: 'intro__title' }, [
      `Chat with ${state.ownerName === 'the owner' ? 'the' : state.ownerName + '’s'} digital twin`,
    ]),
    el('p', { class: 'intro__lead' }, [
      'Ask about the work, the stack, projects, or availability. The owner may join the conversation live.',
    ]),
    el('div', { class: 'intro__hint' }, [
      icon('i-zap', 'icon--sm'),
      el('span', {}, ['Tip: type ']),
      el('span', { class: 'qn-tag' }, ['Q1']),
      el('span', {}, [' – ']),
      el('span', { class: 'qn-tag' }, ['Q7']),
      el('span', {}, [' for an instant answer.']),
    ]),
    chips,
  ]);
}

function daySeparator(label: string): HTMLElement {
  return el('div', { class: 'day-sep' }, [el('span', {}, [label])]);
}

function updateVisitorInitials(): void {
  const init = initials(state.visitorName);
  dom.thread.querySelectorAll<HTMLElement>('.msg--visitor .avatar--visitor').forEach((node) => {
    node.textContent = init;
  });
}

function appendSystemLine(text: string): void {
  const line = el('div', { class: 'system-line' }, [icon('i-radio', 'icon--sm'), text]);
  dom.thread.append(line);
  scrollToLatest();
}

function setSendEnabled(enabled: boolean): void {
  dom.send.disabled = !enabled;
}

// ---- Scroll helpers -------------------------------------------------------

function scrollToLatest(): void {
  dom.thread.scrollTop = dom.thread.scrollHeight;
}
function scrollToLatestIfNear(): void {
  const nearBottom =
    dom.thread.scrollHeight - dom.thread.scrollTop - dom.thread.clientHeight < 160;
  if (nearBottom) scrollToLatest();
}

// ---- Polling for the human's async messages -------------------------------

function startPolling(): void {
  scheduleNextPoll();
}

function scheduleNextPoll(): void {
  if (state.pollTimer) clearTimeout(state.pollTimer);
  const idle = Date.now() - state.lastActivity;
  const interval = idle > IDLE_BEFORE_SLOW ? POLL_SLOW : POLL_FAST;
  state.pollTimer = setTimeout(async () => {
    await pollOnce();
    scheduleNextPoll();
  }, interval);
}

async function pollOnce(): Promise<void> {
  if (state.streaming) return; // streaming already keeps the active reply fresh
  try {
    const convo = await getConversation(state.conversationId);
    const incoming = convo.messages || [];
    if (hasNewHumanOrCount(incoming)) {
      state.messages = incoming;
      if (convo.conversation_name && !state.visitorName) {
        state.visitorName = convo.conversation_name;
        dom.nameField.value = state.visitorName;
      }
      renderThread();
    }
  } catch {
    /* network blip — try again next tick */
  }
}

function hasNewHumanOrCount(incoming: Message[]): boolean {
  if (incoming.length !== state.messages.length) return true;
  // Same count: check the latest id changed (covers replaced optimistic rows).
  const a = incoming[incoming.length - 1]?.id;
  const b = state.messages[state.messages.length - 1]?.id;
  return a !== b;
}

async function refreshThreadQuietly(): Promise<void> {
  try {
    const convo = await getConversation(state.conversationId);
    const incoming = convo.messages || [];
    if (incoming.length > 0) {
      state.messages = incoming;
      renderThread();
    }
  } catch {
    /* keep optimistic UI */
  }
}

init();
