/**
 * Mobile filter drawer: on <= 900px the sidebar is an off-canvas drawer
 * toggled by #btn-filters, closed by the scrim or Escape.
 */
export function initFilterDrawer() {
  const sidebar = document.querySelector('#sidebar');
  const btn = document.querySelector('#btn-filters');
  if (!sidebar || !btn) return;

  let scrim = document.querySelector('#drawer-scrim');
  if (!scrim) {
    scrim = document.createElement('div');
    scrim.id = 'drawer-scrim';
    document.body.appendChild(scrim);
  }

  const setOpen = (open) => {
    sidebar.classList.toggle('is-open', open);
    scrim.classList.toggle('is-open', open);
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  };

  btn.setAttribute('aria-controls', 'sidebar');
  setOpen(false);
  btn.addEventListener('click', () => setOpen(!sidebar.classList.contains('is-open')));
  scrim.addEventListener('click', () => setOpen(false));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && sidebar.classList.contains('is-open')) setOpen(false);
  });
  window.matchMedia('(min-width: 901px)').addEventListener('change', (e) => {
    if (e.matches) setOpen(false);
  });
}
