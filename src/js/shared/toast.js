// --- Single transient toast (aria-live) with an optional same-origin link ---

let current = null;
let timer = null;

export function dismissToast() {
  if (timer) { clearTimeout(timer); timer = null; }
  if (current) { current.remove(); current = null; }
}

/**
 * Show a toast, replacing any existing one. Text is set via textContent only.
 * `href` must be a same-origin relative path ("/..."); anything else is ignored.
 */
export function showToast(message, { href, linkText } = {}) {
  dismissToast();
  const el = document.createElement('div');
  el.className = 'app-toast';
  el.id = 'app-toast';
  el.setAttribute('role', 'status');
  el.setAttribute('aria-live', 'polite');

  const msg = document.createElement('span');
  msg.className = 'app-toast-msg';
  msg.textContent = String(message);
  el.appendChild(msg);

  if (href && linkText && /^\/(?![\/\\])/.test(href)) {
    const a = document.createElement('a');
    a.className = 'app-toast-link';
    a.setAttribute('href', href);
    a.textContent = String(linkText);
    el.appendChild(a);
  }

  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'app-toast-close';
  close.setAttribute('aria-label', 'Dismiss');
  close.textContent = '×';
  close.addEventListener('click', (e) => { e.stopPropagation(); dismissToast(); });
  el.appendChild(close);

  document.body.appendChild(el);
  current = el;
  timer = setTimeout(() => { if (current === el) dismissToast(); }, 5000);
  return el;
}
