// Icon helper. Builds an inline <svg class="icon"><use href="/icons.svg#i-..."/></svg>
// that references the shared sprite copied into public/icons.svg. Icons inherit
// currentColor, so colour comes from the surrounding text/role styles.

/** Build an SVG icon element referencing a sprite symbol id (e.g. "i-send"). */
export function icon(id: string, extraClass = ''): SVGSVGElement {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', `icon${extraClass ? ' ' + extraClass : ''}`);
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', `/icons.svg#${id}`);
  svg.append(use);
  return svg;
}
