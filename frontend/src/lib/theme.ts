// Theme persistence. Dark is the default and the hero; light is a full peer.
// The pre-paint inline <script> in each HTML page sets [data-theme] before this
// module loads, so there is never a flash of the wrong theme.

const KEY = 'avatar-theme';
type Theme = 'dark' | 'light';

export function getTheme(): Theme {
  const attr = document.documentElement.getAttribute('data-theme');
  return attr === 'light' ? 'light' : 'dark';
}

export function setTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme);
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* storage may be unavailable (private mode / sandboxed iframe) — ignore */
  }
}

export function toggleTheme(): Theme {
  const next: Theme = getTheme() === 'dark' ? 'light' : 'dark';
  setTheme(next);
  return next;
}

/** Wire a toggle button (sun/moon glyphs are swapped via CSS per [data-theme]). */
export function wireThemeToggle(button: HTMLElement): void {
  button.addEventListener('click', () => {
    toggleTheme();
  });
}
