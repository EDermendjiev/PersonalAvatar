// Admin Dashboard app. Behaviour per SPEC + CONTRACT.md §10 + ux-flows.md.

import {
  adminMe,
  adminLogin,
  adminLogout,
  adminConversations,
  adminOpenConversation,
  adminPostMessage,
  getConversation,
  UnauthorizedError,
  type InboxItem,
  type Message,
} from './lib/api.ts';
import {
  $,
  el,
  formatInboxTime,
  formatDaySep,
  autosize,
  debounce,
} from './lib/dom.ts';
import { icon } from './lib/icons.ts';
import { wireThemeToggle } from './lib/theme.ts';
import { messageBubble } from './lib/bubbles.ts';

const INBOX_POLL = 15_000; // refresh inbox list
const THREAD_POLL = 10_000; // refresh the open thread for new visitor/avatar rows
const MOBILE_BP = 860;

const dom = {
  loginScreen: $<HTMLElement>('#login-screen'),
  loginForm: $<HTMLFormElement>('#login-form'),
  password: $<HTMLInputElement>('#password'),
  loginError: $<HTMLElement>('#login-error'),
  loginSubmit: $<HTMLButtonElement>('#login-submit'),

  admin: $<HTMLElement>('#admin'),
  inbox: $<HTMLElement>('#inbox'),
  unreadBadge: $<HTMLElement>('#unread-badge'),
  search: $<HTMLInputElement>('#search'),
  logout: $<HTMLButtonElement>('#logout'),
  theme: $<HTMLButtonElement>('#theme'),

  panelHead: $<HTMLElement>('#panel-head'),
  panelBack: $<HTMLButtonElement>('#panel-back'),
  panelAvatar: $<HTMLElement>('#panel-avatar'),
  panelName: $<HTMLElement>('#panel-name'),
  panelMeta: $<HTMLElement>('#panel-meta'),
  panelId: $<HTMLElement>('#panel-id'),
  panelStatus: $<HTMLElement>('#panel-status'),
  panelThread: $<HTMLElement>('#panel-thread'),
  panelEmpty: $<HTMLElement>('#panel-empty'),
  panelDock: $<HTMLElement>('#panel-dock'),
  asMe: $<HTMLElement>('#as-me'),
  replyInput: $<HTMLTextAreaElement>('#reply-input'),
  replySend: $<HTMLButtonElement>('#reply-send'),
};

interface State {
  ownerName: string;
  items: InboxItem[];
  filtered: InboxItem[];
  activeId: string | null;
  activeMessages: Message[];
  search: string;
  sending: boolean;
  inboxTimer: ReturnType<typeof setInterval> | null;
  threadTimer: ReturnType<typeof setInterval> | null;
}

const state: State = {
  ownerName: 'owner',
  items: [],
  filtered: [],
  activeId: null,
  activeMessages: [],
  search: '',
  sending: false,
  inboxTimer: null,
  threadTimer: null,
};

// ---- Init / auth gate -----------------------------------------------------

async function init(): Promise<void> {
  wireThemeToggle(dom.theme);
  wireLogin();

  try {
    const me = await adminMe();
    if (me.owner_name) state.ownerName = me.owner_name;
    if (me.authenticated) {
      enterDashboard();
    } else {
      showLogin();
    }
  } catch {
    showLogin();
  }
}

function showLogin(): void {
  dom.loginScreen.hidden = false;
  dom.admin.hidden = true;
  dom.password.focus({ preventScroll: true });
}

function wireLogin(): void {
  dom.loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const pw = dom.password.value;
    if (!pw) return;
    dom.loginError.hidden = true;
    dom.loginSubmit.disabled = true;
    try {
      const res = await adminLogin(pw);
      if (res.owner_name) state.ownerName = res.owner_name;
      dom.password.value = '';
      enterDashboard();
    } catch (err) {
      dom.loginError.hidden = false;
      if (!(err instanceof UnauthorizedError)) {
        dom.loginError.textContent = 'Could not reach the server. Try again.';
      } else {
        dom.loginError.textContent = "That password didn't work. Try again.";
      }
      dom.password.select();
    } finally {
      dom.loginSubmit.disabled = false;
    }
  });
}

let dashboardWired = false;

function enterDashboard(): void {
  dom.loginScreen.hidden = true;
  dom.admin.hidden = false;
  document.title = `Avatar — Admin · ${state.ownerName}`;
  dom.asMe.textContent = `Posting as ${state.ownerName}`;
  dom.replyInput.placeholder = `Reply as ${firstName(state.ownerName)}…`;
  if (!dashboardWired) {
    wireDashboard();
    dashboardWired = true;
  }
  showEmptyState();
  void loadInbox();
  startInboxPolling();
}

function firstName(name: string): string {
  return (name || '').trim().split(/\s+/)[0] || name || 'owner';
}

// ---- Dashboard wiring -----------------------------------------------------

function wireDashboard(): void {
  dom.logout.addEventListener('click', async () => {
    await adminLogout();
    stopAllPolling();
    state.activeId = null;
    state.activeMessages = [];
    showEmptyState();
    dom.admin.classList.remove('show-detail');
    showLogin();
  });

  dom.search.addEventListener(
    'input',
    debounce(() => {
      state.search = dom.search.value.trim().toLowerCase();
      applyFilter();
      renderInbox();
    }, 120)
  );

  dom.panelBack.addEventListener('click', () => {
    dom.admin.classList.remove('show-detail');
    state.activeId = null;
    state.activeMessages = [];
    stopThreadPolling();
    showEmptyState();
    renderInbox();
  });

  dom.replyInput.addEventListener('input', () => autosize(dom.replyInput));
  dom.replyInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void sendReply();
    }
  });
  dom.replySend.addEventListener('click', () => void sendReply());

  // Arrow keys move between conversations (when not typing in the composer/search).
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
    const target = e.target as HTMLElement | null;
    if (
      target &&
      (target.tagName === 'TEXTAREA' || target.tagName === 'INPUT')
    ) {
      return;
    }
    if (state.filtered.length === 0) return;
    e.preventDefault();
    moveSelection(e.key === 'ArrowDown' ? 1 : -1);
  });
}

function moveSelection(delta: number): void {
  const ids = state.filtered.map((c) => c.conversation_id);
  let idx = state.activeId ? ids.indexOf(state.activeId) : -1;
  idx = idx === -1 ? (delta > 0 ? 0 : ids.length - 1) : idx + delta;
  idx = Math.max(0, Math.min(ids.length - 1, idx));
  const next = ids[idx];
  if (next && next !== state.activeId) void openConversation(next);
}

// ---- Inbox ----------------------------------------------------------------

async function loadInbox(): Promise<void> {
  try {
    state.items = await adminConversations();
    applyFilter();
    renderInbox();
  } catch (err) {
    if (err instanceof UnauthorizedError) {
      stopAllPolling();
      showLogin();
    }
  }
}

function applyFilter(): void {
  if (!state.search) {
    state.filtered = state.items;
    return;
  }
  state.filtered = state.items.filter((c) => {
    return (
      (c.name || '').toLowerCase().includes(state.search) ||
      (c.preview || '').toLowerCase().includes(state.search) ||
      (c.initials || '').toLowerCase().includes(state.search)
    );
  });
}

function renderInbox(): void {
  const totalUnread = state.items.reduce((n, c) => n + (c.unread_count > 0 ? 1 : 0), 0);
  if (totalUnread > 0) {
    dom.unreadBadge.hidden = false;
    dom.unreadBadge.textContent = `${totalUnread} unread`;
  } else {
    dom.unreadBadge.hidden = true;
  }

  dom.inbox.replaceChildren();

  if (state.filtered.length === 0) {
    dom.inbox.append(
      el('div', { class: 'inbox-empty' }, [
        state.search ? 'No conversations match your search.' : 'No conversations yet.',
      ])
    );
    return;
  }

  for (const c of state.filtered) {
    dom.inbox.append(inboxRow(c));
  }
}

function inboxRow(c: InboxItem): HTMLElement {
  const classes = ['convo-item'];
  const unread = c.unread_count > 0;
  if (unread) classes.push('is-unread');
  if (c.needs_attention) classes.push('needs-attention');
  if (c.conversation_id === state.activeId) classes.push('is-active');

  const flags = el('div', { class: 'convo-item__flags' });
  if (c.needs_attention) {
    flags.append(
      el('span', { class: 'attn-flag', title: 'Needs your attention' }, [
        icon('i-bell-dot', 'icon--sm'),
      ])
    );
  } else if (unread) {
    flags.append(el('span', { class: 'unread-dot', title: 'Unread' }));
  }

  const row = el('div', { class: classes.join(' ') }, [
    el('div', { class: 'avatar avatar--sm avatar--visitor' }, [c.initials || '·']),
    el('div', { class: 'convo-item__main' }, [
      el('div', { class: 'convo-item__top' }, [
        el('span', { class: 'convo-item__name' }, [c.name || c.initials || 'Visitor']),
        el('span', { class: 'convo-item__time' }, [formatInboxTime(c.last_at)]),
      ]),
      el('div', { class: 'convo-item__preview' }, [c.preview || '…']),
    ]),
    flags,
  ]);

  row.addEventListener('click', () => void openConversation(c.conversation_id));
  return row;
}

// ---- Open / render a thread ----------------------------------------------

async function openConversation(id: string): Promise<void> {
  state.activeId = id;
  renderInbox(); // reflect the active selection immediately
  stopThreadPolling();

  showThreadChrome();
  dom.panelThread.replaceChildren(
    el('div', { class: 'panel__loading' }, ['Loading conversation…'])
  );

  if (window.innerWidth <= MOBILE_BP) {
    dom.admin.classList.add('show-detail');
  }

  try {
    const convo = await adminOpenConversation(id);
    state.activeMessages = convo.messages || [];
    renderThread(convo.conversation_name, id);
    // Opening marked everything read server-side; reflect locally.
    markItemRead(id);
    renderInbox();
    startThreadPolling();
  } catch (err) {
    if (err instanceof UnauthorizedError) {
      stopAllPolling();
      showLogin();
      return;
    }
    dom.panelThread.replaceChildren(
      el('div', { class: 'panel__loading' }, ['Could not load this conversation.'])
    );
  }
}

function showThreadChrome(): void {
  dom.panelEmpty.hidden = true;
  dom.panelThread.hidden = false;
  dom.panelHead.hidden = false;
  dom.panelDock.hidden = false;
}

function showEmptyState(): void {
  dom.panelEmpty.hidden = false;
  dom.panelThread.hidden = true;
  dom.panelThread.replaceChildren();
  dom.panelHead.hidden = true;
  dom.panelDock.hidden = true;
}

function markItemRead(id: string): void {
  const item = state.items.find((c) => c.conversation_id === id);
  if (item) {
    item.unread_count = 0;
    item.needs_attention = false;
  }
}

function renderThread(name: string | null, id: string, forceScroll = true): void {
  // Preserve the reader's scroll position on background refreshes.
  const nearBottom =
    dom.panelThread.scrollHeight - dom.panelThread.scrollTop - dom.panelThread.clientHeight < 200;

  // Header
  const item = state.items.find((c) => c.conversation_id === id);
  const initialsStr = item?.initials || (name ? name.slice(0, 2).toUpperCase() : '·');
  const visitorLabel = name || item?.name || null;
  dom.panelAvatar.textContent = initialsStr;
  dom.panelName.textContent = name || item?.name || initialsStr || 'Conversation';
  const count = state.activeMessages.length;
  const firstSeen = count > 0 ? formatDaySep(state.activeMessages[0].created_at) : '';
  dom.panelMeta.textContent = `${firstSeen ? 'First seen ' + firstSeen.toLowerCase() + ' · ' : ''}${count} message${count === 1 ? '' : 's'}`;
  dom.panelId.textContent = `conv · ${shortId(id)}`;
  dom.panelStatus.replaceChildren(
    el('span', { class: 'status-dot status-dot--live' }),
    document.createTextNode('read')
  );

  // Thread body
  dom.panelThread.replaceChildren();
  if (count === 0) {
    dom.panelThread.append(
      el('div', { class: 'panel__loading' }, ['No messages in this conversation yet.'])
    );
    return;
  }
  let lastDay = '';
  for (const msg of state.activeMessages) {
    const day = formatDaySep(msg.created_at);
    if (day !== lastDay) {
      dom.panelThread.append(daySeparator(day));
      lastDay = day;
    }
    dom.panelThread.append(messageBubble(msg, state.ownerName, visitorLabel));
  }
  if (forceScroll || nearBottom) scrollThreadToLatest();
}

function daySeparator(label: string): HTMLElement {
  return el('div', { class: 'day-sep' }, [el('span', {}, [label])]);
}

function shortId(id: string): string {
  if (id.length <= 13) return id;
  return `${id.slice(0, 4)}-…-${id.slice(-4)}`;
}

function scrollThreadToLatest(): void {
  dom.panelThread.scrollTop = dom.panelThread.scrollHeight;
}

// ---- Reply as owner -------------------------------------------------------

async function sendReply(): Promise<void> {
  const text = dom.replyInput.value.trim();
  if (!text || !state.activeId || state.sending) return;
  state.sending = true;
  dom.replySend.disabled = true;
  const id = state.activeId;
  dom.replyInput.value = '';
  autosize(dom.replyInput);

  try {
    const row = await adminPostMessage(id, text);
    if (id === state.activeId) {
      state.activeMessages.push(row);
      appendBubble(row);
      scrollThreadToLatest();
    }
  } catch (err) {
    if (err instanceof UnauthorizedError) {
      stopAllPolling();
      showLogin();
      return;
    }
    // Restore the text so the owner can retry.
    dom.replyInput.value = text;
    autosize(dom.replyInput);
  } finally {
    state.sending = false;
    dom.replySend.disabled = false;
    dom.replyInput.focus({ preventScroll: true });
  }
}

function appendBubble(msg: Message): void {
  const last = state.activeMessages[state.activeMessages.length - 2];
  const day = formatDaySep(msg.created_at);
  if (!last || formatDaySep(last.created_at) !== day) {
    // Only add a separator if the thread doesn't already end on this day.
    const existing = dom.panelThread.querySelectorAll('.day-sep');
    const lastSep = existing[existing.length - 1]?.textContent?.trim();
    if (lastSep !== day) dom.panelThread.append(daySeparator(day));
  }
  dom.panelThread.append(messageBubble(msg, state.ownerName));
}

// ---- Polling --------------------------------------------------------------

function startInboxPolling(): void {
  stopInboxPolling();
  state.inboxTimer = setInterval(() => void loadInbox(), INBOX_POLL);
}
function stopInboxPolling(): void {
  if (state.inboxTimer) clearInterval(state.inboxTimer);
  state.inboxTimer = null;
}
function startThreadPolling(): void {
  stopThreadPolling();
  state.threadTimer = setInterval(() => void pollThread(), THREAD_POLL);
}
function stopThreadPolling(): void {
  if (state.threadTimer) clearInterval(state.threadTimer);
  state.threadTimer = null;
}
function stopAllPolling(): void {
  stopInboxPolling();
  stopThreadPolling();
}

async function pollThread(): Promise<void> {
  if (!state.activeId || state.sending) return;
  const id = state.activeId;
  try {
    // Read-only fetch first: cheap, and detects new visitor/avatar rows.
    const convo = await getConversation(id);
    const incoming = convo.messages || [];
    const changed =
      incoming.length !== state.activeMessages.length ||
      incoming[incoming.length - 1]?.id !== state.activeMessages[state.activeMessages.length - 1]?.id;
    if (!changed || id !== state.activeId) return;

    // New rows arrived while this thread is open — mark them read (the admin is
    // actively viewing) so the inbox doesn't flag the conversation you're on.
    const hasUnread = incoming.some((m) => !m.read);
    const fresh = hasUnread ? await adminOpenConversation(id) : convo;
    if (id !== state.activeId) return;

    state.activeMessages = fresh.messages || incoming;
    renderThread(fresh.conversation_name ?? convo.conversation_name, id, false);
    if (hasUnread) {
      markItemRead(id);
      renderInbox();
    }
  } catch (err) {
    if (err instanceof UnauthorizedError) {
      stopAllPolling();
      showLogin();
    }
    /* otherwise transient — retry next tick */
  }
}

init();
